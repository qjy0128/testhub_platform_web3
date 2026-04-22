from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from apps.ui_automation.wallet_session import (
    build_chrome_launch_args,
    clone_wallet_profile,
    detect_metamask_extension_id,
    finalize_wallet_session,
    is_supported_chrome_executable,
    launch_chrome_for_wallet,
    probe_wallet_cdp_capabilities,
    resolve_wallet_remote_debugging_port,
    sanitize_wallet_runtime_profile,
    terminate_existing_chrome,
    wait_for_cdp_url,
)


class WalletSessionServiceTests(SimpleTestCase):
    def test_is_supported_chrome_executable_rejects_edge_binary(self):
        self.assertFalse(
            is_supported_chrome_executable(
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
            )
        )

    def test_is_supported_chrome_executable_accepts_chrome_binary(self):
        self.assertTrue(
            is_supported_chrome_executable(
                r'C:\Program Files\Google\Chrome\Application\chrome.exe'
            )
        )

    def test_build_chrome_launch_args_preserves_extensions(self):
        args = build_chrome_launch_args(
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9333,
        )

        command = ' '.join(args)
        self.assertIn('--user-data-dir=', command)
        self.assertIn('--profile-directory=Default', command)
        self.assertIn('--remote-debugging-port=9333', command)
        self.assertIn('--hide-crash-restore-bubble', command)
        self.assertIn('--disable-quic', command)
        self.assertNotIn('--disable-extensions', command)

    def test_detect_metamask_extension_id_from_profile_tree(self):
        def fake_exists(path_obj):
            path = str(path_obj)
            return (
                path.endswith(r'Default\Local Extension Settings')
                or path.endswith(r'Default\Local Extension Settings\nkbihfbeogaeaoehlefnkodbefgpgknn')
            )

        with patch('apps.ui_automation.wallet_session.Path.exists', autospec=True) as mock_exists:
            mock_exists.side_effect = fake_exists

            extension_id = detect_metamask_extension_id(
                r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
                'Default',
            )

        self.assertEqual(extension_id, 'nkbihfbeogaeaoehlefnkodbefgpgknn')

    @patch('apps.ui_automation.wallet_session.httpx.get')
    def test_wait_for_cdp_url_reads_websocket_debugger_url(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/test'
        }
        mock_get.return_value = response

        cdp_url = wait_for_cdp_url(9222, attempts=1, sleep_seconds=0)

        self.assertEqual(cdp_url, 'ws://127.0.0.1:9222/devtools/browser/test')

    @patch('apps.ui_automation.wallet_session.httpx.get')
    def test_probe_wallet_cdp_capabilities_reports_visible_extension_pages(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {'id': 'page-1', 'type': 'page', 'url': 'https://example.com/'},
            {
                'id': 'page-2',
                'type': 'page',
                'url': 'chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html#/unlock',
            },
        ]
        mock_get.return_value = response

        result = probe_wallet_cdp_capabilities(
            debugger_address='127.0.0.1:9222',
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
        )

        self.assertTrue(result['cdp_connected'])
        self.assertTrue(result['extension_pages_visible'])
        self.assertEqual(
            result['extension_page_urls'],
            ['chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html#/unlock'],
        )

    def test_clone_wallet_profile_copies_runtime_assets(self):
        extension_id = 'nkbihfbeogaeaoehlefnkodbefgpgknn'
        runtime_root = Path(r'D:\wallet-runtime')
        cloned_dir = runtime_root / 'testhub_wallet_profiles' / 'session-17'
        copy_plan = [
            (Path(r'C:\source\Local State'), cloned_dir / 'Local State', True),
            (Path(r'C:\source\Default\Preferences'), cloned_dir / 'Default' / 'Preferences', True),
            (Path(r'C:\source\Default\Secure Preferences'), cloned_dir / 'Default' / 'Secure Preferences', True),
        ]

        with patch('apps.ui_automation.wallet_session.tempfile.gettempdir', return_value=str(runtime_root)), \
             patch('apps.ui_automation.wallet_session.Path.exists', return_value=False), \
             patch('apps.ui_automation.wallet_session.Path.mkdir') as mock_mkdir, \
             patch('apps.ui_automation.wallet_session.build_wallet_profile_copy_plan', return_value=copy_plan), \
             patch('apps.ui_automation.wallet_session.sanitize_wallet_runtime_profile') as mock_sanitize_wallet_runtime_profile, \
             patch('apps.ui_automation.wallet_session.copy_wallet_profile_asset') as mock_copy_wallet_profile_asset:
            result = clone_wallet_profile(
                r'C:\source',
                'Default',
                extension_id,
                session_id=17,
            )

        self.assertEqual(result, str(cloned_dir))
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_copy_wallet_profile_asset.assert_has_calls([call(*item) for item in copy_plan])
        mock_sanitize_wallet_runtime_profile.assert_called_once_with(str(cloned_dir), 'Default')

    def test_sanitize_wallet_runtime_profile_rewrites_crashed_exit_type(self):
        runtime_root = Path(__file__).resolve().parents[3] / 'tmp_wallet_service_runtime'
        shutil.rmtree(runtime_root, ignore_errors=True)
        runtime_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        preferences_path = runtime_root / 'Default' / 'Preferences'
        preferences_path.parent.mkdir(parents=True, exist_ok=True)
        preferences_path.write_text('{"profile":{"exit_type":"Crashed"},"theme":"dark"}', encoding='utf-8')

        sanitize_wallet_runtime_profile(str(runtime_root), 'Default')

        self.assertEqual(
            preferences_path.read_text(encoding='utf-8'),
            '{"profile":{"exit_type":"Normal"},"theme":"dark"}',
        )

    @patch('apps.ui_automation.wallet_session.subprocess.run')
    @patch('apps.ui_automation.wallet_session.shutil.which', return_value=None)
    @patch('apps.ui_automation.wallet_session.os.name', 'nt')
    def test_terminate_existing_chrome_uses_windows_taskkill_fallback_path(
        self,
        mock_which,
        mock_run,
    ):
        with patch.dict('apps.ui_automation.wallet_session.os.environ', {'SystemRoot': r'C:\Windows'}, clear=False):
            terminate_existing_chrome()

        self.assertEqual(mock_run.call_args.args[0][0], r'C:\Windows\System32\taskkill.exe')

    @patch('apps.ui_automation.wallet_session.find_free_debugging_port', return_value=9555)
    @patch('apps.ui_automation.wallet_session.is_debugging_port_in_use', return_value=True)
    def test_resolve_wallet_remote_debugging_port_falls_back_when_port_is_busy(
        self,
        mock_is_debugging_port_in_use,
        mock_find_free_debugging_port,
    ):
        resolved_port = resolve_wallet_remote_debugging_port(9222)

        self.assertEqual(resolved_port, 9555)
        mock_is_debugging_port_in_use.assert_called_once_with(9222)
        mock_find_free_debugging_port.assert_called_once_with()

    @patch('apps.ui_automation.wallet_session.wait_for_cdp_url')
    @patch('apps.ui_automation.wallet_session.subprocess.Popen')
    @patch('apps.ui_automation.wallet_session.clone_wallet_profile')
    @patch('apps.ui_automation.wallet_session.resolve_wallet_remote_debugging_port', return_value=9444)
    def test_launch_chrome_for_wallet_uses_cloned_runtime_profile(
        self,
        mock_resolve_wallet_remote_debugging_port,
        mock_clone_wallet_profile,
        mock_popen,
        mock_wait_for_cdp_url,
    ):
        mock_clone_wallet_profile.return_value = r'D:\wallet-runtime\session-17'
        mock_wait_for_cdp_url.return_value = 'ws://127.0.0.1:9333/devtools/browser/test'
        mock_popen.return_value.pid = 4321

        config = SimpleNamespace(
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9333,
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            launch_mode='runtime_clone',
            force_close_existing_chrome=False,
        )

        launch_result = launch_chrome_for_wallet(config, session_id=17)

        command = mock_popen.call_args.args[0]
        command_line = ' '.join(command)

        self.assertIn(r'--user-data-dir=D:\wallet-runtime\session-17', command_line)
        self.assertNotIn(r'--user-data-dir=C:\Users\tester\AppData\Local\Google\Chrome\User Data', command_line)
        self.assertIn(r'--remote-debugging-port=9444', command_line)
        mock_wait_for_cdp_url.assert_called_once_with(9444)
        mock_resolve_wallet_remote_debugging_port.assert_called_once_with(9333)
        self.assertEqual(launch_result.process_id, 4321)
        self.assertEqual(launch_result.cdp_url, 'ws://127.0.0.1:9333/devtools/browser/test')
        self.assertEqual(launch_result.debugger_address, '127.0.0.1:9444')
        self.assertEqual(launch_result.remote_debugging_port, 9444)
        self.assertEqual(launch_result.runtime_user_data_dir, r'D:\wallet-runtime\session-17')

    @patch('apps.ui_automation.wallet_session.is_default_chrome_user_data_dir', return_value=True, create=True)
    @patch(
        'apps.ui_automation.wallet_session.wait_for_cdp_url',
        side_effect=RuntimeError('Unable to get CDP URL from http://127.0.0.1:9666/json/version'),
    )
    @patch('apps.ui_automation.wallet_session.subprocess.Popen')
    @patch('apps.ui_automation.wallet_session.resolve_wallet_remote_debugging_port', return_value=9666)
    def test_launch_chrome_for_wallet_reports_chrome_default_profile_debugging_restriction(
        self,
        mock_resolve_wallet_remote_debugging_port,
        mock_popen,
        mock_wait_for_cdp_url,
        mock_is_default_chrome_user_data_dir,
    ):
        process = MagicMock()
        process.pid = 2468
        process.poll.return_value = None
        mock_popen.return_value = process

        config = SimpleNamespace(
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\qjy01\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9333,
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            launch_mode='global_profile',
            force_close_existing_chrome=False,
        )

        with self.assertRaisesRegex(RuntimeError, r'Chrome 136\+'):
            launch_chrome_for_wallet(config, session_id=24)

        mock_resolve_wallet_remote_debugging_port.assert_called_once_with(9333)
        process.terminate.assert_called_once_with()
        mock_is_default_chrome_user_data_dir.assert_called_once_with(
            r'C:\Users\qjy01\AppData\Local\Google\Chrome\User Data'
        )

    @patch('apps.ui_automation.wallet_session.wait_for_cdp_url')
    @patch('apps.ui_automation.wallet_session.subprocess.Popen')
    @patch('apps.ui_automation.wallet_session.clone_wallet_profile')
    @patch('apps.ui_automation.wallet_session.resolve_wallet_remote_debugging_port', return_value=9666)
    def test_launch_chrome_for_wallet_uses_global_profile_without_cloning(
        self,
        mock_resolve_wallet_remote_debugging_port,
        mock_clone_wallet_profile,
        mock_popen,
        mock_wait_for_cdp_url,
    ):
        mock_wait_for_cdp_url.return_value = 'ws://127.0.0.1:9666/devtools/browser/test'
        mock_popen.return_value.pid = 9876

        config = SimpleNamespace(
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9333,
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            launch_mode='global_profile',
            force_close_existing_chrome=False,
        )

        launch_result = launch_chrome_for_wallet(config, session_id=23)

        command = mock_popen.call_args.args[0]
        command_line = ' '.join(command)

        self.assertIn(
            r'--user-data-dir=C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            command_line,
        )
        mock_clone_wallet_profile.assert_not_called()
        mock_wait_for_cdp_url.assert_called_once_with(9666)
        mock_resolve_wallet_remote_debugging_port.assert_called_once_with(9333)
        self.assertEqual(launch_result.process_id, 9876)
        self.assertEqual(launch_result.cdp_url, 'ws://127.0.0.1:9666/devtools/browser/test')
        self.assertEqual(launch_result.debugger_address, '127.0.0.1:9666')
        self.assertEqual(launch_result.remote_debugging_port, 9666)
        self.assertEqual(
            launch_result.runtime_user_data_dir,
            r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
        )

    @patch('apps.ui_automation.wallet_session.terminate_wallet_browser_process')
    @patch('apps.ui_automation.wallet_session.tempfile.gettempdir')
    def test_finalize_wallet_session_stops_process_and_cleans_runtime_clone_profile(
        self,
        mock_gettempdir,
        mock_terminate_wallet_browser_process,
    ):
        runtime_root = Path(__file__).resolve().parents[3] / 'tmp_wallet_finalize_runtime'
        shutil.rmtree(runtime_root, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        mock_gettempdir.return_value = str(runtime_root)
        runtime_profile_dir = runtime_root / 'testhub_wallet_profiles' / 'session-33'
        runtime_profile_dir.mkdir(parents=True, exist_ok=True)
        (runtime_profile_dir / 'Preferences').write_text('{}', encoding='utf-8')

        session = SimpleNamespace(
            launch_mode='runtime_clone',
            runtime_user_data_dir=str(runtime_profile_dir),
            process_id=4333,
            status='running',
            error_message='',
            finished_at=None,
            save=MagicMock(),
        )

        finalize_wallet_session(session, 'passed')

        self.assertEqual(session.status, 'passed')
        self.assertFalse(runtime_profile_dir.exists())
        mock_terminate_wallet_browser_process.assert_called_once_with(4333)
        session.save.assert_called_once()
