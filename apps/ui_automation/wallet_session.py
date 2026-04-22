from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import signal

import httpx
from django.utils import timezone

from apps.ui_automation.models import WalletBrowserConfig, WalletSession


DEFAULT_PROFILE_DIRECTORY = 'Default'
DEFAULT_DEBUGGER_HOST = '127.0.0.1'
RUNTIME_PROFILE_ROOT_NAME = 'testhub_wallet_profiles'
METAMASK_KNOWN_EXTENSION_IDS = [
    'nkbihfbeogaeaoehlefnkodbefgpgknn',
]
GLOBAL_PROFILE_LAUNCH_MODE = 'global_profile'
RUNTIME_CLONE_LAUNCH_MODE = 'runtime_clone'


@dataclass(frozen=True)
class ChromeLaunchResult:
    process_id: int
    cdp_url: str
    debugger_address: str
    remote_debugging_port: int
    metamask_extension_id: str
    runtime_user_data_dir: str


def is_supported_chrome_executable(chrome_executable_path: str) -> bool:
    normalized_path = str(chrome_executable_path or '').strip().lower().replace('/', '\\')
    if not normalized_path:
        return False

    filename = Path(normalized_path).name
    if any(marker in normalized_path for marker in ('msedge', 'microsoft\\edge', 'chromedriver')):
        return False

    return 'chrome' in filename and 'driver' not in filename


def build_chrome_launch_args(
    chrome_executable_path: str,
    user_data_dir: str,
    profile_directory: str,
    remote_debugging_port: int,
):
    profile_name = profile_directory or DEFAULT_PROFILE_DIRECTORY
    return [
        chrome_executable_path,
        f'--user-data-dir={user_data_dir}',
        f'--profile-directory={profile_name}',
        f'--remote-debugging-port={remote_debugging_port}',
        '--disable-quic',
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--disable-popup-blocking',
        '--hide-crash-restore-bubble',
        '--no-first-run',
        '--no-default-browser-check',
        '--start-maximized',
    ]


def terminate_existing_chrome():
    if os.name == 'nt':
        taskkill_path = shutil.which('taskkill') or os.path.join(
            os.environ.get('SystemRoot', r'C:\Windows'),
            'System32',
            'taskkill.exe',
        )
        command = [taskkill_path, '/F', '/IM', 'chrome.exe']
    else:
        command = ['pkill', '-f', 'chrome']

    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return


def terminate_wallet_browser_process(process_id: int | None):
    if not process_id:
        return

    if os.name == 'nt':
        taskkill_path = shutil.which('taskkill') or os.path.join(
            os.environ.get('SystemRoot', r'C:\Windows'),
            'System32',
            'taskkill.exe',
        )
        command = [taskkill_path, '/PID', str(process_id), '/T', '/F']
        try:
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return
        return

    try:
        os.kill(int(process_id), signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        return


def is_debugging_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((DEFAULT_DEBUGGER_HOST, int(port))) == 0


def find_free_debugging_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_DEBUGGER_HOST, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def resolve_wallet_remote_debugging_port(preferred_port: int) -> int:
    preferred_port = int(preferred_port)
    if preferred_port > 0 and not is_debugging_port_in_use(preferred_port):
        return preferred_port
    return find_free_debugging_port()


def is_default_chrome_user_data_dir(user_data_dir: str) -> bool:
    candidate = Path(user_data_dir).expanduser()
    try:
        candidate = candidate.resolve(strict=False)
    except Exception:
        candidate = Path(str(candidate))

    default_dirs = []
    if os.name == 'nt':
        local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
        default_dirs.append(Path(local_appdata) / 'Google' / 'Chrome' / 'User Data')
    elif sys.platform == 'darwin':
        default_dirs.append(Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome')
    else:
        default_dirs.extend(
            [
                Path.home() / '.config' / 'google-chrome',
                Path.home() / '.config' / 'chromium',
            ]
        )

    normalized_candidate = os.path.normcase(str(candidate))
    for default_dir in default_dirs:
        try:
            normalized_default = os.path.normcase(str(default_dir.expanduser().resolve(strict=False)))
        except Exception:
            normalized_default = os.path.normcase(str(default_dir))
        if normalized_candidate == normalized_default:
            return True
    return False


def wait_for_cdp_url(port: int, attempts: int = 15, sleep_seconds: float = 1.0) -> str:
    endpoint = f'http://{DEFAULT_DEBUGGER_HOST}:{port}/json/version'
    last_error = None

    for attempt in range(attempts):
        try:
            response = httpx.get(endpoint, timeout=5.0)
            response.raise_for_status()
            websocket_url = response.json().get('webSocketDebuggerUrl')
            if websocket_url:
                return websocket_url
            last_error = RuntimeError(f'CDP endpoint returned no webSocketDebuggerUrl: {endpoint}')
        except Exception as exc:
            last_error = exc

        if attempt < attempts - 1:
            time.sleep(sleep_seconds)

    raise RuntimeError(f'Unable to get CDP URL from {endpoint}') from last_error


def probe_wallet_cdp_capabilities(
    debugger_address: str = '',
    remote_debugging_port: int | None = None,
    metamask_extension_id: str = '',
) -> dict:
    debugger_address = str(debugger_address or '').strip()
    extension_id = str(metamask_extension_id or '').strip()

    if debugger_address:
        endpoint = f'http://{debugger_address}/json/list'
    elif remote_debugging_port:
        endpoint = f'http://{DEFAULT_DEBUGGER_HOST}:{int(remote_debugging_port)}/json/list'
    else:
        return {
            'cdp_connected': False,
            'extension_pages_visible': False,
            'extension_page_urls': [],
            'unsupported_reason': 'Chrome CDP debugger address is missing',
        }

    if not extension_id:
        return {
            'cdp_connected': False,
            'extension_pages_visible': False,
            'extension_page_urls': [],
            'unsupported_reason': 'MetaMask extension id is missing',
        }

    try:
        response = httpx.get(endpoint, timeout=5.0)
        response.raise_for_status()
        targets = response.json()
    except Exception as exc:
        return {
            'cdp_connected': False,
            'extension_pages_visible': False,
            'extension_page_urls': [],
            'unsupported_reason': f'Unable to query Chrome CDP targets: {exc}',
        }

    if not isinstance(targets, list):
        targets = []

    prefix = f'chrome-extension://{extension_id}/'
    extension_page_urls = [
        str(target.get('url') or '').strip()
        for target in targets
        if str(target.get('type') or '').strip().lower() == 'page'
        and str(target.get('url') or '').strip().startswith(prefix)
    ]

    return {
        'cdp_connected': True,
        'extension_pages_visible': bool(extension_page_urls),
        'extension_page_urls': extension_page_urls,
        'unsupported_reason': (
            ''
            if extension_page_urls
            else 'MetaMask extension pages are not visible via CDP. Only Chrome + MetaMask full-page mode is supported.'
        ),
    }


def detect_metamask_extension_id(user_data_dir: str, profile_directory: str) -> str:
    profile_name = profile_directory or DEFAULT_PROFILE_DIRECTORY
    candidate_dirs = [
        Path(user_data_dir) / profile_name / 'Local Extension Settings',
        Path(user_data_dir) / profile_name / 'Extensions',
    ]

    for base_dir in candidate_dirs:
        if not base_dir.exists():
            continue
        for extension_id in METAMASK_KNOWN_EXTENSION_IDS:
            if (base_dir / extension_id).exists():
                return extension_id

    return ''


def build_wallet_profile_copy_plan(
    source_user_data_dir: str,
    profile_directory: str,
    extension_id: str,
    runtime_user_data_dir: str,
):
    profile_name = profile_directory or DEFAULT_PROFILE_DIRECTORY
    source_root = Path(source_user_data_dir)
    runtime_root = Path(runtime_user_data_dir)

    return [
        (source_root / 'Local State', runtime_root / 'Local State', True),
        (source_root / profile_name / 'Preferences', runtime_root / profile_name / 'Preferences', True),
        (source_root / profile_name / 'Secure Preferences', runtime_root / profile_name / 'Secure Preferences', True),
        (
            source_root / profile_name / 'Extensions' / extension_id,
            runtime_root / profile_name / 'Extensions' / extension_id,
            True,
        ),
        (
            source_root / profile_name / 'Local Extension Settings' / extension_id,
            runtime_root / profile_name / 'Local Extension Settings' / extension_id,
            True,
        ),
        (
            source_root / profile_name / 'IndexedDB' / f'chrome-extension_{extension_id}_0.indexeddb.leveldb',
            runtime_root / profile_name / 'IndexedDB' / f'chrome-extension_{extension_id}_0.indexeddb.leveldb',
            False,
        ),
        (
            source_root / profile_name / 'IndexedDB' / f'chrome-extension_{extension_id}_0.indexeddb.blob',
            runtime_root / profile_name / 'IndexedDB' / f'chrome-extension_{extension_id}_0.indexeddb.blob',
            False,
        ),
        (
            source_root / profile_name / 'Extension State',
            runtime_root / profile_name / 'Extension State',
            False,
        ),
        (
            source_root / profile_name / 'Sync Extension Settings',
            runtime_root / profile_name / 'Sync Extension Settings',
            False,
        ),
    ]


def copy_wallet_profile_asset(source_path: Path, target_path: Path, required: bool):
    if not source_path.exists():
        if required:
            raise RuntimeError(f'Required wallet profile asset is missing: {source_path}')
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
        else:
            shutil.copy2(source_path, target_path)
    except PermissionError as exc:
        raise RuntimeError(
            f'Unable to copy wallet profile asset. Close Chrome or enable force close first: {source_path}'
        ) from exc


def sanitize_wallet_runtime_profile(runtime_user_data_dir: str, profile_directory: str):
    profile_name = profile_directory or DEFAULT_PROFILE_DIRECTORY
    preferences_path = Path(runtime_user_data_dir) / profile_name / 'Preferences'
    if not preferences_path.exists():
        return

    preferences_data = json.loads(preferences_path.read_text(encoding='utf-8'))
    profile_data = preferences_data.get('profile')
    if isinstance(profile_data, dict) and profile_data.get('exit_type') == 'Crashed':
        profile_data['exit_type'] = 'Normal'
        preferences_path.write_text(
            json.dumps(preferences_data, ensure_ascii=True, separators=(',', ':')),
            encoding='utf-8',
        )


def clone_wallet_profile(
    source_user_data_dir: str,
    profile_directory: str,
    extension_id: str,
    session_id: int,
) -> str:
    runtime_root = Path(tempfile.gettempdir()) / RUNTIME_PROFILE_ROOT_NAME / f'session-{session_id}'

    if runtime_root.exists():
        shutil.rmtree(runtime_root, ignore_errors=True)

    runtime_root.mkdir(parents=True, exist_ok=True)

    for source_path, target_path, required in build_wallet_profile_copy_plan(
        source_user_data_dir=source_user_data_dir,
        profile_directory=profile_directory,
        extension_id=extension_id,
        runtime_user_data_dir=str(runtime_root),
    ):
        copy_wallet_profile_asset(source_path, target_path, required)

    sanitize_wallet_runtime_profile(str(runtime_root), profile_directory)

    return str(runtime_root)


def _resolve_wallet_runtime_root() -> Path:
    return Path(tempfile.gettempdir()).resolve(strict=False) / RUNTIME_PROFILE_ROOT_NAME


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def cleanup_wallet_runtime_profile(runtime_user_data_dir: str):
    runtime_user_data_dir = str(runtime_user_data_dir or '').strip()
    if not runtime_user_data_dir:
        return

    runtime_path = Path(runtime_user_data_dir).resolve(strict=False)
    runtime_root = _resolve_wallet_runtime_root()
    if not _is_relative_to(runtime_path, runtime_root):
        return
    if not runtime_path.exists():
        return

    shutil.rmtree(runtime_path, ignore_errors=True)


def get_active_wallet_browser_config() -> WalletBrowserConfig | None:
    return WalletBrowserConfig.objects.filter(is_active=True).order_by('-updated_at').first()


def resolve_metamask_extension_id(config: WalletBrowserConfig) -> str:
    extension_id = config.metamask_extension_id or detect_metamask_extension_id(
        config.user_data_dir,
        config.profile_directory,
    )
    if not extension_id:
        raise RuntimeError('MetaMask extension was not found in the configured Chrome profile')
    return extension_id


def resolve_wallet_launch_mode(config: WalletBrowserConfig) -> str:
    launch_mode = str(getattr(config, 'launch_mode', RUNTIME_CLONE_LAUNCH_MODE) or RUNTIME_CLONE_LAUNCH_MODE)
    if launch_mode == GLOBAL_PROFILE_LAUNCH_MODE:
        return GLOBAL_PROFILE_LAUNCH_MODE
    return RUNTIME_CLONE_LAUNCH_MODE


def launch_chrome_for_wallet(
    config: WalletBrowserConfig,
    session_id: int,
    force_close_existing_chrome: bool | None = None,
) -> ChromeLaunchResult:
    should_force_close = config.force_close_existing_chrome
    if force_close_existing_chrome is not None:
        should_force_close = bool(force_close_existing_chrome)

    if should_force_close:
        terminate_existing_chrome()
        time.sleep(1.0)

    extension_id = resolve_metamask_extension_id(config)
    launch_mode = resolve_wallet_launch_mode(config)
    runtime_user_data_dir = config.user_data_dir
    if launch_mode != GLOBAL_PROFILE_LAUNCH_MODE:
        runtime_user_data_dir = clone_wallet_profile(
            source_user_data_dir=config.user_data_dir,
            profile_directory=config.profile_directory,
            extension_id=extension_id,
            session_id=session_id,
        )
    remote_debugging_port = resolve_wallet_remote_debugging_port(config.remote_debugging_port)

    args = build_chrome_launch_args(
        chrome_executable_path=config.chrome_executable_path,
        user_data_dir=runtime_user_data_dir,
        profile_directory=config.profile_directory,
        remote_debugging_port=remote_debugging_port,
    )
    process = subprocess.Popen(args)
    try:
        cdp_url = wait_for_cdp_url(remote_debugging_port)
    except Exception as exc:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:
                pass

        if launch_mode == GLOBAL_PROFILE_LAUNCH_MODE and is_default_chrome_user_data_dir(config.user_data_dir):
            raise RuntimeError(
                'Chrome 136+ blocks remote debugging on the default Chrome user data directory. '
                'The current global_profile launch mode cannot attach to your real Chrome profile. '
                'Switch to runtime_clone or use a non-default Chrome user data directory.'
            ) from exc
        if launch_mode == RUNTIME_CLONE_LAUNCH_MODE:
            cleanup_wallet_runtime_profile(runtime_user_data_dir)
        raise

    return ChromeLaunchResult(
        process_id=process.pid,
        cdp_url=cdp_url,
        debugger_address=f'{DEFAULT_DEBUGGER_HOST}:{remote_debugging_port}',
        remote_debugging_port=remote_debugging_port,
        metamask_extension_id=extension_id,
        runtime_user_data_dir=runtime_user_data_dir,
    )


def launch_controlled_chrome(
    config: WalletBrowserConfig,
    started_by,
    force_close_existing_chrome: bool | None = None,
) -> WalletSession:
    session = WalletSession.objects.create(
        wallet_provider=config.wallet_provider,
        chrome_executable_path=config.chrome_executable_path,
        user_data_dir=config.user_data_dir,
        profile_directory=config.profile_directory,
        launch_mode=resolve_wallet_launch_mode(config),
        remote_debugging_port=config.remote_debugging_port,
        started_by=started_by,
        status='pending',
    )

    try:
        launch_result = launch_chrome_for_wallet(
            config,
            session_id=session.id,
            force_close_existing_chrome=force_close_existing_chrome,
        )
    except Exception as exc:
        session.status = 'failed'
        session.error_message = str(exc)
        session.finished_at = timezone.now()
        session.save(update_fields=['status', 'error_message', 'finished_at'])
        raise

    session.cdp_url = launch_result.cdp_url
    session.debugger_address = launch_result.debugger_address
    session.process_id = launch_result.process_id
    session.remote_debugging_port = launch_result.remote_debugging_port
    session.metamask_extension_id = launch_result.metamask_extension_id
    session.runtime_user_data_dir = launch_result.runtime_user_data_dir
    session.status = 'running'
    session.save(
        update_fields=[
            'cdp_url',
            'debugger_address',
            'process_id',
            'remote_debugging_port',
            'metamask_extension_id',
            'runtime_user_data_dir',
            'status',
        ]
    )
    return session


def prepare_wallet_browser_session(
    started_by,
    force_close_existing_chrome: bool | None = None,
) -> WalletSession:
    config = get_active_wallet_browser_config()
    if not config:
        raise RuntimeError('No active wallet browser configuration is available')

    return launch_controlled_chrome(
        config,
        started_by=started_by,
        force_close_existing_chrome=force_close_existing_chrome,
    )


def finalize_wallet_session(session: WalletSession, status: str, error_message: str = '') -> WalletSession:
    terminate_wallet_browser_process(getattr(session, 'process_id', None))
    if getattr(session, 'launch_mode', '') == RUNTIME_CLONE_LAUNCH_MODE:
        cleanup_wallet_runtime_profile(getattr(session, 'runtime_user_data_dir', ''))
    session.status = status
    session.error_message = error_message
    session.finished_at = timezone.now()
    session.save(update_fields=['status', 'error_message', 'finished_at'])
    return session
