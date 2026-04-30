import logging

logger = logging.getLogger('django')

import os

# 禁用 browser-use 遥测
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import asyncio
import functools
import json
import re
from types import SimpleNamespace
from urllib.parse import urlsplit
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .planned_task_state import (
    ACTIVE_TASK_STATUSES,
    get_next_active_task as get_next_planned_task,
    sync_planned_task_status,
)

# 加载环境变量
load_dotenv()

TASK_STATUS_ACTIONS = {'mark_task_complete', 'mark_task_failed', 'mark_task_skipped'}
METAMASK_UNLOCK_PASSWORD_SELECTOR = '[data-testid="unlock-password"]'
METAMASK_UNLOCK_SUBMIT_SELECTOR = '[data-testid="unlock-submit"]'
METAMASK_CONNECT_CONFIRM_SELECTOR = '[data-testid="confirm-btn"]'
METAMASK_FOOTER_CONFIRM_SELECTOR = '[data-testid="confirm-footer-button"]'
METAMASK_UNLOCK_TEXT_BUTTONS = ['Unlock', '解锁', '登录']
METAMASK_CONNECT_TEXT_BUTTONS = ['Connect', '连接', '下一步', 'Next']
METAMASK_CONFIRM_TEXT_BUTTONS = ['Confirm', '确认', 'Approve', '签名', '切换网络', 'Switch network', 'Send']
BOOTSTRAP_PLACEHOLDER_TAB_URLS = {
    'chrome://newtab-footer',
    'chrome://newtab-footer/',
    'chrome://newtab',
    'chrome://newtab/',
    'chrome://new-tab-page',
    'chrome://new-tab-page/',
    'edge://newtab',
    'edge://newtab/',
}
WALLET_TARGET_CHAIN_PRESETS = (
    {
        'aliases': {
            'bnb smart chain testnet',
            'bnb chain testnet',
            'bsc testnet',
            'binance smart chain testnet',
            '0x61',
            '97',
        },
        'chain_id': '0x61',
        'chain_name': 'BNB Smart Chain Testnet',
        'native_currency': {
            'name': 'tBNB',
            'symbol': 'tBNB',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
            'https://data-seed-prebsc-2-s1.bnbchain.org:8545',
        ],
        'block_explorer_urls': [
            'https://testnet.bscscan.com',
        ],
    },
    {
        'aliases': {
            'bnb smart chain',
            'bnb chain',
            'bsc',
            'binance smart chain',
            '0x38',
            '56',
        },
        'chain_id': '0x38',
        'chain_name': 'BNB Smart Chain',
        'native_currency': {
            'name': 'BNB',
            'symbol': 'BNB',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://bsc-dataseed.bnbchain.org',
        ],
        'block_explorer_urls': [
            'https://bscscan.com',
        ],
    },
    {
        'aliases': {
            'ethereum',
            'ethereum mainnet',
            'mainnet',
            '0x1',
            '1',
        },
        'chain_id': '0x1',
        'chain_name': 'Ethereum Mainnet',
        'native_currency': {
            'name': 'Ether',
            'symbol': 'ETH',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://cloudflare-eth.com',
        ],
        'block_explorer_urls': [
            'https://etherscan.io',
        ],
    },
    {
        'aliases': {
            'sepolia',
            'ethereum sepolia',
            'sepolia testnet',
            '0xaa36a7',
            '11155111',
        },
        'chain_id': '0xaa36a7',
        'chain_name': 'Sepolia',
        'native_currency': {
            'name': 'Sepolia Ether',
            'symbol': 'ETH',
            'decimals': 18,
        },
        'rpc_urls': [
            'https://rpc.sepolia.org',
        ],
        'block_explorer_urls': [
            'https://sepolia.etherscan.io',
        ],
    },
)
TRADE_TASK_MARKERS = (
    'swap',
    'trade',
    'buy',
    'sell',
    'exchange',
    'launchpad',
    '发射台',
    '兑换',
    '换币',
    '买入',
    '卖出',
    '购买',
    '出售',
)
BUSINESS_BLOCKER_SIGNAL_RULES = (
    {
        'code': 'price_impact_too_high',
        'message': '当前交易报价价格影响过高，站点已阻止继续执行',
        'keywords': (
            'price impact too high',
            '价格影响过高',
        ),
    },
    {
        'code': 'routing_timeout',
        'message': '当前交易报价路由超时，页面未返回可执行报价',
        'keywords': (
            'routing timeout',
            '路由超时',
        ),
    },
    {
        'code': 'insufficient_liquidity',
        'message': '当前币对流动性不足或没有可执行路由',
        'keywords': (
            'insufficient liquidity',
            '流动性不足',
            'no route found',
            '无法找到路由',
            '无可用路由',
        ),
    },
)

PATCHED_NAVIGATE_HANDLER_NAME = 'on_patched_NavigateToUrlEvent'

Agent = None
Controller = None
BrowserProfile = None
CloseTabEvent = None
SwitchTabEvent = None
BrowserSession = None
BROWSER_USE_IMPORT_ERROR = None
_ORIGINAL_BROWSER_USE_EXTRACT_START_URL = None


def _is_browser_use_permission_error(exc):
    error_text = str(exc or '')
    return (
        isinstance(exc, PermissionError)
        or '[WinError 5]' in error_text
        or '.config\\browseruse' in error_text
        or '.config/browseruse' in error_text
    )


def _log_browser_use_patch_issue(message, exc, default_level='error'):
    if _is_browser_use_permission_error(exc):
        logger.warning(
            f"{message} skipped because browser-use runtime is unavailable in this environment: {exc}"
        )
        return

    log_fn = logger.warning if default_level == 'warning' else logger.error
    log_fn(f"{message}: {exc}")


def is_bootstrap_placeholder_tab_url(url):
    normalized = str(url or '').strip().lower()
    return normalized in BOOTSTRAP_PLACEHOLDER_TAB_URLS


def build_wallet_mode_rules(wallet_provider, target_chain):
    provider_label = str(wallet_provider or 'metamask')
    chain_label = str(target_chain or 'unspecified')
    return (
        "\nWALLET MODE RULES:\n"
        f"- This run uses a real Chrome profile with {provider_label} already installed.\n"
        f"- Target chain: {chain_label}.\n"
        "- Handle wallet tasks in this order when the dApp triggers them: connect wallet, switch chain, sign message, confirm transaction.\n"
        "- Interact with the dApp first. Some dApps show a generic 'Connect Wallet' entrypoint before the provider list appears. Click that first, then wait for the provider picker.\n"
        "- Wait for the provider picker after clicking 'Connect Wallet'. Do not assume the MetaMask option is visible immediately.\n"
        "- If meaningful text or controls are visible, treat the dApp page as loaded. Do not keep waiting or call done just because the layout changed.\n"
        "- If the dApp page looks correct but the body stays empty, skeleton-only, or otherwise half-loaded, recover by returning focus to a fresh foreground tab and retry the current dApp step once before failing.\n"
        "- When a MetaMask popup/tab opens, switch to it and finish the approval before returning to the dApp.\n"
        "- browser-use cannot reliably inspect chrome-extension pages in this environment. Use the dedicated MetaMask actions instead of generic clicks inside the extension.\n"
        "- If MetaMask opens an unlock page (#/unlock or home.html#unlock), call metamask_unlock with the provided password before any wallet approval step.\n"
        "- If MetaMask opens a connect, signature, chain switch, or transaction confirmation page, call metamask_confirm to press the primary approval button.\n"
        "- If the dApp must run on the configured target chain, call metamask_ensure_target_chain after the dApp page is visible instead of manually hunting MetaMask network controls.\n"
        "- If the current MetaMask state is unclear, call metamask_inspect before failing.\n"
        "- NEVER skip, fake, or silently bypass wallet approval steps.\n"
        "- NEVER fall back to blind generic clicking inside MetaMask before the popup/tab is clearly visible.\n"
        "- If MetaMask does not appear after the dApp action, stop and mark the current wallet-related sub-task as failed.\n"
    )


def sanitize_task_text_for_browser_url_extraction(task):
    sanitized_task = str(task or '')
    if not sanitized_task:
        return sanitized_task

    # browser-use will treat bare tokens like `home.html#unlock` as a domain and
    # auto-navigate to `https://home.html`. Neutralize those wallet-internal route
    # hints without touching real URLs such as https://example.com/index.html.
    return re.sub(
        r'(?<![\w/:.-])(?P<name>home|notification|popup|background|offscreen|index)\.html(?=(?:[#?)]|\s|$))',
        lambda match: f"{match.group('name')} html",
        sanitized_task,
        flags=re.IGNORECASE,
    )


def _fallback_extract_start_url_from_task(task):
    task_text = str(task or '')
    if not task_text:
        return None

    task_without_emails = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', task_text)
    patterns = [
        r'https?://[^\s<>"\']+',
        r'(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}(?:/[^\s<>"\']*)?',
    ]
    excluded_words = {'never', 'dont', 'not', "don't"}
    found_urls = []

    for pattern in patterns:
        matches = re.finditer(pattern, task_without_emails)
        for match in matches:
            url = re.sub(r'[.,;:!?()\[\]]+$', '', match.group(0))
            context_start = max(0, match.start() - 20)
            context_text = task_without_emails[context_start:match.start()]
            if any(word.lower() in context_text.lower() for word in excluded_words):
                continue
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            found_urls.append(url)

    unique_urls = list(set(found_urls))
    if len(unique_urls) == 1:
        return unique_urls[0]
    return None


def extract_browser_use_start_url_from_task(task, extractor=None, logger_obj=None):
    sanitized_task = sanitize_task_text_for_browser_url_extraction(task)
    extractor_fn = extractor or _ORIGINAL_BROWSER_USE_EXTRACT_START_URL
    if extractor_fn is None:
        return _fallback_extract_start_url_from_task(sanitized_task)

    proxy_self = SimpleNamespace(logger=logger_obj or logger)
    return extractor_fn(proxy_self, sanitized_task)


def _normalize_wallet_chain_alias(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return ''
    return re.sub(r'\s+', ' ', normalized)


def _normalize_wallet_chain_id(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return ''
    if normalized.startswith('0x'):
        return normalized
    try:
        return hex(int(normalized))
    except (TypeError, ValueError):
        return normalized


def _normalize_wallet_task_text(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _task_requires_wallet_connection(task_description):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            'connect wallet',
            '连接钱包',
            '连接 metamask',
            '连接 meta mask',
            '连接 meta-mask',
            '使用 metamask 连接',
            'use metamask',
        )
    )


def _task_requires_target_chain(task_description, target_chain_config=None):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False

    has_chain_intent = any(
        marker in normalized
        for marker in ('switch chain', 'target chain', 'network', 'chain', '切链', '切换网络', '目标链', '网络')
    )
    if not has_chain_intent:
        return False

    if not target_chain_config:
        return True

    aliases = {
        _normalize_wallet_chain_alias(target_chain_config.get('chain_name')),
        _normalize_wallet_chain_alias(target_chain_config.get('chain_id')),
    }
    for alias in target_chain_config.get('aliases', []) or []:
        aliases.add(_normalize_wallet_chain_alias(alias))
    aliases.discard('')
    return any(alias in normalized for alias in aliases)


def _task_has_trade_intent(task_description):
    normalized = _normalize_wallet_task_text(task_description)
    if not normalized:
        return False
    return any(marker in normalized for marker in TRADE_TASK_MARKERS)


def validate_wallet_task_completion_state(task_description, wallet_context, ethereum_state):
    normalized_task = _normalize_wallet_task_text(task_description)
    if not normalized_task or not (wallet_context or {}).get('enabled'):
        return

    runtime_state = dict(ethereum_state or {})
    has_provider = bool(runtime_state.get('has_provider'))
    current_chain_id = _normalize_wallet_chain_id(runtime_state.get('chain_id'))
    selected_address = str(runtime_state.get('selected_address') or '').strip()

    if _task_requires_wallet_connection(task_description):
        if not has_provider:
            raise RuntimeError('Cannot mark wallet connection task complete before window.ethereum is available')
        if not selected_address:
            raise RuntimeError('Cannot mark wallet connection task complete before the dApp exposes a connected wallet address')

    target_chain_config = resolve_wallet_target_chain_config(wallet_context)
    if target_chain_config and _task_requires_target_chain(task_description, target_chain_config):
        target_chain_id = _normalize_wallet_chain_id(target_chain_config.get('chain_id'))
        if current_chain_id != target_chain_id:
            raise RuntimeError(
                f"Cannot mark target-chain task complete before wallet chain is {target_chain_id}; current chain is {current_chain_id or 'unknown'}"
            )


def detect_business_blocker_signal(text):
    normalized = _normalize_wallet_task_text(text)
    if not normalized:
        return None

    for rule in BUSINESS_BLOCKER_SIGNAL_RULES:
        matched_keyword = next(
            (keyword for keyword in rule.get('keywords', ()) if keyword in normalized),
            None,
        )
        if matched_keyword:
            return {
                'code': rule['code'],
                'message': rule['message'],
                'matched_text': matched_keyword,
            }
    return None


async def detect_business_blocker_for_active_task(
    browser_session,
    task_description,
    target_id=None,
    body_text_fetcher=None,
    tabs=None,
):
    if not _task_has_trade_intent(task_description):
        return None

    current_target_id = target_id or getattr(browser_session, 'agent_focus_target_id', None)
    if not current_target_id:
        return None

    current_url = _get_browser_session_target_url(browser_session, current_target_id, tabs=tabs)
    split_result = urlsplit(str(current_url or '').strip())
    if split_result.scheme.lower() not in {'http', 'https'} or not split_result.netloc:
        return None

    fetch_body_text = body_text_fetcher or _fetch_target_body_text
    current_body_text = str(await fetch_body_text(browser_session, current_target_id) or '').strip()
    if not current_body_text:
        return None

    blocker = detect_business_blocker_signal(current_body_text)
    if not blocker:
        return None

    return {
        **blocker,
        'url': current_url,
        'target_id': current_target_id,
    }


def resolve_wallet_target_chain_config(wallet_context):
    wallet_context = wallet_context or {}
    raw_target_chain = (
        wallet_context.get('wallet_target_chain')
        or wallet_context.get('wallet_target_chain_id')
        or wallet_context.get('target_chain')
        or ''
    )
    normalized_target = _normalize_wallet_chain_alias(raw_target_chain)
    if not normalized_target:
        return None

    for preset in WALLET_TARGET_CHAIN_PRESETS:
        aliases = {_normalize_wallet_chain_alias(alias) for alias in preset.get('aliases', set())}
        if normalized_target in aliases or _normalize_wallet_chain_id(normalized_target) == preset.get('chain_id'):
            chain_config = {
                'chain_id': preset['chain_id'],
                'chain_name': preset['chain_name'],
                'native_currency': dict(preset['native_currency']),
                'rpc_urls': list(preset.get('rpc_urls', [])),
                'block_explorer_urls': list(preset.get('block_explorer_urls', [])),
            }
            chain_config['add_chain_params'] = {
                'chainId': chain_config['chain_id'],
                'chainName': chain_config['chain_name'],
                'nativeCurrency': dict(chain_config['native_currency']),
                'rpcUrls': list(chain_config['rpc_urls']),
                'blockExplorerUrls': list(chain_config['block_explorer_urls']),
            }
            return chain_config

    return None


def _strip_html_text_preview(html, max_chars=240):
    text = re.sub(r'<[^>]+>', ' ', str(html or ''))
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_chars]


def _pick_button_text_selector(html, labels):
    normalized_html = str(html or '')
    normalized_html_lower = normalized_html.lower()
    for label in labels or []:
        if str(label).lower() in normalized_html_lower:
            return f'button:has-text("{label}")'
    return None


def _build_selector_candidates(primary_selector, fallback_selectors):
    ordered = []
    for selector in [primary_selector, *(fallback_selectors or [])]:
        selector = str(selector or '').strip()
        if selector and selector not in ordered:
            ordered.append(selector)
    return ordered


def inspect_metamask_page_html(url, html):
    normalized_url = str(url or '').strip().lower()
    normalized_html = str(html or '')
    normalized_html_lower = normalized_html.lower()

    snapshot = {
        'page_kind': 'unknown',
        'primary_selector': None,
        'password_selector': None,
        'primary_selectors': [],
        'password_selectors': [],
        'text_preview': _strip_html_text_preview(normalized_html),
    }

    has_unlock_testid = (
        'data-testid="unlock-password"' in normalized_html
        or 'data-testid="unlock-submit"' in normalized_html
    )
    has_unlock_fallback = (
        normalized_url.endswith('#/unlock')
        or normalized_url.endswith('home.html#unlock')
        or (
            'type="password"' in normalized_html_lower
            and any(token in normalized_html_lower for token in ('unlock', 'password', '密码', '解锁'))
        )
    )
    if has_unlock_testid or has_unlock_fallback:
        snapshot['page_kind'] = 'unlock'
        snapshot['password_selector'] = (
            METAMASK_UNLOCK_PASSWORD_SELECTOR
            if 'data-testid="unlock-password"' in normalized_html
            else 'input[type="password"]'
        )
        snapshot['primary_selector'] = (
            METAMASK_UNLOCK_SUBMIT_SELECTOR
            if 'data-testid="unlock-submit"' in normalized_html
            else _pick_button_text_selector(normalized_html, METAMASK_UNLOCK_TEXT_BUTTONS)
            or 'button[type="submit"]'
        )
        snapshot['password_selectors'] = _build_selector_candidates(
            snapshot['password_selector'],
            ['input[type="password"]'],
        )
        snapshot['primary_selectors'] = _build_selector_candidates(
            snapshot['primary_selector'],
            ['button[type="submit"]'],
        )
        return snapshot

    has_confirm_testid = 'data-testid="confirm-footer-button"' in normalized_html
    has_confirm_fallback = (
        'signature-request' in normalized_url
        or 'confirm-transaction' in normalized_url
        or any(
            marker in normalized_html_lower
            for marker in (
                'signature request',
                'confirm transaction',
                'switch network',
                'approve',
                '确认',
                '签名',
                '切换网络',
            )
        )
    )
    if has_confirm_testid or has_confirm_fallback:
        snapshot['page_kind'] = 'confirm'
        snapshot['primary_selector'] = (
            METAMASK_FOOTER_CONFIRM_SELECTOR
            if has_confirm_testid
            else _pick_button_text_selector(normalized_html, METAMASK_CONFIRM_TEXT_BUTTONS)
            or 'button[type="submit"]'
        )
        snapshot['primary_selectors'] = _build_selector_candidates(
            snapshot['primary_selector'],
            ['button[type="submit"]'],
        )
        return snapshot

    has_connect_testid = 'data-testid="confirm-btn"' in normalized_html
    has_connect_fallback = (
        '/connect/' in normalized_url
        or any(
            marker in normalized_html_lower
            for marker in ('connect request', 'connect wallet', '连接钱包', '连接此网站')
        )
    )
    if has_connect_testid or has_connect_fallback:
        snapshot['page_kind'] = 'connect'
        snapshot['primary_selector'] = (
            METAMASK_CONNECT_CONFIRM_SELECTOR
            if has_connect_testid
            else _pick_button_text_selector(normalized_html, METAMASK_CONNECT_TEXT_BUTTONS)
            or 'button[type="submit"]'
        )
        snapshot['primary_selectors'] = _build_selector_candidates(
            snapshot['primary_selector'],
            ['button[type="submit"]'],
        )
        return snapshot

    return snapshot


async def _wait_for_first_visible_locator(page, selectors, timeout=1200):
    for selector in selectors or []:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state='visible', timeout=timeout)
            return locator, selector
        except Exception:
            continue
    return None, None


async def _fill_first_available_locator(page, selectors, value):
    locator, matched_selector = await _wait_for_first_visible_locator(page, selectors, timeout=1500)
    if locator is None:
        raise RuntimeError(f'Unable to find an actionable MetaMask input from selectors: {selectors}')
    await locator.fill(str(value))
    return matched_selector


async def _click_first_available_locator(page, selectors):
    locator, matched_selector = await _wait_for_first_visible_locator(page, selectors, timeout=1500)
    if locator is None:
        raise RuntimeError(f'Unable to find an actionable MetaMask button from selectors: {selectors}')
    await locator.click()
    return matched_selector


async def _selectors_still_visible(page, selectors):
    for selector in selectors or []:
        locator = page.locator(selector).first
        try:
            if await locator.count():
                if await locator.is_visible():
                    return True
        except Exception:
            continue
    return False


async def _wait_for_metamask_page_transition(page, previous_url, selectors):
    for _ in range(8):
        if page.is_closed():
            return

        current_url = str(getattr(page, 'url', '') or '')
        if current_url != previous_url:
            return

        if not await _selectors_still_visible(page, selectors):
            return

        await page.wait_for_timeout(250)


async def _collect_metamask_snapshots(browser, extension_id):
    snapshots = []
    extension_prefix = f'chrome-extension://{extension_id}/'
    for context in browser.contexts:
        for page in context.pages:
            page_url = str(getattr(page, 'url', '') or '')
            if not page_url.startswith(extension_prefix):
                continue

            try:
                page_html = await page.content()
            except Exception:
                page_html = ''

            snapshot = inspect_metamask_page_html(page_url, page_html)
            snapshot['url'] = page_url
            snapshot['page'] = page
            snapshots.append(snapshot)
    return snapshots


async def _ensure_metamask_home_page(browser, extension_id):
    if not browser.contexts:
        return False

    target_url = f'chrome-extension://{extension_id}/home.html'
    context = next((item for item in browser.contexts if item.pages), browser.contexts[0])
    page = None
    try:
        page = await context.new_page()
        await page.goto(target_url, wait_until='domcontentloaded')
        await page.wait_for_timeout(800)
        return True
    except Exception:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        return False


def _is_metamask_provider_selection_step(step):
    text = str(step or '').strip().lower()
    return any(
        marker in text
        for marker in (
            '选择metamask',
            'metamask作为登录方式',
            'metamask 作为登录方式',
            'select metamask',
        )
    )


def _is_metamask_unlock_step(step):
    text = str(step or '').strip().lower()
    return '密码' in text or '解锁' in text or 'unlock' in text


def _is_metamask_blocking_auth_step(step):
    text = str(step or '').strip().lower()
    if not any(marker in text for marker in ('metamask', '钱包', 'wallet')):
        return False
    return any(
        marker in text
        for marker in (
            '授权',
            '连接',
            '绑定',
            '签名',
            'sign',
            'switch chain',
            '切链',
            '切换网络',
            'transaction',
            '交易',
            'confirm',
        )
    ) and not _is_metamask_provider_selection_step(step)


def reorder_wallet_planned_steps(steps, wallet_provider=''):
    normalized_steps = list(steps or [])
    provider_label = str(wallet_provider or '').strip().lower()
    if provider_label and provider_label != 'metamask':
        return normalized_steps
    if not any('metamask' in str(step).lower() for step in normalized_steps):
        return normalized_steps

    unlock_index = next((i for i, step in enumerate(normalized_steps) if _is_metamask_unlock_step(step)), None)
    blocking_index = next((i for i, step in enumerate(normalized_steps) if _is_metamask_blocking_auth_step(step)), None)

    if unlock_index is None or blocking_index is None or unlock_index < blocking_index:
        return normalized_steps

    insert_index = blocking_index
    for i, step in enumerate(normalized_steps[:blocking_index]):
        if _is_metamask_provider_selection_step(step):
            insert_index = i + 1

    reordered_steps = list(normalized_steps)
    unlock_step = reordered_steps.pop(unlock_index)
    reordered_steps.insert(insert_index, unlock_step)
    return reordered_steps


def build_wallet_debugger_http_url(wallet_context):
    debugger_address = str((wallet_context or {}).get('debugger_address') or '').strip()
    if debugger_address:
        return f'http://{debugger_address}'

    cdp_url = str((wallet_context or {}).get('cdp_url') or '').strip()
    if cdp_url.startswith('ws://') and '/devtools/' in cdp_url:
        return f"http://{cdp_url[5:].split('/devtools/', 1)[0]}"
    if cdp_url.startswith('http://'):
        return cdp_url
    return ''


class MetaMaskWalletController:
    def __init__(self, wallet_context, playwright_factory=None):
        self.wallet_context = wallet_context or {}
        self._wallet_controller = None
        self.playwright_factory = playwright_factory
        self.debugger_http_url = build_wallet_debugger_http_url(self.wallet_context)
        self.extension_id = str(self.wallet_context.get('metamask_extension_id') or '').strip()
        self.target_chain_config = resolve_wallet_target_chain_config(self.wallet_context)
        self._playwright_runtime = None
        self._browser = None

    async def connect(self):
        if self._browser is not None:
            return self._browser

        if not self.debugger_http_url:
            raise RuntimeError('MetaMask action requires an active wallet debugger address')
        if not self.extension_id:
            raise RuntimeError('MetaMask action requires a detected MetaMask extension id')

        runtime_factory = self.playwright_factory
        if runtime_factory is None:
            from playwright.async_api import async_playwright

            runtime_factory = async_playwright

        runtime_candidate = runtime_factory()
        if hasattr(runtime_candidate, 'start'):
            self._playwright_runtime = await runtime_candidate.start()
        else:
            self._playwright_runtime = runtime_candidate

        self._browser = await self._playwright_runtime.chromium.connect_over_cdp(self.debugger_http_url)
        return self._browser

    async def close(self):
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright_runtime is not None and hasattr(self._playwright_runtime, 'stop'):
            try:
                await self._playwright_runtime.stop()
            except Exception:
                pass
            self._playwright_runtime = None

    async def collect_snapshots(self):
        browser = await self.connect()
        snapshots = await _collect_metamask_snapshots(browser, self.extension_id)
        if not snapshots:
            await _ensure_metamask_home_page(browser, self.extension_id)
            snapshots = await _collect_metamask_snapshots(browser, self.extension_id)
        return snapshots

    async def inspect_pages(self):
        payload = [
            {
                'page_kind': snapshot.get('page_kind'),
                'url': snapshot.get('url'),
                'text_preview': snapshot.get('text_preview'),
                'primary_selector': snapshot.get('primary_selector'),
            }
            for snapshot in await self.collect_snapshots()
        ]
        return json.dumps({'pages': payload}, ensure_ascii=False)

    async def probe(self):
        try:
            snapshots = await self.collect_snapshots()
        except Exception as exc:
            return {
                'cdp_connected': False,
                'extension_pages_visible': False,
                'pages': [],
                'supported': False,
                'unsupported_reason': str(exc),
            }

        pages = [
            {
                'page_kind': snapshot.get('page_kind'),
                'url': snapshot.get('url'),
                'text_preview': snapshot.get('text_preview'),
                'primary_selector': snapshot.get('primary_selector'),
            }
            for snapshot in snapshots
        ]
        extension_pages_visible = bool(pages)
        return {
            'cdp_connected': True,
            'extension_pages_visible': extension_pages_visible,
            'pages': pages,
            'supported': extension_pages_visible,
            'unsupported_reason': (
                ''
                if extension_pages_visible
                else 'MetaMask extension pages are not visible via CDP. Only Chrome + MetaMask full-page mode is supported.'
            ),
        }

    async def _find_wallet_capable_dapp_page(self):
        browser = await self.connect()
        candidates = []
        for context in browser.contexts:
            for page in context.pages:
                page_url = str(getattr(page, 'url', '') or '').strip().lower()
                if page_url.startswith('http://') or page_url.startswith('https://'):
                    candidates.append(page)
        return candidates[-1] if candidates else None

    async def _read_ethereum_state(self, page):
        state = await page.evaluate(
            """
            () => {
              const ethereum = window.ethereum;
              return {
                has_provider: !!ethereum,
                chain_id: ethereum?.chainId ?? null,
                selected_address: ethereum?.selectedAddress ?? null,
                is_metamask: !!ethereum?.isMetaMask,
                href: window.location?.href ?? null,
              };
            }
            """
        )
        return state or {}

    async def read_dapp_runtime_state(self):
        page = await self._find_wallet_capable_dapp_page()
        if page is None:
            return {
                'has_provider': False,
                'chain_id': None,
                'selected_address': None,
                'href': None,
            }

        bring_to_front = getattr(page, 'bring_to_front', None)
        if callable(bring_to_front):
            await bring_to_front()

        state = await self._read_ethereum_state(page)
        state = dict(state or {})
        state.setdefault('href', str(getattr(page, 'url', '') or ''))
        return state

    async def _request_switch_chain(self, page, chain_id):
        return await self._dispatch_wallet_request(
            page,
            result_slot='__testhubSwitchChainResult',
            method='wallet_switchEthereumChain',
            params=[{'chainId': chain_id}],
        )

    async def _request_add_chain(self, page, chain_config):
        return await self._dispatch_wallet_request(
            page,
            result_slot='__testhubAddChainResult',
            method='wallet_addEthereumChain',
            params=[dict((chain_config or {}).get('add_chain_params') or {})],
        )

    async def _dispatch_wallet_request(self, page, result_slot, method, params):
        await page.evaluate(
            """
            ({ resultSlot, method, params }) => {
              const ethereum = window.ethereum;
              if (!ethereum) {
                window[resultSlot] = {
                  status: 'rejected',
                  ok: false,
                  code: -1,
                  message: 'window.ethereum is unavailable',
                  chainId: null,
                };
                return window[resultSlot];
              }

              window[resultSlot] = {
                status: 'pending',
                ok: false,
                pending: true,
                chainId: ethereum?.chainId ?? null,
              };

              ethereum.request({ method, params })
                .then((result) => {
                  window[resultSlot] = {
                    status: 'fulfilled',
                    ok: true,
                    result: result ?? null,
                    chainId: window.ethereum?.chainId ?? null,
                  };
                })
                .catch((error) => {
                  window[resultSlot] = {
                    status: 'rejected',
                    ok: false,
                    code: error?.code ?? null,
                    message: error?.message ?? String(error),
                    chainId: window.ethereum?.chainId ?? null,
                  };
                });

              return window[resultSlot];
            }
            """,
            {
                'resultSlot': result_slot,
                'method': method,
                'params': list(params or []),
            },
        )
        return await self._read_wallet_request_result(page, result_slot)

    async def _read_wallet_request_result(self, page, result_slot, attempts=8, delay_ms=250):
        last_result = {}
        for _ in range(attempts):
            last_result = await page.evaluate(
                """
                ({ resultSlot }) => {
                  return window[resultSlot] || {
                    status: 'missing',
                    ok: false,
                    pending: false,
                    message: 'wallet request result is missing',
                    chainId: window.ethereum?.chainId ?? null,
                  };
                }
                """,
                {'resultSlot': result_slot},
            )
            if last_result.get('status') != 'pending':
                break
            wait_for_timeout = getattr(page, 'wait_for_timeout', None)
            if callable(wait_for_timeout):
                await wait_for_timeout(delay_ms)
            else:
                await asyncio.sleep(delay_ms / 1000)

        if last_result.get('status') == 'pending':
            last_result = dict(last_result)
            last_result['pending'] = True
            last_result['message'] = 'wallet request is still pending'
        return last_result

    async def _wait_for_target_chain(self, page, chain_id, attempts=10, delay_ms=800):
        last_state = {}
        for _ in range(attempts):
            last_state = await self._read_ethereum_state(page)
            if _normalize_wallet_chain_id(last_state.get('chain_id')) == _normalize_wallet_chain_id(chain_id):
                return last_state
            wait_for_timeout = getattr(page, 'wait_for_timeout', None)
            if callable(wait_for_timeout):
                await wait_for_timeout(delay_ms)
            else:
                await asyncio.sleep(delay_ms / 1000)
        return last_state

    async def _confirm_pending_chain_prompt(self, attempts=2, wait_for_page_attempts=4, delay_ms=800):
        confirmations = []
        for _ in range(attempts):
            confirmed = False
            for _ in range(wait_for_page_attempts):
                try:
                    confirmations.append(await self.confirm())
                    confirmed = True
                    break
                except RuntimeError as exc:
                    if 'No actionable MetaMask confirmation page is available' not in str(exc):
                        raise
                    await asyncio.sleep(delay_ms / 1000)
            if not confirmed:
                break
        return confirmations

    async def ensure_target_chain(self):
        target_chain_config = self.target_chain_config
        if target_chain_config is None:
            return {
                'status': 'skipped',
                'reason': 'No recognized wallet target chain is configured',
            }

        page = await self._find_wallet_capable_dapp_page()
        if page is None:
            return {
                'status': 'pending',
                'reason': 'No wallet-capable dApp page is available yet',
                'target_chain': target_chain_config['chain_name'],
            }

        bring_to_front = getattr(page, 'bring_to_front', None)
        if callable(bring_to_front):
            await bring_to_front()

        current_state = await self._read_ethereum_state(page)
        if not current_state.get('has_provider'):
            return {
                'status': 'pending',
                'reason': 'The current dApp page does not expose window.ethereum yet',
                'target_chain': target_chain_config['chain_name'],
                'page_url': current_state.get('href') or str(getattr(page, 'url', '') or ''),
            }

        current_chain_id = _normalize_wallet_chain_id(current_state.get('chain_id'))
        target_chain_id = _normalize_wallet_chain_id(target_chain_config['chain_id'])
        if current_chain_id == target_chain_id:
            return {
                'status': 'already_on_target',
                'chain_id': current_chain_id,
                'target_chain': target_chain_config['chain_name'],
                'page_url': current_state.get('href') or str(getattr(page, 'url', '') or ''),
            }

        switch_result = await self._request_switch_chain(page, target_chain_id)
        confirmations = []
        add_result = None

        if switch_result.get('code') == 4902:
            add_result = await self._request_add_chain(page, target_chain_config)
            confirmations.extend(await self._confirm_pending_chain_prompt())
        elif switch_result.get('pending') or switch_result.get('code') == -32002 or switch_result.get('ok'):
            confirmations.extend(await self._confirm_pending_chain_prompt())

        final_wait_attempts = 16 if switch_result.get('code') == 4902 else 10
        final_state = await self._wait_for_target_chain(page, target_chain_id, attempts=final_wait_attempts)
        final_chain_id = _normalize_wallet_chain_id(final_state.get('chain_id'))
        if final_chain_id != target_chain_id and switch_result.get('code') == 4902:
            second_switch_result = await self._request_switch_chain(page, target_chain_id)
            if second_switch_result.get('pending') or second_switch_result.get('ok') or second_switch_result.get('code') == -32002:
                confirmations.extend(await self._confirm_pending_chain_prompt())
                final_state = await self._wait_for_target_chain(page, target_chain_id)
                final_chain_id = _normalize_wallet_chain_id(final_state.get('chain_id'))

        if final_chain_id != target_chain_id:
            latest_page = await self._find_wallet_capable_dapp_page()
            if latest_page is not None:
                page = latest_page
                final_state = await self._wait_for_target_chain(page, target_chain_id, attempts=8, delay_ms=1000)
                final_chain_id = _normalize_wallet_chain_id(final_state.get('chain_id'))

        if final_chain_id == target_chain_id:
            return {
                'status': 'switched',
                'chain_id': final_chain_id,
                'target_chain': target_chain_config['chain_name'],
                'page_url': final_state.get('href') or str(getattr(page, 'url', '') or ''),
                'confirmations': confirmations,
            }

        error_message = (
            (switch_result or {}).get('message')
            or (add_result or {}).get('message')
            or f'Wallet chain stayed on {current_chain_id or "unknown"} instead of {target_chain_id}'
        )
        return {
            'status': 'failed',
            'reason': error_message,
            'chain_id': final_chain_id or current_chain_id,
            'target_chain': target_chain_config['chain_name'],
            'page_url': final_state.get('href') or current_state.get('href') or str(getattr(page, 'url', '') or ''),
        }

    async def unlock(self, password):
        if not str(password or '').strip():
            raise RuntimeError('MetaMask unlock requires a non-empty password')

        snapshots = await self.collect_snapshots()
        snapshot = select_metamask_snapshot(snapshots, {'unlock'})
        if snapshot is None:
            raise RuntimeError('No actionable MetaMask unlock page is available')

        page = snapshot['page']
        previous_url = str(getattr(page, 'url', '') or '')
        await page.bring_to_front()
        await _fill_first_available_locator(
            page,
            snapshot.get('password_selectors') or [snapshot.get('password_selector')],
            password,
        )
        await _click_first_available_locator(
            page,
            snapshot.get('primary_selectors') or [snapshot.get('primary_selector')],
        )
        await _wait_for_metamask_page_transition(
            page,
            previous_url,
            snapshot.get('primary_selectors') or [snapshot.get('primary_selector')],
        )
        return f"Unlocked MetaMask on {snapshot['url']}"

    async def confirm(self):
        snapshots = await self.collect_snapshots()
        snapshot = select_metamask_snapshot(snapshots, {'connect', 'confirm'})
        if snapshot is None:
            raise RuntimeError('No actionable MetaMask confirmation page is available')

        page = snapshot['page']
        previous_url = str(getattr(page, 'url', '') or '')
        await page.bring_to_front()
        await _click_first_available_locator(
            page,
            snapshot.get('primary_selectors') or [snapshot.get('primary_selector')],
        )
        try:
            await _wait_for_metamask_page_transition(
                page,
                previous_url,
                snapshot.get('primary_selectors') or [snapshot.get('primary_selector')],
            )
        except Exception as exc:
            error_text = str(exc)
            if 'Target page, context or browser has been closed' not in error_text:
                raise
        return f"Confirmed MetaMask {snapshot['page_kind']} page on {snapshot['url']}"


async def _with_metamask_pages(wallet_context, callback, wallet_controller=None):
    owns_controller = wallet_controller is None
    controller = wallet_controller or MetaMaskWalletController(wallet_context)
    try:
        snapshots = await controller.collect_snapshots()
        return await callback(snapshots)
    finally:
        if owns_controller:
            await controller.close()


def select_metamask_snapshot(snapshots, allowed_kinds):
    allowed = set(allowed_kinds or [])
    for snapshot in reversed(list(snapshots or [])):
        if snapshot.get('page_kind') in allowed:
            return snapshot
    return None


async def inspect_metamask_pages_action(wallet_context, wallet_controller=None):
    if wallet_controller is not None:
        return await wallet_controller.inspect_pages()

    async def _callback(snapshots):
        payload = [
            {
                'page_kind': snapshot.get('page_kind'),
                'url': snapshot.get('url'),
                'text_preview': snapshot.get('text_preview'),
                'primary_selector': snapshot.get('primary_selector'),
            }
            for snapshot in snapshots
        ]
        return json.dumps({'pages': payload}, ensure_ascii=False)

    return await _with_metamask_pages(wallet_context, _callback)


async def probe_metamask_wallet_runtime(wallet_context, wallet_controller=None):
    if wallet_controller is not None:
        return await wallet_controller.probe()

    controller = MetaMaskWalletController(wallet_context)
    try:
        return await controller.probe()
    finally:
        await controller.close()


async def perform_metamask_unlock_action(wallet_context, password, wallet_controller=None):
    if wallet_controller is not None:
        return await wallet_controller.unlock(password)
    controller = MetaMaskWalletController(wallet_context)
    try:
        return await controller.unlock(password)
    finally:
        await controller.close()


async def perform_metamask_confirm_action(wallet_context, wallet_controller=None):
    if wallet_controller is not None:
        return await wallet_controller.confirm()
    controller = MetaMaskWalletController(wallet_context)
    try:
        return await controller.confirm()
    finally:
        await controller.close()


async def perform_metamask_ensure_target_chain_action(wallet_context, wallet_controller=None):
    if wallet_controller is not None:
        return await wallet_controller.ensure_target_chain()
    controller = MetaMaskWalletController(wallet_context)
    try:
        return await controller.ensure_target_chain()
    finally:
        await controller.close()


async def activate_browser_session_focus_target(browser_session):
    focus_target_id = getattr(browser_session, 'agent_focus_target_id', None)
    event_bus = getattr(browser_session, 'event_bus', None)
    if not focus_target_id or event_bus is None:
        return False

    from browser_use.browser.events import SwitchTabEvent

    await event_bus.dispatch(SwitchTabEvent(target_id=focus_target_id))
    return True


async def reload_browser_session_focus_target(browser_session):
    focus_target_id = getattr(browser_session, 'agent_focus_target_id', None)
    if not focus_target_id:
        return False

    cdp_session = await browser_session.get_or_create_cdp_session(target_id=focus_target_id, focus=False)
    await cdp_session.cdp_client.send.Page.reload(
        params={'ignoreCache': False},
        session_id=cdp_session.session_id,
    )
    return True


async def stabilize_browser_session_initial_focus(browser_session):
    """
    browser-use may attach focus to Chrome's internal new tab footer page on Windows.
    That page is a poor starting point for CDP navigation, especially for wallet sessions.
    Prefer an existing about:blank page or create one before the agent begins navigation.
    """
    focus_target_id = getattr(browser_session, 'agent_focus_target_id', None)
    session_manager = getattr(browser_session, 'session_manager', None)
    if not focus_target_id or session_manager is None:
        return False

    current_target = session_manager.get_target(focus_target_id)
    current_url = getattr(current_target, 'url', '')
    if not is_bootstrap_placeholder_tab_url(current_url):
        return False

    from browser_use.browser.events import SwitchTabEvent, TabCreatedEvent

    tabs = await browser_session.get_tabs()
    blank_tab = next(
        (
            tab
            for tab in tabs
            if getattr(tab, 'target_id', None) != focus_target_id
            and str(getattr(tab, 'url', '')).strip().lower() == 'about:blank'
        ),
        None,
    )
    if blank_tab is not None:
        browser_session.agent_focus_target_id = blank_tab.target_id
        await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=blank_tab.target_id))
        return True

    cdp_client_root = getattr(browser_session, '_cdp_client_root', None)
    if cdp_client_root is None:
        return False

    new_target = await cdp_client_root.send.Target.createTarget(params={'url': 'about:blank'})
    new_target_id = new_target['targetId']
    browser_session.agent_focus_target_id = new_target_id
    await browser_session.event_bus.dispatch(TabCreatedEvent(target_id=new_target_id, url='about:blank'))
    await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=new_target_id))
    return True


def _get_browser_session_target_url(browser_session, target_id, tabs=None):
    if not target_id:
        return ''

    if tabs:
        for tab in tabs:
            if getattr(tab, 'target_id', None) == target_id:
                return str(getattr(tab, 'url', '') or '').strip()

    session_manager = getattr(browser_session, 'session_manager', None)
    if session_manager is None:
        return ''

    try:
        target = session_manager.get_target(target_id)
    except Exception:
        target = None

    return str(getattr(target, 'url', '') or '').strip()


async def _fetch_target_body_text(browser_session, target_id):
    cdp_session = await browser_session.get_or_create_cdp_session(target_id=target_id, focus=False)
    result = await cdp_session.cdp_client.send.Runtime.evaluate(
        params={
            'expression': """
                (() => {
                    const bodyText = (document.body && (document.body.innerText || document.body.textContent || '')) || '';
                    const rootText = (document.documentElement && (document.documentElement.innerText || document.documentElement.textContent || '')) || '';
                    return (bodyText || rootText || '').trim();
                })()
            """,
            'returnByValue': True,
            'awaitPromise': True,
        },
        session_id=cdp_session.session_id,
    )
    return str(result.get('result', {}).get('value', '') or '').strip()


def _normalize_wallet_recovery_url(url):
    normalized_url = str(url or '').strip()
    if not normalized_url:
        return ''

    split_result = urlsplit(normalized_url)
    if split_result.scheme.lower() not in {'http', 'https'} or not split_result.netloc:
        return ''

    normalized_path = split_result.path.rstrip('/') or '/'
    return f"{split_result.scheme.lower()}://{split_result.netloc.lower()}{normalized_path}"


def _body_text_has_wallet_picker(text):
    normalized_text = ' '.join(str(text or '').strip().lower().split())
    if not normalized_text:
        return False

    strong_markers = (
        'metamask supports multiple ecosystems',
        'select which chain(s) to connect to',
        '选择要连接的链',
    )
    if any(marker in normalized_text for marker in strong_markers):
        return True

    marker_hits = 0
    for marker in (
        'connect wallet',
        'select chain',
        'top wallets',
        'previously used',
        '连接钱包',
        '选择链',
        '请选择',
        'evm',
        'solana',
    ):
        if marker in normalized_text:
            marker_hits += 1
    return marker_hits >= 4 and 'metamask' in normalized_text


async def recover_empty_wallet_dapp_tab(browser_session, body_text_fetcher=None):
    """
    Some wallet dApps render into a broken foreground tab where the URL is correct but
    the page body is empty, or remain stuck on a stale wallet-picker overlay after
    the real connected dApp content is already available in a sibling tab. Prefer a
    healthier sibling tab for the same site/path, otherwise open a fresh foreground
    tab for the same dApp URL when the current page is actually empty.
    """
    focus_target_id = getattr(browser_session, 'agent_focus_target_id', None)
    event_bus = getattr(browser_session, 'event_bus', None)
    if not focus_target_id or event_bus is None:
        return False

    tabs = await browser_session.get_tabs()
    current_url = _get_browser_session_target_url(browser_session, focus_target_id, tabs=tabs)
    normalized_recovery_url = _normalize_wallet_recovery_url(current_url)
    if not normalized_recovery_url:
        return False

    fetch_body_text = body_text_fetcher or _fetch_target_body_text
    current_body_text = str(await fetch_body_text(browser_session, focus_target_id) or '').strip()
    current_page_stuck_on_wallet_picker = _body_text_has_wallet_picker(current_body_text)
    if current_body_text and not current_page_stuck_on_wallet_picker:
        return False

    from browser_use.browser.events import SwitchTabEvent, TabCreatedEvent

    best_candidate_target_id = None
    best_candidate_score = -1
    for tab in tabs:
        candidate_target_id = getattr(tab, 'target_id', None)
        candidate_url = str(getattr(tab, 'url', '') or '').strip()
        if (
            candidate_target_id == focus_target_id
            or _normalize_wallet_recovery_url(candidate_url) != normalized_recovery_url
        ):
            continue
        candidate_body_text = str(await fetch_body_text(browser_session, candidate_target_id) or '').strip()
        if not candidate_body_text:
            continue
        candidate_stuck_on_wallet_picker = _body_text_has_wallet_picker(candidate_body_text)
        if current_page_stuck_on_wallet_picker and candidate_stuck_on_wallet_picker:
            continue

        candidate_score = 0
        if not candidate_stuck_on_wallet_picker:
            candidate_score += 10
        if candidate_url == current_url:
            candidate_score += 2
        if len(candidate_body_text) > len(current_body_text):
            candidate_score += 1
        if candidate_score > best_candidate_score:
            best_candidate_score = candidate_score
            best_candidate_target_id = candidate_target_id

    if best_candidate_target_id is not None:
        browser_session.agent_focus_target_id = best_candidate_target_id
        await event_bus.dispatch(SwitchTabEvent(target_id=best_candidate_target_id))
        return True

    if current_page_stuck_on_wallet_picker:
        return False

    cdp_client_root = getattr(browser_session, '_cdp_client_root', None)
    if cdp_client_root is None:
        return False

    new_target = await cdp_client_root.send.Target.createTarget(params={'url': current_url})
    new_target_id = new_target['targetId']
    browser_session.agent_focus_target_id = new_target_id
    await event_bus.dispatch(TabCreatedEvent(target_id=new_target_id, url=current_url))
    await event_bus.dispatch(SwitchTabEvent(target_id=new_target_id))
    return True


def should_open_url_in_new_target(current_url, target_url, new_tab=False):
    normalized_target_url = str(target_url or '').strip().lower()
    if new_tab or not normalized_target_url.startswith(('http://', 'https://')):
        return False

    normalized_current_url = str(current_url or '').strip().lower()
    return (
        not normalized_current_url
        or normalized_current_url == 'about:blank'
        or is_bootstrap_placeholder_tab_url(normalized_current_url)
        or normalized_current_url.startswith('chrome://newtab')
        or normalized_current_url.startswith('edge://newtab')
    )


def should_fallback_navigation_with_new_target(exc, target_url):
    normalized_target_url = str(target_url or '').strip().lower()
    if not normalized_target_url.startswith(('http://', 'https://')):
        return False

    error_text = str(exc or '')
    return 'ERR_INVALID_ARGUMENT' in error_text


async def navigate_browser_session_via_new_target(browser_session, url):
    event_bus = getattr(browser_session, 'event_bus', None)
    cdp_client_root = getattr(browser_session, '_cdp_client_root', None)
    if event_bus is None or cdp_client_root is None:
        raise RuntimeError('Browser session cannot create a direct navigation target')

    from browser_use.browser.events import SwitchTabEvent, TabCreatedEvent

    target_url = str(url or '').strip()
    new_target = await cdp_client_root.send.Target.createTarget(params={'url': target_url})
    new_target_id = new_target['targetId']

    await event_bus.dispatch(TabCreatedEvent(target_id=new_target_id, url=target_url))

    get_or_create_cdp_session = getattr(browser_session, 'get_or_create_cdp_session', None)
    if callable(get_or_create_cdp_session):
        await get_or_create_cdp_session(target_id=new_target_id, focus=False)

    resolved_target_id = new_target_id
    get_tabs = getattr(browser_session, 'get_tabs', None)
    if callable(get_tabs):
        for _ in range(5):
            await asyncio.sleep(0.2)
            tabs = await get_tabs()
            matching_tabs = [
                tab for tab in tabs
                if str(getattr(tab, 'url', '') or '').strip() == target_url
            ]
            if matching_tabs:
                matching_target = next(
                    (tab for tab in matching_tabs if getattr(tab, 'target_id', None) == new_target_id),
                    matching_tabs[-1],
                )
                resolved_target_id = getattr(matching_target, 'target_id', new_target_id) or new_target_id
                break

    browser_session.agent_focus_target_id = resolved_target_id
    await event_bus.dispatch(SwitchTabEvent(target_id=resolved_target_id))
    await asyncio.sleep(0.5)
    return resolved_target_id


def _normalize_action_params(action_name, action_params):
    """Normalize common LLM-generated action parameter variants to browser-use schema."""
    if isinstance(action_params, int):
        if action_name in TASK_STATUS_ACTIONS:
            return {'task_id': action_params}
        return {'index': action_params}

    if action_name == 'switch_tab' and isinstance(action_params, str) and not isinstance(action_params, dict):
        return {'tab_id': action_params}

    if not isinstance(action_params, dict):
        return action_params

    normalized_params = {}
    for key, value in action_params.items():
        normalized_key = key
        if key in {'element_index', 'element_id', 'node_id', 'id'} and action_name not in TASK_STATUS_ACTIONS:
            normalized_key = 'index'
        elif key in {'tab', 'target', 'target_id'} and action_name in {'switch_tab', 'switch'}:
            normalized_key = 'tab_id'
        elif key in {'content', 'value'} and action_name in {'input', 'input_text'}:
            normalized_key = 'text'
        normalized_params[normalized_key] = value
    return normalized_params


def _is_terminal_status_action(action_name, action_params):
    if action_name in TASK_STATUS_ACTIONS:
        return True
    if action_name != 'update_task_status' or not isinstance(action_params, dict):
        return False
    return str(action_params.get('status', '')).strip().lower() in {'completed', 'failed', 'skipped'}


def _enforce_single_task_step(actions):
    """
    Enforce single-task-per-step:
    once a terminal task status action appears, discard any later business actions.
    """
    if not isinstance(actions, list):
        return actions

    trimmed_actions = []
    terminal_seen = False
    dropped_count = 0

    for action in actions:
        if not isinstance(action, dict):
            trimmed_actions.append(action)
            continue

        if terminal_seen:
            dropped_count += 1
            continue

        trimmed_actions.append(action)
        for action_name, action_params in action.items():
            if _is_terminal_status_action(action_name, action_params):
                terminal_seen = True
                break
            if action_name == 'done':
                terminal_seen = True
                break

    if dropped_count:
        logger.warning(
            f"⚠️ Enforced single-task step boundary: dropped {dropped_count} action(s) after terminal status update"
        )

    return trimmed_actions


def _get_task_status_action_task_id(action):
    if not isinstance(action, dict):
        return None

    for action_name, action_params in action.items():
        if action_name in TASK_STATUS_ACTIONS and isinstance(action_params, dict):
            return action_params.get('task_id')
        if action_name == 'update_task_status' and isinstance(action_params, dict):
            status = str(action_params.get('status', '')).strip().lower()
            if status in {'completed', 'failed', 'skipped'}:
                return action_params.get('task_id')
    return None


def _has_real_business_action(action):
    if not isinstance(action, dict):
        return False
    return any(
        action_name not in {'mark_task_complete', 'mark_task_failed', 'mark_task_skipped', 'update_task_status', 'done'}
        for action_name in action.keys()
    )


def _extract_task_literals(task_description):
    if not task_description:
        return []

    text = str(task_description)
    literals = []
    literals.extend(re.findall(r'「([^」]+)」', text))
    literals.extend(re.findall(r'"([^"\n]+)"', text))
    literals.extend(re.findall(r"'([^'\n]+)'", text))
    literals.extend(re.findall(r'https?://[^\s]+', text))
    literals.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text))

    deduped = []
    for item in literals:
        cleaned = str(item).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _action_matches_pending_task(action, pending_task_description):
    if not isinstance(action, dict):
        return False

    literals = _extract_task_literals(pending_task_description)
    if not literals:
        return False

    action_payload = json.dumps(action, ensure_ascii=False)
    return any(literal in action_payload for literal in literals)


def _enforce_pending_status_settlement(actions, pending_task_id, pending_task_description=None):
    """
    If the previous step executed a task but forgot to mark it, the next step must settle
    that pending task status first and must not start the following business task in the same step.
    """
    if not pending_task_id or not isinstance(actions, list):
        return actions

    marked_pending_task = any(
        str(_get_task_status_action_task_id(action)) == str(pending_task_id)
        for action in actions
    )
    has_real_action = any(_has_real_business_action(action) for action in actions)

    if not (marked_pending_task and has_real_action):
        return actions

    real_actions = [action for action in actions if _has_real_business_action(action)]
    if pending_task_description and any(
        _action_matches_pending_task(action, pending_task_description)
        for action in real_actions
    ):
        return actions

    settled_actions = [
        action for action in actions
        if str(_get_task_status_action_task_id(action)) == str(pending_task_id)
    ]

    if settled_actions:
        logger.warning(
            f"⚠️ Settling pending task {pending_task_id} first: dropped business actions from the same step"
        )
        return settled_actions

    return actions


def _contains_auth_failure_signal(text):
    if not text:
        return False

    normalized = str(text).lower()
    keywords = [
        '登录失败', 'login failed', 'invalid credentials', 'incorrect password',
        '用户名或密码', '账号或密码', 'authentication failed', 'auth failed',
        'bad credentials', 'unauthorized', '401', '403'
    ]
    return any(keyword in normalized for keyword in keywords)

# ============================================================================
# PART 1: Common Patches (Pydantic, ActionModel, TokenCost, Basic Connection)
# ============================================================================

# Patch ChatOpenAI to allow setting attributes (required for browser-use token counting)
try:
    from pydantic import ConfigDict

    if hasattr(ChatOpenAI, 'model_config'):
        if isinstance(ChatOpenAI.model_config, dict):
            ChatOpenAI.model_config['extra'] = 'allow'
        else:
            ChatOpenAI.model_config = ConfigDict(extra='allow', arbitrary_types_allowed=True)
    else:
        ChatOpenAI.model_config = ConfigDict(extra='allow', arbitrary_types_allowed=True)
except ImportError:
    if hasattr(ChatOpenAI, 'model_config'):
        ChatOpenAI.model_config['extra'] = 'allow'

# 修改 ActionModel 配置以允许额外字段
try:
    from browser_use.tools.registry.views import ActionModel
    from pydantic import ConfigDict

    ActionModel.model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')
    logger.info("✅ Modified ActionModel.model_config to allow extra fields")
except Exception as e:
    _log_browser_use_patch_issue("Failed to modify ActionModel config", e, default_level='warning')

# Patch Agent.get_model_output 方法
try:
    from browser_use.agent.service import Agent
    from browser_use.agent.message_manager.service import AgentOutput
    import json as json_module

    _ORIGINAL_BROWSER_USE_EXTRACT_START_URL = Agent._extract_start_url
    _original_get_model_output = Agent.get_model_output


    def _patched_extract_start_url(self, task):
        return extract_browser_use_start_url_from_task(
            task,
            extractor=_ORIGINAL_BROWSER_USE_EXTRACT_START_URL,
            logger_obj=getattr(self, 'logger', logger),
        )


    async def _patched_get_model_output(self, input_messages):
        """修补后的 get_model_output，直接从 response.content 解析 JSON"""
        # logger.info("🔧 _patched_get_model_output called")

        if hasattr(self, '_task_was_done') and self._task_was_done:
            logger.info("🔧 Task was marked as done, stopping LLM interaction")
            raise KeyboardInterrupt("Task finished")

        kwargs = {'output_format': self.AgentOutput}

        # Add retry logic for LLM invocation with timeout
        max_retries = 2  # 重试次数为2次
        last_exception = None
        response = None
        for attempt in range(max_retries):
            try:
                # 添加超时控制，设置为60秒（支持硅基流动等大模型API的响应时间）
                response = await asyncio.wait_for(
                    self.llm.ainvoke(input_messages, **kwargs),
                    timeout=60.0  # 超时时间60秒
                )
                break
            except asyncio.TimeoutError as te:
                last_exception = te
                logger.warning(f"⚠️ LLM invocation timed out (attempt {attempt + 1}/{max_retries}): {te}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)  # 重试间隔0.5秒
            except Exception as e:
                last_exception = e
                logger.warning(f"⚠️ LLM invocation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)  # 重试间隔0.5秒
        else:
            logger.error(f"❌ LLM invocation failed after {max_retries} attempts.")
            raise last_exception

        # 检查响应是否为空或无效
        if not response or not hasattr(response, 'content'):
            error_msg = "LLM returned invalid response (no content attribute)"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        # 检查content是否为空字符串
        content = response.content
        if not content or not isinstance(content, str) or not content.strip():
            error_msg = "LLM returned empty content - possible API error or timeout"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        try:
            if hasattr(response, 'content') and isinstance(response.content, str):
                # 处理带有 <thinking> 标签的响应
                content_text = response.content.strip()
                # 移除开头的 <thinking>...</thinking> 标签块
                import re
                thinking_pattern = r'^<thinking>.*?</thinking>\s*'
                if re.match(thinking_pattern, content_text, re.DOTALL):
                    content_text = re.sub(thinking_pattern, '', content_text, count=1, flags=re.DOTALL)
                    logger.info("🔧 Fixed: removed leading <thinking> block from response")

                content_dict = json_module.loads(content_text)

                # 规范化 action 字典
                if 'action' in content_dict:
                    import re
                    normalized_actions = []
                    for action_dict in content_dict['action']:
                        # 处理字符串格式的 action（如 "mark_task_complete(task_id=8)"）
                        if isinstance(action_dict, str):
                            match = re.match(r'(\w+)\(([^)]*)\)', action_dict.strip())
                            if match:
                                action_name = match.group(1)
                                params_str = match.group(2)
                                # 解析参数
                                if action_name in TASK_STATUS_ACTIONS:
                                    task_id_match = re.search(r'task_id=(\d+)', params_str)
                                    if task_id_match:
                                        normalized_actions.append({action_name: {'task_id': int(task_id_match.group(1))}})
                                        logger.info(f"🔧 Fixed: parsed string action '{action_dict}'")
                                elif action_name == 'update_task_status':
                                    task_id_match = re.search(r'task_id=(\d+)', params_str)
                                    status_match = re.search(r"status=['\"]?(\w+)['\"]?", params_str)
                                    if task_id_match and status_match:
                                        normalized_actions.append({
                                            action_name: {
                                                'task_id': int(task_id_match.group(1)),
                                                'status': status_match.group(1)
                                            }
                                        })
                                        logger.info(f"🔧 Fixed: parsed string action '{action_dict}'")
                                elif action_name == 'done':
                                    normalized_actions.append({'done': {}})
                            continue

                        normalized_action = {}
                        for action_name, action_params in action_dict.items():
                            normalized_value = _normalize_action_params(action_name, action_params)
                            # 忽略无效的字符串参数（如 {"click": "保存"}）
                            if isinstance(normalized_value, str) and action_name not in ['done', 'switch_tab']:
                                logger.warning(f"⚠️ Invalid action format: {action_name}: {normalized_value}, skipping")
                                continue
                            normalized_action[action_name] = normalized_value
                        if normalized_action:  # 只添加非空的 action
                            normalized_actions.append(normalized_action)
                    normalized_actions = _enforce_single_task_step(normalized_actions)
                    pending_task_id = getattr(self, '_pending_status_task_id', None)
                    pending_task_description = getattr(self, '_pending_status_task_description', None)
                    content_dict['action'] = _enforce_pending_status_settlement(
                        normalized_actions,
                        pending_task_id,
                        pending_task_description
                    )

                # 检查 action 数组外部的 mark_task_complete（错误格式）
                # 如果存在，将其添加到 action 数组中
                for action_name in [*TASK_STATUS_ACTIONS, 'update_task_status']:
                    if action_name not in content_dict:
                        continue
                    if 'action' not in content_dict:
                        content_dict['action'] = []
                    if isinstance(content_dict[action_name], dict):
                        content_dict['action'].append({action_name: content_dict[action_name]})
                        logger.info(f"🔧 Fixed: moved {action_name} into action array")
                    elif isinstance(content_dict[action_name], int) and action_name in TASK_STATUS_ACTIONS:
                        task_id = content_dict[action_name]
                        content_dict['action'].append({action_name: {'task_id': task_id}})
                        logger.info(f"🔧 Fixed: converted {action_name}({task_id}) to proper format and added to action array")

                parsed = AgentOutput.model_construct(
                    thinking=content_dict.get('thinking'),
                    evaluation_previous_goal=content_dict.get('evaluation_previous_goal'),
                    memory=content_dict.get('memory'),
                    next_goal=content_dict.get('next_goal'),
                    action=[]
                )

                class _ActionWrapper:
                    def __init__(self, action_dict):
                        self._action_dict = action_dict

                    def model_dump(self, **kwargs):
                        return self._action_dict

                    def get_index(self):
                        for action_params in self._action_dict.values():
                            if isinstance(action_params, dict) and 'index' in action_params:
                                return action_params['index']
                        return None

                action_list = []
                for action_dict in content_dict.get('action', []):
                    action_list.append(_ActionWrapper(action_dict))

                object.__setattr__(parsed, 'action', action_list)

                if len(parsed.action) > self.settings.max_actions_per_step:
                    parsed.action = parsed.action[:self.settings.max_actions_per_step]

                return parsed
        except Exception as e:
            # If our complex normalization fails, fall back to the original method
            logger.warning(f"⚠️ Custom output normalization failed, falling back: {e}")
            return await _original_get_model_output(self, input_messages)


    Agent._extract_start_url = _patched_extract_start_url
    logger.info("✅ Successfully patched Agent._extract_start_url")
    Agent.get_model_output = _patched_get_model_output
    logger.info("✅ Successfully patched Agent.get_model_output")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch Agent.get_model_output", e)

# Patch TokenCost
try:
    from browser_use.tokens.service import TokenCost
    from langchain_core.messages import HumanMessage, SystemMessage as LangChainSystemMessage, AIMessage


    def _patched_register_llm(self, llm):
        """修补后的 register_llm，修复 langchain 兼容性"""
        instance_id = str(id(llm))
        if instance_id in self.registered_llms:
            return llm

        self.registered_llms[instance_id] = llm
        _original_ainvoke = llm.ainvoke
        _token_service = self

        async def _fixed_tracked_ainvoke(messages, output_format=None, **kwargs):
            # Sanitize message contents
            def _content_to_str(content):
                if isinstance(content, str): return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            if 'text' in item:
                                parts.append(str(item['text']))
                            elif 'image' in item or 'image_url' in item:
                                parts.append("[image]")
                        else:
                            parts.append(str(item))
                    return "\n".join(parts)
                if isinstance(content, dict):
                    if 'text' in content: return str(content['text'])
                    if 'content' in content: return str(content['content'])
                    if 'image' in content or 'image_url' in content: return "[image]"
                return str(content)

            def _sanitize_message(msg):
                msg_type_name = type(msg).__name__
                content = getattr(msg, 'content', msg)
                content_str = _content_to_str(content)
                if msg_type_name == 'SystemMessage': return LangChainSystemMessage(content=content_str)
                if msg_type_name in ('HumanMessage', 'UserMessage'): return HumanMessage(content=content_str)
                if msg_type_name == 'AIMessage': return AIMessage(content=content_str)
                if isinstance(msg, (HumanMessage, LangChainSystemMessage, AIMessage)): return type(msg)(
                    content=content_str)
                return HumanMessage(content=str(content_str))

            sanitized_messages = [_sanitize_message(m) for m in messages]

            output_format = kwargs.pop('output_format', None)
            if output_format:
                kwargs['response_format'] = {"type": "json_object"}

            # Add retry logic for LLM invocation
            max_retries = 2  # 重试次数为2次
            last_exception = None
            for attempt in range(max_retries):
                try:
                    result = await _original_ainvoke(sanitized_messages, **kwargs)
                    break
                except Exception as e:
                    last_exception = e
                    if "response_format" in str(e):
                        kwargs.pop('response_format', None)
                        # retry immediately without response_format
                        continue

                    logger.warning(f"⚠️ LLM ainvoke failed (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)  # 等待0.5秒
            else:
                logger.error(f"❌ LLM ainvoke failed after {max_retries} attempts.")
                raise last_exception

            # Enhance response parsing
            import json as json_module
            clean_content = result.content.strip() if hasattr(result, 'content') else str(result).strip()

            # 处理带有 <thinking> 标签的响应
            thinking_pattern = r'^<thinking>.*?</thinking>\s*'
            if re.match(thinking_pattern, clean_content, re.DOTALL):
                clean_content = re.sub(thinking_pattern, '', clean_content, count=1, flags=re.DOTALL)
                logger.info("🔧 Fixed in TokenCost: removed leading <thinking> block from response")

            # Remove Markdown
            if '```' in clean_content:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean_content, re.DOTALL)
                if match:
                    clean_content = match.group(1).strip()
                else:
                    clean_content = re.sub(r'```[a-z]*', '', clean_content).replace('```', '').strip()

            parsed_data = None
            try:
                parsed_data = json_module.loads(clean_content)
            except:
                try:
                    match = re.search(r'(\{.*\})', clean_content, re.DOTALL)
                    if match: parsed_data = json_module.loads(match.group(1))
                except:
                    pass

            # Wrapper classes
            class _ActionWrapper:
                def __init__(self, action_dict):
                    self._dict = {}
                    for k, v in action_dict.items():
                        if isinstance(v, dict):
                            self._dict[k] = _normalize_action_params(k, v)
                        else:
                            self._dict[k] = v
                    for k, v in self._dict.items(): setattr(self, k, v)

                def model_dump(self, **kwargs):
                    return self._dict

                def get_index(self):
                    for v in self._dict.values():
                        if isinstance(v, dict) and 'index' in v: return v['index']
                    return None

            # Construct AgentOutput manually
            agent_output = None
            if parsed_data and 'action' in parsed_data:
                # Normalize actions
                normalized_actions = []
                for action_dict in parsed_data['action']:
                    # 处理字符串格式的 action（如 "mark_task_complete(task_id=8)"）
                    if isinstance(action_dict, str):
                        match = re.match(r'(\w+)\(([^)]*)\)', action_dict.strip())
                        if match:
                            action_name = match.group(1)
                            params_str = match.group(2)
                            # 解析参数
                            if action_name in TASK_STATUS_ACTIONS:
                                task_id_match = re.search(r'task_id=(\d+)', params_str)
                                if task_id_match:
                                    normalized_actions.append({action_name: {'task_id': int(task_id_match.group(1))}})
                                    logger.info(f"🔧 Fixed in TokenCost: parsed string action '{action_dict}'")
                            elif action_name == 'update_task_status':
                                task_id_match = re.search(r'task_id=(\d+)', params_str)
                                status_match = re.search(r"status=['\"]?(\w+)['\"]?", params_str)
                                if task_id_match and status_match:
                                    normalized_actions.append({
                                        action_name: {
                                            'task_id': int(task_id_match.group(1)),
                                            'status': status_match.group(1)
                                        }
                                    })
                                    logger.info(f"🔧 Fixed in TokenCost: parsed string action '{action_dict}'")
                            elif action_name == 'done':
                                normalized_actions.append({'done': {}})
                        continue

                    normalized_action = {}
                    for action_name, action_params in action_dict.items():
                        normalized_value = _normalize_action_params(action_name, action_params)
                        # 忽略无效的字符串参数（如 {"click": "保存"}）
                        if isinstance(normalized_value, str) and action_name not in ['done', 'switch_tab']:
                            logger.warning(f"⚠️ Invalid action format in TokenCost: {action_name}: {normalized_value}, skipping")
                            continue
                        normalized_action[action_name] = normalized_value
                    if normalized_action:  # 只添加非空的 action
                        normalized_actions.append(normalized_action)
                normalized_actions = _enforce_single_task_step(normalized_actions)
                pending_task_id = getattr(llm, '_pending_status_task_id', None)
                pending_task_description = getattr(llm, '_pending_status_task_description', None)
                parsed_data['action'] = _enforce_pending_status_settlement(
                    normalized_actions,
                    pending_task_id,
                    pending_task_description
                )

                # 检查 action 数组外部的 mark_task_complete（错误格式）
                for action_name in [*TASK_STATUS_ACTIONS, 'update_task_status']:
                    if action_name not in parsed_data:
                        continue
                    if isinstance(parsed_data[action_name], dict):
                        parsed_data['action'].append({action_name: parsed_data[action_name]})
                        logger.info(f"🔧 Fixed in TokenCost: moved {action_name} into action array")
                    elif isinstance(parsed_data[action_name], int) and action_name in TASK_STATUS_ACTIONS:
                        task_id = parsed_data[action_name]
                        parsed_data['action'].append({action_name: {'task_id': task_id}})
                        logger.info(f"🔧 Fixed in TokenCost: moved {action_name}(task_id={task_id}) into action array")

                try:
                    from browser_use.agent.message_manager.service import AgentOutput
                    agent_output = AgentOutput.model_construct(
                        thinking=parsed_data.get('thinking'),
                        evaluation_previous_goal=parsed_data.get('evaluation_previous_goal'),
                        memory=parsed_data.get('memory'),
                        next_goal=parsed_data.get('next_goal'),
                        action=[]
                    )
                    action_list = []
                    for action_dict in parsed_data.get('action', []):
                        action_list.append(_ActionWrapper(action_dict))
                    object.__setattr__(agent_output, 'action', action_list)
                except Exception as e:
                    logger.error(f"🔧 Failed to create AgentOutput: {e}")

            class _ResponseWrapper:
                def __init__(self, orig, completion_obj):
                    self._orig = orig
                    self.content = getattr(orig, 'content', '')
                    self.response_metadata = getattr(orig, 'response_metadata', {})
                    self.completion = completion_obj
                    usage = getattr(orig, 'usage', None) or (
                        orig.response_metadata.get('token_usage') if hasattr(orig, 'response_metadata') else None)
                    if not usage: usage = {}
                    # Fix usage
                    usage = dict(usage) if hasattr(usage, '__dict__') else usage
                    usage.setdefault('prompt_tokens', 0)
                    usage.setdefault('completion_tokens', 0)
                    usage.setdefault('total_tokens', 0)
                    self.usage = usage

                def __getattr__(self, name): return getattr(self._orig, name)

            wrapped = _ResponseWrapper(result, agent_output)
            if hasattr(wrapped, 'usage') and wrapped.usage:
                try:
                    _token_service.add_usage(llm.model, wrapped.usage)
                except:
                    pass

            return wrapped

        setattr(llm, 'ainvoke', _fixed_tracked_ainvoke)
        return llm


    TokenCost.register_llm = _patched_register_llm
    logger.info("✅ Successfully patched TokenCost.register_llm")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch TokenCost", e)

# Patch BrowserSession.connect (Windows CDP fix)
try:
    from browser_use.browser.session import BrowserSession
    import httpx

    _original_connect = BrowserSession.connect


    async def _patched_connect(self, cdp_url=None):
        if cdp_url: return await _original_connect(self, cdp_url=cdp_url)

        browser_profile = getattr(self, 'browser_profile', None)
        if hasattr(browser_profile, 'cdp_url') and browser_profile.cdp_url:
            return await _original_connect(self, cdp_url=browser_profile.cdp_url)

        port = 9222
        if hasattr(browser_profile, 'extra_chromium_args'):
            for arg in browser_profile.extra_chromium_args:
                if '--remote-debugging-port=' in str(arg):
                    try:
                        port = int(arg.split('=')[1]); break
                    except:
                        pass
        if hasattr(browser_profile, 'remote_debugging_port'):
            port = browser_profile.remote_debugging_port

        cdp_endpoint = f"http://localhost:{port}/json/version"

        for attempt in range(10): # 增加重试次数
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(cdp_endpoint)
                    if response.status_code == 200 and response.text:
                        version_info = response.json()
                        browser_profile.cdp_url = version_info['webSocketDebuggerUrl']
                        return await _original_connect(self, cdp_url=browser_profile.cdp_url)
            except Exception:
                if attempt < 4: await asyncio.sleep(1.0)

        return await _original_connect(self, cdp_url=cdp_url)


    BrowserSession.connect = _patched_connect
    logger.info("✅ Successfully patched BrowserSession.connect")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch BrowserSession.connect", e)

# Patch BrowserSession.start to avoid landing on Chrome's internal footer tab
try:
    from browser_use.browser.session import BrowserSession

    _original_browser_session_start = BrowserSession.start


    async def _patched_browser_session_start(self, *args, **kwargs):
        result = await _original_browser_session_start(self, *args, **kwargs)
        try:
            focus_stabilized = await stabilize_browser_session_initial_focus(self)
            if focus_stabilized:
                logger.info("✅ Stabilized BrowserSession initial focus onto a usable blank tab")
            focus_activated = await activate_browser_session_focus_target(self)
            if focus_activated:
                logger.info("✅ Activated BrowserSession focus target in the foreground")
        except Exception as exc:
            logger.warning(f"⚠️ Failed to stabilize BrowserSession initial focus: {exc}")
        return result


    BrowserSession.start = _patched_browser_session_start
    logger.info("✅ Successfully patched BrowserSession.start")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch BrowserSession.start", e)

# Patch BrowserSession.on_NavigateToUrlEvent to avoid invalid navigation on placeholder tabs
try:
    from browser_use.browser.events import (
        AgentFocusChangedEvent,
        NavigationCompleteEvent,
        NavigationStartedEvent,
        SwitchTabEvent,
        TabCreatedEvent,
    )
    from browser_use.browser.session import BrowserSession
    from browser_use.utils import is_new_tab_page

    async def on_patched_NavigateToUrlEvent(self, event):
        self.logger.debug(
            f'[patched on_NavigateToUrlEvent] Received NavigateToUrlEvent: '
            f'url={event.url}, new_tab={event.new_tab}'
        )
        if not self.agent_focus_target_id:
            self.logger.warning('Cannot navigate - browser not connected')
            return

        target_id = None
        current_target_id = self.agent_focus_target_id
        current_target = self.session_manager.get_target(current_target_id)
        current_url = str(getattr(current_target, 'url', '') or '').strip()

        if event.new_tab and is_new_tab_page(current_url):
            self.logger.debug(
                f'[patched on_NavigateToUrlEvent] Already on blank tab ({current_url}), reusing'
            )
            event.new_tab = False

        try:
            self.logger.debug(
                f'[patched on_NavigateToUrlEvent] Processing new_tab={event.new_tab}'
            )

            if should_open_url_in_new_target(current_url, event.url, new_tab=event.new_tab):
                self.logger.info(
                    f'[patched on_NavigateToUrlEvent] Opening {event.url} via direct target '
                    f'because current focus is placeholder ({current_url})'
                )
                target_id = await navigate_browser_session_via_new_target(self, event.url)
                await self.event_bus.dispatch(
                    NavigationStartedEvent(target_id=target_id, url=event.url)
                )
            else:
                if event.new_tab:
                    page_targets = self.session_manager.get_all_page_targets()
                    self.logger.debug(
                        f'[patched on_NavigateToUrlEvent] Found {len(page_targets)} existing tabs'
                    )

                    for idx, target in enumerate(page_targets):
                        self.logger.debug(
                            f'[patched on_NavigateToUrlEvent] '
                            f'Tab {idx}: url={target.url}, targetId={target.target_id}'
                        )
                        if target.url == 'about:blank' and target.target_id != current_target_id:
                            target_id = target.target_id
                            self.logger.debug(f'Reusing existing about:blank tab #{target_id[-4:]}')
                            break

                    if not target_id:
                        self.logger.debug(
                            '[patched on_NavigateToUrlEvent] No reusable about:blank tab found, '
                            'creating new tab...'
                        )
                        try:
                            target_id = await self._cdp_create_new_page('about:blank')
                            self.logger.debug(f'Created new tab #{target_id[-4:]}')
                            await self.event_bus.dispatch(
                                TabCreatedEvent(target_id=target_id, url='about:blank')
                            )
                        except Exception as create_error:
                            self.logger.error(
                                '[patched on_NavigateToUrlEvent] Failed to create new tab: '
                                f'{type(create_error).__name__}: {create_error}'
                            )
                            target_id = current_target_id
                            self.logger.warning(
                                '[patched on_NavigateToUrlEvent] Falling back to current tab '
                                f'#{target_id[-4:]}'
                            )
                else:
                    target_id = target_id or current_target_id

                if self.agent_focus_target_id is None or self.agent_focus_target_id != target_id:
                    self.logger.debug(
                        '[patched on_NavigateToUrlEvent] Switching to target tab '
                        f'{target_id[-4:]} '
                        f'(current: {self.agent_focus_target_id[-4:] if self.agent_focus_target_id else "none"})'
                    )
                    await self.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
                else:
                    self.logger.debug(
                        f'[patched on_NavigateToUrlEvent] Already on target tab {target_id[-4:]}, '
                        'skipping SwitchTabEvent'
                    )

                assert self.agent_focus_target_id is not None and self.agent_focus_target_id == target_id, (
                    'Agent focus not updated to new target_id after SwitchTabEvent should have switched to it'
                )

                await self.event_bus.dispatch(
                    NavigationStartedEvent(target_id=target_id, url=event.url)
                )
                await self._navigate_and_wait(event.url, target_id)

            await self._close_extension_options_pages()
            self.logger.debug(
                f'[patched on_NavigateToUrlEvent] Dispatching NavigationCompleteEvent for '
                f'{event.url} (tab #{target_id[-4:]})'
            )
            await self.event_bus.dispatch(
                NavigationCompleteEvent(
                    target_id=target_id,
                    url=event.url,
                    status=None,
                )
            )
            await self.event_bus.dispatch(
                AgentFocusChangedEvent(target_id=target_id, url=event.url)
            )
        except Exception as exc:
            if should_fallback_navigation_with_new_target(exc, event.url):
                self.logger.warning(
                    '[patched on_NavigateToUrlEvent] Retrying navigation via direct target '
                    f'after error: {exc}'
                )
                target_id = await navigate_browser_session_via_new_target(self, event.url)
                await self.event_bus.dispatch(
                    NavigationStartedEvent(target_id=target_id, url=event.url)
                )
                await self._close_extension_options_pages()
                await self.event_bus.dispatch(
                    NavigationCompleteEvent(
                        target_id=target_id,
                        url=event.url,
                        status=None,
                    )
                )
                await self.event_bus.dispatch(
                    AgentFocusChangedEvent(target_id=target_id, url=event.url)
                )
                return

            self.logger.error(f'Navigation failed: {type(exc).__name__}: {exc}')
            if target_id:
                await self.event_bus.dispatch(
                    NavigationCompleteEvent(
                        target_id=target_id,
                        url=event.url,
                        error_message=f'{type(exc).__name__}: {exc}',
                    )
                )
                await self.event_bus.dispatch(
                    AgentFocusChangedEvent(target_id=target_id, url=event.url)
                )
            raise


    on_patched_NavigateToUrlEvent.__name__ = PATCHED_NAVIGATE_HANDLER_NAME


    BrowserSession.on_NavigateToUrlEvent = on_patched_NavigateToUrlEvent
    logger.info("鉁?Successfully patched BrowserSession.on_NavigateToUrlEvent")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch BrowserSession.on_NavigateToUrlEvent", e)

# Patch ClickElementAction parameters
try:
    from browser_use.tools.views import ClickElementAction

    _original_click_init = ClickElementAction.__init__


    def _patched_click_init(self, **kwargs):
        fixed_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, int) and key not in ['index']:
                fixed_kwargs['index'] = value
            else:
                fixed_kwargs[key] = value
        if len(kwargs) == 1:
            key, value = list(kwargs.items())[0]
            if isinstance(value, int) and key != 'index':
                fixed_kwargs = {'index': value}
        try:
            return _original_click_init(self, **fixed_kwargs)
        except TypeError:
            if fixed_kwargs and isinstance(list(fixed_kwargs.values())[0], int):
                return _original_click_init(self, **{'index': list(fixed_kwargs.values())[0]})
            raise


    ClickElementAction.__init__ = _patched_click_init
except Exception:
    pass

# Patch ToolRegistry
try:
    from browser_use.tools.registry.service import Registry as ToolRegistry

    # Force patch Registry class
    _original_execute_action = ToolRegistry.execute_action


    async def _patched_execute_action(self, action_name: str, params: dict, **kwargs):
        # 自动映射 switch_tab -> switch (强制映射)
        if action_name == 'switch_tab':
            logger.info(f"🔧 Force aliasing: switch_tab -> switch")
            action_name = 'switch'

        if isinstance(params, int):
            params = {'index': params}
        elif not isinstance(params, dict) and params is not None:
            # 针对 switch_tab 可能是纯字符串的情况
            if action_name in ['switch_tab', 'switch']:
                params = {'tab_id': params}
            else:
                params = {'value': params} if params else {}

        if isinstance(params, dict):
            normalized_params = _normalize_action_params(action_name, params)
            if normalized_params != params:
                logger.info(f"🔧 Normalized action params for {action_name}: {params} -> {normalized_params}")
            params = normalized_params

        # 针对点击增加延迟，确保 UI 更新 (如弹窗弹出、下拉框展开)
        if action_name in ['click_element', 'click']:
            result = await _original_execute_action(self, action_name, params, **kwargs)
            # 增加延迟到 1.5s，并强制在点击后等待浏览器渲染
            # 尤其是对于 element-plus 等 UI 框架，下拉列表渲染需要时间
            await asyncio.sleep(1.5)
            return result

        return await _original_execute_action(self, action_name, params, **kwargs)


    ToolRegistry.execute_action = _patched_execute_action
    logger.info("✅ Successfully patched ToolRegistry.execute_action with alias support")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch ToolRegistry", e)

# Patch ScreenshotWatchdog GLOBALLY to fix timeouts
try:
    from browser_use.browser.watchdogs.screenshot_watchdog import ScreenshotWatchdog

    _original_on_screenshot_event = ScreenshotWatchdog.on_ScreenshotEvent

    # Check if already patched to avoid double patching
    if not getattr(_original_on_screenshot_event, '_is_patched_global', False):
        async def on_ScreenshotEvent(self, event):
            """
            Patched screenshot event handler with increased timeout and optimized parameters.
            """
            try:
                # Try original method first with strict timeout
                result = await asyncio.wait_for(
                    _original_on_screenshot_event(self, event),
                    timeout=3.0  # Reduced for fail-fast
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(f"DEBUG: Watchdog timeout (3s), trying optimized approach...")
                try:
                    # Get CDP session
                    cdp_session = await self.browser_session.get_or_create_cdp_session(target_id=None)
                    if not cdp_session: raise Exception("Failed to get CDP session")

                    params = {'format': 'png', 'quality': 50, 'from_surface': True, 'capture_beyond_viewport': False}

                    # One quick retry
                    result = await asyncio.wait_for(
                        cdp_session.cdp_client.send.Page.captureScreenshot(params=params,
                                                                           session_id=cdp_session.session_id),
                        timeout=3.0
                    )
                    return result

                except Exception as ex:
                    # In Text Mode especially, we don't want to die on screenshot
                    logger.warning(f"DEBUG: Screenshot failed optimized, returning placeholder: {ex}")
                    import base64
                    # 1x1 transparent pixel
                    placeholder = base64.b64decode(
                        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
                    return {'data': placeholder}
            except Exception as e:
                logger.error(f"DEBUG: Screenshot unexpected error: {e}")
                import base64
                placeholder = base64.b64decode(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
                return {'data': placeholder}


        on_ScreenshotEvent._is_patched_global = True
        ScreenshotWatchdog.on_ScreenshotEvent = on_ScreenshotEvent
        logger.info("✅ Applied Global ScreenshotWatchdog Patch")

    # Patch DOMWatchdog
    from browser_use.browser.watchdogs.dom_watchdog import DOMWatchdog

    _original_capture_clean_screenshot = DOMWatchdog._capture_clean_screenshot

    if not getattr(_original_capture_clean_screenshot, '_is_patched_global', False):
        async def _capture_clean_screenshot(self):
            try:
                # Very short timeout for DOM clean screenshot checks
                return await asyncio.wait_for(_original_capture_clean_screenshot(self), timeout=3.0)
            except Exception as e:
                logger.warning(f"DEBUG: Clean screenshot failed/timed out: {e}, continuing...")
                return None


        _capture_clean_screenshot._is_patched_global = True
        DOMWatchdog._capture_clean_screenshot = _capture_clean_screenshot
        logger.info("✅ Applied Global DOMWatchdog Patch")

except Exception as e:
    _log_browser_use_patch_issue("Failed to apply Global Watchdog patches", e)

# Patch Agent verdict
try:
    from browser_use.agent.service import Agent
    from browser_use.agent.message_manager.service import AgentOutput

    _original_judge_and_log = Agent._judge_and_log


    def _agent_output_getattr(self, name):
        if name == 'verdict':
            if hasattr(self, 'next_goal') and self.next_goal:
                if any(
                    w in str(self.next_goal).lower() for w in ['complete', 'done', 'finished', 'success']): return True
            if hasattr(self, 'evaluation_previous_goal') and self.evaluation_previous_goal:
                if any(w in str(self.evaluation_previous_goal).lower() for w in ['success', 'complete']): return True
            return False
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


    if not hasattr(AgentOutput, '__getattr__'):
        AgentOutput.__getattr__ = _agent_output_getattr


    async def _patched_judge_and_log(self):
        try:
            return await _original_judge_and_log(self)
        except AttributeError as e:
            if 'verdict' in str(e):
                return None
            raise


    Agent._judge_and_log = _patched_judge_and_log
except Exception:
    pass

# Patch LocalBrowserWatchdog._find_free_port to force port 9222 on Linux
try:
    from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog
    import platform

    _original_find_free_port = LocalBrowserWatchdog._find_free_port

    # 创建补丁函数 - 始终作为实例方法（接受 self）
    def _patched_find_free_port(self):
        if platform.system() == 'Linux':
            logger.info("🔧 Force using port 9222 for Linux environment")
            return 9222
        # 尝试调用原始方法，兼容不同签名
        try:
            return _original_find_free_port(self)
        except TypeError:
            # 如果原始方法不接受 self，尝试不带参数调用
            return _original_find_free_port()

    LocalBrowserWatchdog._find_free_port = _patched_find_free_port
    logger.info("✅ Successfully patched LocalBrowserWatchdog._find_free_port")
except Exception as e:
    _log_browser_use_patch_issue("Failed to patch LocalBrowserWatchdog._find_free_port", e)

# ============================================================================
# PART 2: Helper Classes
# ============================================================================

from langchain_core.callbacks import BaseCallbackHandler
from typing import Any


class RawResponseLogger(BaseCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        pass

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        try:
            generation = response.generations[0][0]
            logger.info(f"DEBUG: Raw LLM Response: {generation.text}")
        except:
            pass


# ============================================================================
# PART 3: Base Browser Agent
# ============================================================================

BROWSER_EXECUTION_MODE_ALIASES = {
    'text': 'text',
    'browser_text': 'text',
    'browser-use-text': 'text',
    'browser_use_text': 'text',
    'vision': 'vision',
    'visual': 'vision',
    'browser_vision': 'vision',
    'browser-use-vision': 'vision',
    'browser_use_vision': 'vision',
}

BROWSER_ROLE_BY_EXECUTION_MODE = {
    'text': 'browser_use_text',
    'vision': 'browser_use_vision',
}


def normalize_browser_execution_mode(execution_mode='text'):
    raw_mode = str(execution_mode or 'text').strip().lower()
    return BROWSER_EXECUTION_MODE_ALIASES.get(raw_mode, 'text')


def browser_role_for_execution_mode(execution_mode='text'):
    return BROWSER_ROLE_BY_EXECUTION_MODE[normalize_browser_execution_mode(execution_mode)]


try:
    from browser_use import Agent, Controller
    from browser_use.browser.events import CloseTabEvent, SwitchTabEvent
    from browser_use.browser.profile import BrowserProfile
except Exception as exc:
    BROWSER_USE_IMPORT_ERROR = exc
    _log_browser_use_patch_issue("Failed to import browser-use runtime dependencies", exc)


class BaseBrowserAgent:
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        if Agent is None or Controller is None or BrowserProfile is None:
            raise RuntimeError(
                'browser-use runtime is unavailable in the current environment: '
                f'{BROWSER_USE_IMPORT_ERROR}'
            )
        self.execution_mode = normalize_browser_execution_mode(execution_mode)
        self.wallet_context = wallet_context or {}
        self._wallet_controller = None
        self._wallet_target_chain_ready = not bool(resolve_wallet_target_chain_config(self.wallet_context))
        self._wallet_target_chain_last_status = ''
        self.enable_gif = enable_gif  # GIF录制开关
        self.case_name = case_name or "Adhoc Task"  # 用例名称

        # Load Config from DB
        from apps.requirement_analysis.models import AIModelConfig

        # Select the model config that matches the requested browser mode.
        role_name = browser_role_for_execution_mode(self.execution_mode)
        config_obj = AIModelConfig.objects.filter(role=role_name, is_active=True).first()
        if config_obj is None and self.execution_mode == 'vision':
            config_obj = AIModelConfig.objects.filter(role='browser_use_text', is_active=True).first()
            if config_obj:
                logger.warning(
                    "No active browser_use_vision config found; using active browser_use_text model config for vision mode."
                )

        model_config = {}
        if config_obj:
            model_config = {
                'api_key': config_obj.api_key,
                'base_url': config_obj.base_url,
                'model_name': config_obj.model_name,
                'provider': config_obj.model_type,
                'temperature': config_obj.temperature  # 读取配置的temperature
            }

        self.api_key = model_config.get('api_key') or os.getenv('AUTH_TOKEN')
        self.base_url = model_config.get('base_url') or os.getenv('BASE_URL')
        self.model_name = model_config.get('model_name') or os.getenv('MODEL_NAME')
        self.provider = model_config.get('provider', 'openai')

        if not self.api_key:
            raise ValueError(f"No API Key found for mode: {self.execution_mode}")

        # 智能temperature处理：特殊模型强制使用特定temperature值
        # 格式: {'模型名称关键字': temperature值}
        special_model_temperature_map = {
            'kimi-2.5': 1.0,  # Moonshot AI Kimi 2.5 只支持 temperature=1
            'kimi-k2.5': 1.0,  # Moonshot AI Kimi K2.5 只支持 temperature=1
            'kimi': 1.0,  # 通用Kimi模型匹配（兜底）
            # 未来可以在这里添加其他特殊模型，例如：
            # 'claude-3.5-sonnet': 0.7,
            # 'gpt-4-turbo': 0.0,
        }

        # 确定最终使用的temperature值
        final_temperature = 0.0  # 默认值
        model_name_lower = self.model_name.lower()

        # 1. 优先检查是否是特殊模型
        for model_keyword, temp in special_model_temperature_map.items():
            if model_keyword in model_name_lower:
                final_temperature = temp
                logger.info(f"✅ 检测到特殊模型 '{self.model_name}'，使用强制 temperature={temp}")
                break
        else:
            # 2. 如果不是特殊模型，使用配置中的值
            if 'temperature' in model_config:
                final_temperature = model_config['temperature']
                logger.info(f"📋 使用配置的 temperature={final_temperature}")
            else:
                # 3. 如果配置中没有，使用默认值
                final_temperature = 0.0
                logger.info(f"⚙️ 使用默认 temperature={final_temperature}")

        self.llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=final_temperature,
            callbacks=[RawResponseLogger()]
        )

        # browser-use requirement
        try:
            object.__setattr__(self.llm, 'provider', self.provider)
            object.__setattr__(self.llm, 'model', self.model_name)
        except:
            if not hasattr(self.llm, '__pydantic_extra__') or self.llm.__pydantic_extra__ is None:
                self.llm.__pydantic_extra__ = {}
            self.llm.__pydantic_extra__['provider'] = self.provider
            self.llm.__pydantic_extra__['model'] = self.model_name

    async def _get_wallet_controller(self):
        if not self.wallet_context.get('enabled'):
            raise RuntimeError('Wallet controller requires wallet mode')
        if self._wallet_controller is None:
            self._wallet_controller = MetaMaskWalletController(self.wallet_context)
        await self._wallet_controller.connect()
        return self._wallet_controller

    async def _close_wallet_controller(self):
        if self._wallet_controller is None:
            return
        try:
            await self._wallet_controller.close()
        finally:
            self._wallet_controller = None

    async def _ensure_wallet_target_chain_ready(self, callback=None):
        if self._wallet_target_chain_ready or not self.wallet_context.get('enabled'):
            return None

        wallet_controller = await self._get_wallet_controller()
        result = await wallet_controller.ensure_target_chain()
        status = str((result or {}).get('status') or '')
        if status in {'already_on_target', 'switched'}:
            self._wallet_target_chain_ready = True

        log_message = ''
        if status == 'already_on_target':
            log_message = (
                f"\n[Wallet]\n已确认当前 dApp 网络为目标链 "
                f"{result.get('target_chain')} ({result.get('chain_id')})。\n"
            )
        elif status == 'switched':
            log_message = (
                f"\n[Wallet]\n已切换钱包到目标链 "
                f"{result.get('target_chain')} ({result.get('chain_id')})。\n"
            )
        elif status == 'failed':
            log_message = (
                f"\n[Wallet]\n目标链校验失败：{result.get('reason') or 'unknown error'}\n"
            )

        if log_message and log_message != self._wallet_target_chain_last_status and callback:
            if asyncio.iscoroutinefunction(callback):
                await callback({'type': 'log', 'content': log_message})
            else:
                callback({'type': 'log', 'content': log_message})
            self._wallet_target_chain_last_status = log_message

        return result

    def _format_action(self, action):
        try:
            action_dict = {}
            if hasattr(action, 'model_dump'):
                action_dict = action.model_dump()
            elif hasattr(action, '_action_dict'):
                action_dict = action._action_dict
            elif hasattr(action, '_dict'):
                action_dict = action._dict
            elif isinstance(action, dict):
                action_dict = action
            else:
                return str(action)

            if not action_dict: return "待机"

            descriptions = []
            for name, params in action_dict.items():
                if not params and name not in ['scroll_down', 'scroll_up', 'done']: continue

                if name in ['go_to_url', 'navigate']:
                    url = params.get('url') if isinstance(params, dict) else params
                    descriptions.append(f"访问: {url}")
                elif name in ['click_element', 'click']:
                    index = params.get('index') if isinstance(params, dict) else params
                    descriptions.append(f"点击[{index}]")
                elif name in ['input_text', 'input']:
                    text = params.get('text') if isinstance(params, dict) else None
                    descriptions.append(f"输入: '{text}'")
                elif name == 'switch_tab':
                    index = params.get('index', params)
                    descriptions.append(f"切换标签 {index}")
                elif name == 'open_new_tab':
                    url = params.get('url', params)
                    descriptions.append(f"新标签打开: {url}")
                elif name == 'close_tab':
                    descriptions.append("关闭当前标签页")
                elif name == 'done':
                    descriptions.append("任务完成")
                else:
                    descriptions.append(f"{name}")
            return " | ".join(descriptions)
        except:
            return "执行操作"

    async def _verify_execution_llm(self):
        """在真正启动执行前做一次轻量连通性检查，避免浏览器启动后反复空转失败。"""
        try:
            await asyncio.wait_for(
                self.llm.ainvoke("Reply with OK."),
                timeout=20.0
            )
        except Exception as e:
            raise RuntimeError(f"Execution LLM unavailable: {e}") from e

    def _extract_structured_steps(self, text: str):
        """从原始任务文本中稳定提取步骤，作为 LLM 拆分失败时的兜底。"""
        if not text:
            return []

        normalized_text = str(text).replace('\r\n', '\n').replace('\r', '\n').strip()
        if not normalized_text:
            return []

        # 优先按行解析显式编号步骤
        numbered_line_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)[\.\s、:：-]+(.*)$')
        extracted_steps = []
        plain_lines = []

        for raw_line in normalized_text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            match = numbered_line_pattern.match(line)
            if match:
                desc = match.group(2).strip()
                if desc:
                    extracted_steps.append(desc)
            else:
                plain_lines.append(line)

        if extracted_steps:
            if len(extracted_steps) == 1 and '\n' not in normalized_text:
                split_inline_text = re.sub(
                    r'\s+(?=\d+(?:\.\d+)*[\.\s、:：-]+)',
                    '\n',
                    normalized_text
                )
                if split_inline_text != normalized_text:
                    inline_steps = self._extract_structured_steps(split_inline_text)
                    if len(inline_steps) > 1:
                        return inline_steps
            return extracted_steps

        # 其次解析单行内多个编号步骤，例如：
        # "1.访问xx 2.搜索xx 3.点击xx"
        split_inline_text = re.sub(
            r'\s+(?=\d+(?:\.\d+)*[\.\s、:：-]+)',
            '\n',
            normalized_text
        )
        if split_inline_text != normalized_text:
            inline_steps = self._extract_structured_steps(split_inline_text)
            if inline_steps:
                return inline_steps

        # 最后退化为逐行文本
        return plain_lines or [normalized_text]

    def _normalize_steps(self, raw_steps, fallback_text: str):
        """清洗并展开步骤列表，避免多步被合并成一条。"""
        steps = raw_steps if isinstance(raw_steps, list) else []
        normalized_steps = []

        for step in steps:
            if step is None:
                continue
            desc = str(step).strip()
            if not desc:
                continue

            # 如果单个 step 里仍然包含多行/多编号步骤，继续拆开
            nested_steps = self._extract_structured_steps(desc)
            if nested_steps and not (len(nested_steps) == 1 and nested_steps[0] == desc):
                normalized_steps.extend(nested_steps)
            else:
                normalized_steps.append(desc)

        if not normalized_steps:
            normalized_steps = self._extract_structured_steps(fallback_text)

        cleaned_steps = []
        for desc in normalized_steps:
            current = str(desc).strip()
            while True:
                match = re.match(r'^\s*\d+(?:\.\d+)*[\.\s、:：-]+(.*)', current, re.S)
                if not match:
                    break
                current = match.group(1).strip()
            if current:
                cleaned_steps.append(current)

        return cleaned_steps or [fallback_text.strip()]

    def _compact_steps(self, steps):
        """合并过细的动作级步骤，收敛为核心业务子任务。"""
        if not steps:
            return []

        compacted = []
        i = 0
        total = len(steps)

        while i < total:
            current = str(steps[i]).strip()
            current_lower = current.lower()

            # 合并“打开浏览器 / 输入URL / 回车访问”这一类导航碎步
            if (
                ('浏览器' in current or 'browser' in current_lower or '地址栏' in current)
                and i + 1 < total
            ):
                window = " ".join(str(s).strip() for s in steps[i:i + 3])
                url_match = re.search(r'https?://[^\s]+', window)
                if url_match:
                    compacted.append(f"访问{url_match.group(0)}")
                    i += min(3, total - i)
                    continue

            # 合并“点击搜索框 / 输入关键词 / 点击搜索 / 等待结果”
            search_window = " ".join(str(s).strip() for s in steps[i:i + 4])
            if any(keyword in search_window for keyword in ['搜索框', '关键词', '百度一下', '搜索结果', 'search']):
                query_match = re.search(r"(?:输入搜索关键词[:：]?\s*|搜索)\s*['\"]?([^'\"\n]+?)['\"]?(?:\s|$)", search_window)
                if query_match:
                    query = query_match.group(1).strip()
                    query = re.sub(r'(并执行搜索|按钮或按下回车键|结果列表加载完成)$', '', query).strip()
                    compacted.append(f"搜索{query}")
                    i += min(4, total - i)
                    continue

            # 合并“点击第N条结果 + 新标签查看详情”
            if any(keyword in current for keyword in ['搜索结果', '结果', '标题链接', '查看详情']):
                if any(keyword in current for keyword in ['第二条', '第2条', '详情', '链接']):
                    compacted.append("点击第2条搜索结果查看详情")
                    i += 1
                    continue

            # 合并关闭标签页相关步骤
            if any(keyword in current for keyword in ['关闭', '标签页', '新标签页', 'close tab']):
                compacted.append("关闭该标签页")
                i += 1
                continue

            compacted.append(current)
            i += 1

        # 去重并保持顺序
        deduped = []
        for step in compacted:
            if not deduped or deduped[-1] != step:
                deduped.append(step)
        return deduped

    def _step_complexity_score(self, step: str) -> int:
        """粗略评估单个步骤是否包含多个动作。"""
        text = str(step).strip()
        if not text:
            return 0

        score = 0
        if len(text) >= 24:
            score += 1
        if len(text) >= 48:
            score += 1
        if any(token in text for token in ['并', '然后', '之后', '再', '并且', '同时', '且']):
            score += 1
        if any(token in text for token in ['点击', '输入', '搜索', '选择', '打开', '关闭', '提交', '保存', '查看', '切换']):
            action_hits = sum(text.count(token) for token in ['点击', '输入', '搜索', '选择', '打开', '关闭', '提交', '保存', '查看', '切换'])
            if action_hits >= 2:
                score += 1
        return score

    def _step_has_specific_requirements(self, step: str) -> bool:
        """判断步骤是否包含必须保留的字面值、断言或字段约束。"""
        text = str(step).strip()
        if not text:
            return False

        signals = 0
        if re.search(r'https?://', text):
            signals += 1
        if any(token in text for token in ['「', '」', '"', "'"]):
            signals += 1
        if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text):
            signals += 1
        if re.search(r'\([^)]{2,}\)', text):
            signals += 1
        if any(token in text for token in ['标题为', '返回', '确认页面', '确认', '验证', '校验']):
            signals += 1
        if any(token in text for token in ['输入框', '按钮', '下拉', '单选', '日期', 'Password', 'Text input', 'Dropdown']):
            signals += 1
        return signals >= 2

    def _should_redecompose_explicit_steps(self, steps):
        """判断已编号任务是否复杂到需要模型二次整合。"""
        if not steps:
            return False

        detail_rich_count = sum(1 for step in steps if self._step_has_specific_requirements(step))
        if detail_rich_count >= max(2, len(steps) // 2):
            return False

        if len(steps) >= 10:
            return True

        complex_count = sum(1 for step in steps if self._step_complexity_score(step) >= 2)
        if complex_count >= max(2, len(steps) // 2):
            return True

        very_long_count = sum(1 for step in steps if len(str(step).strip()) >= 40)
        if very_long_count >= max(2, len(steps) // 2):
            return True

        return False

    async def _model_break_down_task(self, task_description: str, mode: str = 'break_down'):
        """调用模型拆分或重整任务步骤。"""
        if mode == 'recompose':
            prompt = (
                "You are given a task that already has numbered steps, but some steps may be too granular or redundant. "
                "Rewrite them into core business steps only. "
                "Rules: keep the original intent and order, merge mechanical browser operations into the surrounding business step, "
                "do not invent new goals, do not split into micro-actions like clicking an input box or waiting for page load. "
                "Preserve every concrete literal requirement from the original steps, including URLs, field labels, option values, dates, expected titles, "
                "expected result text, and quoted content. Do not replace them with vague phrases like '输入文本信息' or '验证成功'. "
                "Return JSON list of concise Chinese strings only.\n\n"
                f"Task:\n{task_description}"
            )
        else:
            prompt = (
                "Break down this task into core business steps only. "
                "Avoid micro-actions like opening the browser, clicking into an input box, or waiting for results unless they are the user's explicit goal. "
                "Preserve every concrete literal requirement from the original task, including URLs, field labels, option values, dates, expected titles, "
                "expected result text, and quoted content. Do not replace them with vague summaries like '输入文本信息' or '验证成功'. "
                "Keep the order and return JSON list of concise Chinese strings only.\n\n"
                f"Task:\n{task_description}"
            )

        response = await self.llm.ainvoke(prompt)
        content = response.content.strip() if hasattr(response, 'content') else str(response)

        steps = []
        try:
            import json
            match = re.search(r'(\[.*\])', content, re.DOTALL)
            if match:
                steps = json.loads(match.group(1))
        except Exception:
            pass

        return steps

    def _finalize_steps(self, steps, fallback_text: str):
        """统一收口步骤列表，保证输出可执行且尽量精简。"""
        finalized_steps = self._compact_steps(self._normalize_steps(steps, fallback_text))
        if self.wallet_context.get('enabled'):
            finalized_steps = reorder_wallet_planned_steps(
                finalized_steps,
                wallet_provider=self.wallet_context.get('wallet_provider', ''),
            )
        return finalized_steps

    async def analyze_task(self, task_description: str):
        try:
            explicit_steps = self._extract_structured_steps(task_description)
            if len(explicit_steps) >= 2:
                if self._should_redecompose_explicit_steps(explicit_steps):
                    steps = await self._model_break_down_task(task_description, mode='recompose')
                    cleaned_steps = self._finalize_steps(steps, task_description)
                else:
                    cleaned_steps = self._normalize_steps(explicit_steps, task_description)
                    if self.wallet_context.get('enabled'):
                        cleaned_steps = reorder_wallet_planned_steps(
                            cleaned_steps,
                            wallet_provider=self.wallet_context.get('wallet_provider', ''),
                        )
                return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]

            steps = await self._model_break_down_task(task_description, mode='break_down')
            cleaned_steps = self._finalize_steps(steps, task_description)

            return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]
        except Exception as e:
            logger.warning(f"⚠️ analyze_task fallback triggered: {e}")
            cleaned_steps = self._finalize_steps([], task_description)
            return [{'id': i + 1, 'description': s, 'status': 'pending'} for i, s in enumerate(cleaned_steps)]

    def _cleanup_zombie_chrome(self):
        """Clean up any existing Chrome processes on port 9222 (Linux only)"""
        import platform
        import psutil

        if platform.system() != 'Linux':
            return

        logger.info("🧹 Cleaning up zombie Chrome processes...")
        cleaned_count = 0
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check for chrome/chromium
                    if proc.info['name'] and ('chrome' in proc.info['name'] or 'chromium' in proc.info['name']):
                        # Check command line for port 9222
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any('9222' in str(arg) for arg in cmdline):
                            logger.info(f"Killing zombie chrome pid={proc.pid}")
                            proc.kill()
                            cleaned_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup zombie chrome: {e}")

        if cleaned_count > 0:
            logger.info(f"✅ Cleaned up {cleaned_count} zombie Chrome processes")

    def _create_browser_profile(self):
        # Default implementation, can be overridden
        chrome_path = None
        import platform

        system = platform.system()
        if self.wallet_context.get('enabled') and self.wallet_context.get('cdp_url'):
            return BrowserProfile(
                headless=False,
                disable_security=True,
                cdp_url=self.wallet_context['cdp_url'],
                profile_directory=self.wallet_context.get('profile_directory', 'Default'),
                wait_for_network_idle_page_load_time=0.2,
                minimum_wait_page_load_time=0.05,
                wait_between_actions=0.1,
                enable_default_extensions=True
            )

        if system == 'Windows':
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
            ]
            for p in paths:
                if os.path.exists(p):
                    chrome_path = p
                    break
        elif system == 'Linux':
            # Linux 系统常见的 Chrome 路径 - 优先使用我们预装的浏览器
            paths = [
                # 优先使用Docker容器中预装的Chromium
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/usr/bin/google-chrome',
                # 检查Playwright安装的浏览器
                '/ms-playwright/chromium-*/chromium-linux/chromium',
                '/root/.cache/ms-playwright/chromium-*/chromium-linux/chromium',
                # 备用路径
                '/usr/bin/google-chrome-stable',
                '/opt/google/chrome/chrome',
                '/snap/bin/chromium',
            ]
            for p in paths:
                # 支持通配符路径
                if '*' in p:
                    import glob
                    matches = glob.glob(p)
                    if matches:
                        for match in matches:
                            if os.path.exists(match) and os.access(match, os.X_OK):
                                chrome_path = match
                                logger.info(f"找到浏览器: {chrome_path}")
                                break
                        if chrome_path:
                            break
                elif os.path.exists(p) and os.access(p, os.X_OK):
                    chrome_path = p
                    logger.info(f"找到浏览器: {chrome_path}")
                    break

            # 如果还是没找到，尝试查找Playwright的默认路径或让browser-use自行安装
            if not chrome_path:
                import glob
                playwright_paths = glob.glob('/ms-playwright/**/chromium', recursive=True)
                playwright_paths.extend(glob.glob('/root/.cache/ms-playwright/**/chromium', recursive=True))
                playwright_paths.extend(glob.glob('/ms-playwright/**/chromium-linux/chromium', recursive=True))
                playwright_paths.extend(glob.glob('/root/.cache/ms-playwright/**/chromium-linux/chromium', recursive=True))
                for p in playwright_paths:
                    if os.path.exists(p) and os.access(p, os.X_OK):
                        chrome_path = p
                        logger.info(f"通过Playwright找到浏览器: {chrome_path}")
                        break

                # 最后的备用方案：让browser-use自行处理浏览器安装
                if not chrome_path:
                    logger.info("未找到预装浏览器，将让browser-use自动安装")
                    chrome_path = None  # 让browser-use处理

        # 基础性能优化参数
        extra_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars', '--disable-notifications',
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            '--disable-extensions',
            '--disable-web-security',  # 允许跨域请求
        ]

        # 根据操作系统添加特定参数
        if system == 'Linux':
            # Linux 服务器环境（特别是无头环境）必需的参数
            extra_args.extend([
                '--no-sandbox',  # Linux 必需：禁用沙箱
                '--disable-setuid-sandbox',  # Linux 必需：禁用 setuid 沙箱
                '--disable-dev-shm-usage',  # Linux 必需：使用 /tmp 而不是 /dev/shm
                '--disable-gpu',  # 禁用 GPU 加速（服务器通常无 GPU）
                '--headless=new',  # Linux 服务器使用无头模式
                '--disable-software-rasterizer',  # 禁用软件光栅化器
                '--remote-debugging-port=9222',  # 使用固定端口，避免随机端口导致连接失败
                '--remote-debugging-address=0.0.0.0', # 允许远程连接，而不仅仅是 127.0.0.1
                '--no-zygote',  # 减少进程数
                '--single-process',  # 单进程模式，虽然不稳定但能解决某些 Docker 环境下的 PID 问题
            ])
        else:
            # macOS 和 Windows 使用显示模式
            extra_args.extend([
                '--no-sandbox',  # 兼容性
                '--disable-gpu',
                '--remote-debugging-port=9222',
            ])

        return BrowserProfile(
            headless=(system == 'Linux'),  # Linux 使用无头模式，其他系统使用显示模式
            disable_security=True,
            executable_path=chrome_path,
            args=extra_args,
            wait_for_network_idle_page_load_time=0.2,
            minimum_wait_page_load_time=0.05,
            wait_between_actions=0.1,
            enable_default_extensions=False
        )

    async def run_task(self, task_description: str, planned_tasks=None, callback=None, should_stop=None):
        await self._verify_execution_llm()

        # Cleanup potential zombie processes before starting
        self._cleanup_zombie_chrome()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        controller = Controller()
        _task_was_done = False
        active_task_statuses = set(ACTIVE_TASK_STATUSES)

        async def emit_callback(payload):
            if planned_tasks and isinstance(payload, dict):
                task_id = payload.get('task_id')
                task_status = payload.get('status')
                if task_id is not None and task_status:
                    sync_planned_task_status(planned_tasks, task_id, task_status)

            if not callback:
                return

            if asyncio.iscoroutinefunction(callback):
                await callback(payload)
            else:
                callback(payload)

        def is_placeholder_url(url: str) -> bool:
            normalized = (url or '').strip().lower()
            return (
                not normalized
                or normalized == 'about:blank'
                or normalized.startswith('chrome://newtab')
                or normalized.startswith('edge://newtab')
            )

        def is_close_step(description: str) -> bool:
            text = str(description or '').strip()
            return any(keyword in text for keyword in ['关闭', '关闭该标签页', '关闭标签页'])

        def get_next_active_task():
            return get_next_planned_task(planned_tasks, active_statuses=active_task_statuses)

        async def find_preferred_fallback_tab(browser_session, exclude_target_id=None):
            tabs = await browser_session.get_tabs()
            candidate_tabs = [tab for tab in tabs if tab.target_id != exclude_target_id]
            if not candidate_tabs:
                return None

            non_placeholder_tabs = [tab for tab in candidate_tabs if not is_placeholder_url(getattr(tab, 'url', ''))]
            return (non_placeholder_tabs or candidate_tabs)[-1]

        @controller.action('Done')
        async def done(success: bool = True, text: str = ""):
            nonlocal _task_was_done
            _task_was_done = True
            return f"Finished: {text}"

        @controller.action('close_tab')
        async def close_tab(browser_session=None):
            if browser_session is None or browser_session.agent_focus_target_id is None:
                raise ValueError("No active tab to close")
            target_id = browser_session.agent_focus_target_id
            fallback_tab = None
            try:
                fallback_tab = await find_preferred_fallback_tab(browser_session, exclude_target_id=target_id)
            except Exception as e:
                logger.warning(f"Failed to determine fallback tab before closing {target_id[-4:]}: {e}")

            event = browser_session.event_bus.dispatch(CloseTabEvent(target_id=target_id))
            await event

            if fallback_tab is not None:
                try:
                    await asyncio.sleep(0.15)
                    if browser_session.agent_focus_target_id != fallback_tab.target_id:
                        await browser_session.event_bus.dispatch(
                            SwitchTabEvent(target_id=fallback_tab.target_id)
                        )
                        logger.info(
                            f"↩️ Switched back to existing tab {fallback_tab.target_id[-4:]} "
                            f"({fallback_tab.url}) after closing {target_id[-4:]}"
                        )
                        await emit_callback({
                            'type': 'log',
                            'content': (
                                f"\n[System]\n关闭标签页后，已切回来源页 {fallback_tab.target_id[-4:]}\n"
                            )
                        })
                except Exception as e:
                    logger.warning(f"Failed to switch back to preferred tab after closing {target_id[-4:]}: {e}")

            next_active_task = get_next_active_task()
            if next_active_task and is_close_step(next_active_task.get('description')):
                logger.info(f"✅ Auto-marking close step task {next_active_task['id']} as completed after close_tab")
                await emit_callback({'task_id': int(next_active_task['id']), 'status': 'completed'})

            return f"Closed tab {target_id[-4:]}"

        @controller.action('reload')
        async def reload(browser_session=None):
            if browser_session is None:
                raise ValueError("No browser session available for reload")
            changed = await reload_browser_session_focus_target(browser_session)
            if not changed:
                raise ValueError("No active tab to reload")
            return "Reloaded current tab"

        @controller.action('refresh')
        async def refresh(browser_session=None):
            if browser_session is None:
                raise ValueError("No browser session available for refresh")
            changed = await reload_browser_session_focus_target(browser_session)
            if not changed:
                raise ValueError("No active tab to refresh")
            return "Refreshed current tab"

        @controller.action('metamask_inspect')
        async def metamask_inspect():
            if not self.wallet_context.get('enabled'):
                raise ValueError("MetaMask inspection requires wallet mode")
            wallet_controller = await self._get_wallet_controller()
            return await inspect_metamask_pages_action(
                self.wallet_context,
                wallet_controller=wallet_controller,
            )

        @controller.action('metamask_unlock')
        async def metamask_unlock(password: str):
            if not self.wallet_context.get('enabled'):
                raise ValueError("MetaMask unlock requires wallet mode")
            wallet_controller = await self._get_wallet_controller()
            return await perform_metamask_unlock_action(
                self.wallet_context,
                password=password,
                wallet_controller=wallet_controller,
            )

        @controller.action('metamask_confirm')
        async def metamask_confirm():
            if not self.wallet_context.get('enabled'):
                raise ValueError("MetaMask confirmation requires wallet mode")
            wallet_controller = await self._get_wallet_controller()
            return await perform_metamask_confirm_action(
                self.wallet_context,
                wallet_controller=wallet_controller,
            )

        @controller.action('metamask_ensure_target_chain')
        async def metamask_ensure_target_chain():
            if not self.wallet_context.get('enabled'):
                raise ValueError("MetaMask chain enforcement requires wallet mode")
            wallet_controller = await self._get_wallet_controller()
            result = await perform_metamask_ensure_target_chain_action(
                self.wallet_context,
                wallet_controller=wallet_controller,
            )
            status_value = str((result or {}).get('status') or '')
            if status_value in {'already_on_target', 'switched'}:
                self._wallet_target_chain_ready = True
            return json.dumps(result, ensure_ascii=False)

        @controller.action('mark_task_complete')
        async def mark_task_complete(task_id: int):
            logger.info(f"✅ Explicitly marking task {task_id} as completed")
            task_description = None
            if planned_tasks:
                for task in planned_tasks:
                    if str(task.get('id')) == str(task_id):
                        task_description = task.get('description')
                        break

            if self.wallet_context.get('enabled') and task_description:
                wallet_controller = await self._get_wallet_controller()
                wallet_runtime_state = await wallet_controller.read_dapp_runtime_state()
                validate_wallet_task_completion_state(
                    task_description=task_description,
                    wallet_context=self.wallet_context,
                    ethereum_state=wallet_runtime_state,
                )
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'completed'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_complete callback: {e}")
            return f"Task {task_id} marked completed"

        @controller.action('mark_task_failed')
        async def mark_task_failed(task_id: int):
            logger.info(f"❌ Explicitly marking task {task_id} as failed")
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'failed'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_failed callback: {e}")
            return f"Task {task_id} marked failed"

        @controller.action('mark_task_skipped')
        async def mark_task_skipped(task_id: int):
            logger.info(f"⏭️ Explicitly marking task {task_id} as skipped")
            try:
                await emit_callback({'task_id': int(task_id), 'status': 'skipped'})
            except Exception as e:
                logger.warning(f"Failed to execute mark_task_skipped callback: {e}")
            return f"Task {task_id} marked skipped"

        @controller.action('update_task_status')
        async def update_task_status(task_id: int, status: str):
            normalized_status = str(status).strip().lower()
            if normalized_status not in {'completed', 'failed', 'skipped', 'in_progress'}:
                raise ValueError(f"Unsupported task status: {status}")
            logger.info(f"🔄 Explicitly updating task {task_id} to {normalized_status}")
            try:
                await emit_callback({'task_id': int(task_id), 'status': normalized_status})
            except Exception as e:
                logger.warning(f"Failed to execute update_task_status callback: {e}")
            return f"Task {task_id} marked {normalized_status}"

        # 构建强化版 Prompt
        final_task = task_description
        if planned_tasks:
            final_task += "\n\nIMPORTANT INSTRUCTION:\n"
            final_task += "You have a list of sub-tasks. Execute strictly in order.\n"
            final_task += "CRITICAL: MUST call one of 'mark_task_complete', 'mark_task_failed', 'mark_task_skipped', or 'update_task_status(task_id=..., status=...)' IMMEDIATELY after determining each sub-task result. NEVER skip this step.\n"
            final_task += "IMPORTANT: If a sub-task (like opening a URL) is already fulfilled by the initial state, YOU MUST mark it complete in your VERY FIRST STEP.\n"
            final_task += "Sub-tasks (Execute in order):\n"
            cleaned_tasks = []
            for t in planned_tasks:
                desc = t['description']
                # 递归去除所有层级的重复序号，例如 "1. 1. xxx" -> "xxx"
                while True:
                    match = re.match(r'^\s*\d+[\.\s、:]+(.*)', desc)
                    if not match: break
                    desc = match.group(1).strip()
                cleaned_tasks.append(f"{t['id']}. {desc}")
            final_task += "\n".join(cleaned_tasks)

        # 极限效率版标记指令
        from datetime import datetime
        final_task += f"\n\nCURRENT TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        final_task += "\nCRITICAL PERFORMANCE & SYNC RULES:\n"
        final_task += "1. TASK COMPLETION MARKING RULES:\n"
        final_task += "   a) MARK AFTER COMPLETION: Call 'mark_task_complete(task_id=N)' ONLY AFTER you have SUCCESSFULLY COMPLETED task N.\n"
        final_task += "   b) MARK CURRENT TASK: Always mark the task you just completed, NOT the next task or previous tasks.\n"
        final_task += "   c) CHECK TASK ID: Before marking, verify: 'I just completed task N' - if N is already marked, check which task you actually completed.\n"
        final_task += "   d) DO NOT SKIP: Every sub-task must end with an explicit terminal status update: completed, failed, or skipped.\n"
        final_task += "   e) EXAMPLE SUCCESS: [{click: {...}}, {mark_task_complete: {task_id: 4}}]\n"
        final_task += "   f) EXAMPLE FAILURE: if task 4 cannot be completed after verification, call {mark_task_failed: {task_id: 4}}.\n"
        final_task += "   g) EXAMPLE SKIP: if task 4 is intentionally unnecessary, call {mark_task_skipped: {task_id: 4}}.\n"
        final_task += "   h) NO PRE-MARKING: Never mark a task before completing it. Never mark a task twice.\n"
        final_task += "   i) SINGLE-TASK STEP: If you mark task N in the current step, STOP there. Do NOT start task N+1 in the same step.\n"
        final_task += "   j) FORM EXAMPLE: Good: [{input: {...}}, {mark_task_complete: {task_id: 2}}] then next step handles task 3. Bad: [{mark_task_complete: {task_id: 1}}, {input: {...task 2...}}].\n"
        final_task += "2. NO JAVASCRIPT IN INPUT: When a task asks for a timestamp, YOU MUST compute the final string yourself (e.g., 'V8.01734892400').\n"
        final_task += "   - DO NOT output 'Date.now()' or '{{...}}' strings. Use the CURRENT TIME provided above to estimate a timestamp.\n"
        final_task += "3. DROPDOWN & MODAL ISOLATION: If an action (clicking a button/dropdown) triggers a UI change (modal opens/dropdown expands), YOU MUST STOP and WAIT for the next step to see the new elements. DO NOT attempt to interact with newly appeared elements (like dropdown options) in the same step as the click that opened them.\n"
        final_task += "4. TAB HANDLING: If clicking a link/result opens a new tab, DO NOT click the same result again. Immediately switch to the newest tab, verify the detail page there, then mark the current sub-task complete.\n"
        final_task += "5. ULTRALIGHT THINKING: Keep 'thinking' under 10 words. Just list next actions. Merge multiple INPUTS if they are on the same form, but NEVER merge a UI-opening click with its subsequent interaction. SPEED IS CRITICAL - respond as quickly as possible.\n"
        final_task += "6. FORM VALIDATION & ERROR DETECTION: When filling forms, you MUST:\n"
        final_task += "   a) Check for RED TEXT messages (validation errors) before clicking save/submit\n"
        final_task += "   b) If validation errors exist, COMPLETE ALL MISSING FIELDS first, then retry save\n"
        final_task += "   c) NEVER close a dialog/modal if there are validation errors - complete the form instead\n"
        final_task += "   d) Verify all required fields are filled before attempting to save\n"
        final_task += "   e) Common validation errors: missing required fields (red asterisk or red text), invalid format, etc.\n"
        final_task += "7. RETRY LOGIC: If a previous 'save' or 'submit' failed (e.g., error toast or validation error):\n"
        final_task += "   a) STOP and examine the page for validation errors (red text, error messages)\n"
        final_task += "   b) RE-VERIFY all fields - check dropdowns are actually selected, not just clicked\n"
        final_task += "   c) Re-select dropdowns and re-input text to ensure the form is complete\n"
        final_task += "   d) DO NOT close the dialog - stay and complete all missing fields\n"
        final_task += "   e) Often errors are caused by: missing project selection, unfilled required fields, incorrect format\n"
        final_task += "8. DO NOT REPEAT: If a task is complete, mark it and MOVE ON. Never click the same search result or link twice unless you verified the first click failed.\n"
        final_task += "9. VERIFICATION: Task 15/16 usually require checking the list. Ensure you are on the correct page and the new data is visible before marking complete.\n"
        final_task += "10. ELEMENT IDENTIFICATION: Carefully identify elements before clicking. AVOID clicking 'close' or 'cancel' buttons when filling forms. Check button labels, aria-labels, and icons to ensure you're clicking the correct element.\n"
        final_task += "11. ACTION PARAM FORMAT: For browser actions, always use browser-use native parameter names. Use 'index' for click/input/select actions, use 'text' for typed content, and never use aliases like 'element_id'.\n"
        final_task += "12. CREDENTIALS RULE: NEVER invent, replace, or guess credentials. Only use the username/password explicitly provided in the task. If login keeps failing with an explicit error like '登录失败' or '用户名或密码错误', stop retrying after a small number of attempts and mark the current login task as failed.\n"

        if 'qwen' in self.model_name.lower() or 'deepseek' in self.model_name.lower():
            final_task += "13. EXTREMELY MINIMIZE output tokens for speed. Keep responses as short as possible while maintaining accuracy.\n"

        if self.wallet_context.get('enabled'):
            wallet_provider = self.wallet_context.get('wallet_provider', 'metamask')
            target_chain = self.wallet_context.get('wallet_target_chain') or 'unspecified'
            final_task += build_wallet_mode_rules(wallet_provider=wallet_provider, target_chain=target_chain)

        # 核心修复: 清理 task 长文本中的 URL，防止中文标点紧贴 URL 导致 browser-use 解析错误
        # 例如 "http://localhost:3000，" -> "http://localhost:3000 "
        try:
            # 在中文标点前加空格，避免它们成为 URL 的一部分
            final_task = re.sub(r'(https?://[^\s\u4e00-\u9fa5]+?)(?=[，；。、！])', r'\1 ', final_task)
            logger.info(f"🔧 Optimized task description for URL extraction")
        except:
            pass

        browser_profile = self._create_browser_profile()

        agent = Agent(
            task=final_task,
            llm=self.llm,
            controller=controller,
            browser_profile=browser_profile,
            use_vision=self.execution_mode == 'vision',
            max_actions_per_step=10,  # 增加步进密度，减少总步骤数，降低超时风险
            max_retries=2 if self.wallet_context.get('enabled') else 1,
            max_failures=4 if self.wallet_context.get('enabled') else 2,
            llm_timeout=60,  # 设置LLM调用超时为60秒（支持硅基流动等大模型API）
            step_timeout=90,  # 设置每步超时为90秒
            generate_gif=self.enable_gif,  # 根据开关决定是否生成GIF
        )
        agent._task_was_done = False
        agent._pending_status_task_id = None
        agent._pending_status_task_description = None
        agent._auth_failure_task_id = None
        agent._auth_failure_count = 0

        # Callback helper - 添加任务标记跟踪
        last_processed_step = 0
        last_marked_task_id = 0  # 跟踪上一次标记的任务ID
        known_tab_ids = set()
        async def on_step_end(agent_instance):
            nonlocal _task_was_done, last_processed_step, last_marked_task_id, known_tab_ids

            if should_stop:
                do_stop = await should_stop() if asyncio.iscoroutinefunction(should_stop) else should_stop()
                if do_stop: raise KeyboardInterrupt("User requested stop")

            if _task_was_done:
                raise KeyboardInterrupt("Done")

            history = getattr(agent_instance, 'history', [])
            if hasattr(history, 'history'): history = history.history

            if len(history) > last_processed_step:
                for i in range(last_processed_step, len(history)):
                    step = history[i]
                    # Log logic here
                    try:
                        actions = []
                        if hasattr(step, 'model_output') and hasattr(step.model_output, 'action'):
                            raw = step.model_output.action
                            actions = raw if isinstance(raw, list) else [raw]

                        current_active_task = get_next_active_task()
                        current_active_task_id = current_active_task.get('id') if current_active_task else None
                        current_active_task_desc = str(current_active_task.get('description', '')) if current_active_task else ''
                        if current_active_task_id and any(keyword in current_active_task_desc.lower() for keyword in ['登录', 'login']):
                            signal_text_parts = []
                            model_output = getattr(step, 'model_output', None)
                            for field_name in ['thinking', 'evaluation_previous_goal', 'memory', 'next_goal']:
                                value = getattr(model_output, field_name, None)
                                if value:
                                    signal_text_parts.append(str(value))

                            if _contains_auth_failure_signal(" ".join(signal_text_parts)):
                                if getattr(agent_instance, '_auth_failure_task_id', None) == current_active_task_id:
                                    agent_instance._auth_failure_count += 1
                                else:
                                    agent_instance._auth_failure_task_id = current_active_task_id
                                    agent_instance._auth_failure_count = 1

                                if agent_instance._auth_failure_count >= 3:
                                    logger.warning(
                                        f"⚠️ Login/auth failure threshold reached for task {current_active_task_id}; marking task failed"
                                    )
                                    await emit_callback({
                                        'type': 'log',
                                        'content': (
                                            f"\n[System]\n检测到登录连续失败 3 次，已自动将子任务 {current_active_task_id} 标记为失败并停止执行。\n"
                                        )
                                    })
                                    await emit_callback({
                                        'task_id': int(current_active_task_id),
                                        'status': 'failed'
                                    })
                                    raise KeyboardInterrupt("Repeated authentication failure")
                            elif getattr(agent_instance, '_auth_failure_task_id', None) == current_active_task_id:
                                agent_instance._auth_failure_count = 0

                        # 检查这一步是否调用了任务状态更新动作
                        step_has_task_complete = False
                        step_marked_task_id = None
                        for action in actions:
                            action_dict = action.model_dump() if hasattr(action, 'model_dump') else getattr(action,
                                                                                                            '_action_dict',
                                                                                                            {})
                            if 'mark_task_complete' in action_dict:
                                step_has_task_complete = True
                                step_marked_task_id = action_dict['mark_task_complete'].get('task_id')
                            elif 'mark_task_failed' in action_dict:
                                step_has_task_complete = True
                                step_marked_task_id = action_dict['mark_task_failed'].get('task_id')
                            elif 'mark_task_skipped' in action_dict:
                                step_has_task_complete = True
                                step_marked_task_id = action_dict['mark_task_skipped'].get('task_id')
                            elif 'update_task_status' in action_dict:
                                step_has_task_complete = True
                                payload = action_dict['update_task_status']
                                step_marked_task_id = payload.get('task_id')

                            if step_has_task_complete:
                                # 检查是否重复标记已完成的任务 - 提示但不自动修复
                                if planned_tasks:
                                    for task in planned_tasks:
                                        if task['id'] == step_marked_task_id and task.get('status') in ['completed', 'failed', 'skipped']:
                                            next_expected = last_marked_task_id + 1
                                            logger.warning(
                                                f"⚠️ Task {step_marked_task_id} is already terminal ({task.get('status')})! "
                                                f"You should mark task {next_expected} instead.")
                                            break
                                last_marked_task_id = step_marked_task_id
                                if getattr(agent_instance, '_pending_status_task_id', None) == step_marked_task_id:
                                    agent_instance._pending_status_task_id = None
                                    agent_instance._pending_status_task_description = None
                                break

                        # 检查这一步是否有实际操作（非mark_task_complete的操作）
                        has_real_action = False
                        has_link_open_action = False
                        for action in actions:
                            action_dict = action.model_dump() if hasattr(action, 'model_dump') else getattr(action,
                                                                                                            '_action_dict',
                                                                                                            {})
                            for key in action_dict.keys():
                                if key not in ['mark_task_complete', 'mark_task_failed', 'mark_task_skipped', 'update_task_status', 'done']:
                                    has_real_action = True
                                if key in ['click', 'open_new_tab', 'navigate', 'go_to_url']:
                                    has_link_open_action = True
                                    break
                            if has_real_action:
                                break

                        action_str = " | ".join([self._format_action(a) for a in actions])
                        log_content = f"\n[Step {i + 1}]\n执行: {action_str}\n"

                        if callback:
                            if asyncio.iscoroutinefunction(callback):
                                await callback({'type': 'log', 'content': log_content})
                            else:
                                callback({'type': 'log', 'content': log_content})

                        browser_session = getattr(agent_instance, 'browser_session', None)
                        if browser_session is not None:
                            try:
                                tabs = await browser_session.get_tabs()
                                current_tab_ids = {tab.target_id for tab in tabs}
                                if not known_tab_ids:
                                    known_tab_ids = current_tab_ids
                                else:
                                    new_tabs = [tab for tab in tabs if tab.target_id not in known_tab_ids]
                                    if new_tabs and has_link_open_action:
                                        newest_tab = new_tabs[-1]
                                        if browser_session.agent_focus_target_id != newest_tab.target_id:
                                            await browser_session.event_bus.dispatch(
                                                SwitchTabEvent(target_id=newest_tab.target_id)
                                            )
                                            logger.info(
                                                f"🔀 Auto-switched to newly opened tab {newest_tab.target_id[-4:]} after link click"
                                            )
                                            if callback:
                                                auto_switch_log = (
                                                    f"\n[System]\n检测到新标签页，已自动切换到 {newest_tab.target_id[-4:]}\n"
                                                )
                                                if asyncio.iscoroutinefunction(callback):
                                                    await callback({'type': 'log', 'content': auto_switch_log})
                                                else:
                                                    callback({'type': 'log', 'content': auto_switch_log})
                                    known_tab_ids = current_tab_ids
                            except Exception as tab_error:
                                logger.warning(f"⚠️ Failed to inspect/switch tabs after step {i + 1}: {tab_error}")

                            if self.wallet_context.get('enabled'):
                                try:
                                    recovery_target_id = getattr(browser_session, 'agent_focus_target_id', None)
                                    recovery_url = _get_browser_session_target_url(
                                        browser_session,
                                        recovery_target_id,
                                        tabs=tabs,
                                    )
                                    if recovery_url:
                                        recovered = await recover_empty_wallet_dapp_tab(browser_session)
                                        if recovered:
                                            logger.info(
                                                f"✅ Recovered empty wallet dApp tab for {recovery_url}"
                                            )
                                            if callback:
                                                recovery_log = (
                                                    f"\n[System]\n检测到钱包站点页面为空，已切换到新的前台标签页并重试当前步骤\n"
                                                )
                                                if asyncio.iscoroutinefunction(callback):
                                                    await callback({'type': 'log', 'content': recovery_log})
                                                else:
                                                    callback({'type': 'log', 'content': recovery_log})
                                except Exception as wallet_recovery_error:
                                    logger.warning(
                                        f"⚠️ Failed to recover empty wallet dApp tab after step {i + 1}: {wallet_recovery_error}"
                                    )

                            if self.wallet_context.get('enabled'):
                                try:
                                    await self._ensure_wallet_target_chain_ready(callback)
                                except Exception as wallet_chain_error:
                                    logger.warning(
                                        f"⚠️ Failed to ensure wallet target chain after step {i + 1}: {wallet_chain_error}"
                                    )

                            if planned_tasks and not step_has_task_complete:
                                try:
                                    business_task = get_next_active_task()
                                    business_task_id = business_task.get('id') if business_task else None
                                    business_task_desc = str(business_task.get('description', '')) if business_task else ''
                                    if business_task_id and _task_has_trade_intent(business_task_desc):
                                        blocker = await detect_business_blocker_for_active_task(
                                            browser_session=browser_session,
                                            task_description=business_task_desc,
                                            tabs=tabs,
                                        )
                                        if blocker:
                                            blocker_code = blocker.get('code') or 'business_blocker'
                                            blocker_message = blocker.get('message') or '检测到业务阻塞'
                                            blocker_signal = blocker.get('matched_text') or blocker_code
                                            logger.warning(
                                                f"⚠️ Business blocker detected for task {business_task_id}: "
                                                f"{blocker_code} ({blocker_signal})"
                                            )
                                            await emit_callback({
                                                'type': 'log',
                                                'content': (
                                                    f"\n[System]\n检测到业务阻塞：{blocker_message}"
                                                    f"（命中：{blocker_signal}）。已自动将子任务 {business_task_id} "
                                                    "标记为失败并停止执行。\n"
                                                )
                                            })
                                            await emit_callback({
                                                'task_id': int(business_task_id),
                                                'status': 'failed',
                                            })
                                            raise KeyboardInterrupt(f"Business blocker detected: {blocker_code}")
                                except KeyboardInterrupt:
                                    raise
                                except Exception as business_blocker_error:
                                    logger.warning(
                                        f"⚠️ Failed to inspect business blocker after step {i + 1}: {business_blocker_error}"
                                    )

                        # 记录未标记任务的步骤（不自动修复，仅警告）
                        if has_real_action and not step_has_task_complete and planned_tasks:
                            next_expected_task_id = last_marked_task_id + 1
                            if next_expected_task_id <= len(planned_tasks):
                                # 检查这个任务是否还没有被标记
                                task_already_marked = False
                                for task in planned_tasks:
                                    if task['id'] == next_expected_task_id and task.get('status') in ['completed', 'failed', 'skipped']:
                                        task_already_marked = True
                                        last_marked_task_id = next_expected_task_id
                                        break

                                if not task_already_marked:
                                    # 记录警告，提示 AI 标记当前任务
                                    agent_instance._pending_status_task_id = next_expected_task_id
                                    pending_task_description = None
                                    if planned_tasks:
                                        for task in planned_tasks:
                                            if task.get('id') == next_expected_task_id:
                                                pending_task_description = task.get('description')
                                                break
                                    agent_instance._pending_status_task_description = pending_task_description
                                    logger.warning(
                                        f"⚠️ Step {i + 1} had actions but no task status update. "
                                        f"Please mark task {next_expected_task_id} as completed, failed, or skipped.")

                        if planned_tasks and get_next_active_task() is None:
                            _task_was_done = True
                            logger.info("All planned tasks reached terminal states; stopping agent loop")
                            if callback:
                                completion_log = (
                                    "\n[System]\n检测到全部子任务已进入终态，自动结束当前执行循环。\n"
                                )
                                if asyncio.iscoroutinefunction(callback):
                                    await callback({'type': 'log', 'content': completion_log})
                                else:
                                    callback({'type': 'log', 'content': completion_log})
                            raise KeyboardInterrupt("All planned tasks resolved")

                    except Exception as e:
                        logger.warning(f"⚠️ Error in on_step_end processing: {e}")
                last_processed_step = len(history)

        try:
            # Try to pass callback
            import inspect
            sig = inspect.signature(agent.run)
            if 'on_step_end' in sig.parameters:
                await agent.run(max_steps=100, on_step_end=on_step_end)
            else:
                await agent.run(max_steps=100)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            raise

        # 在任务结束时检查不一致的任务状态
        history = getattr(agent, 'history', [])
        if history:
            logger.info("🔍 Performing final task status consistency check")
            # 检查是否有任务执行了但未标记完成
            executed_tasks_info = self._find_executed_tasks(history)
            if (
                executed_tasks_info
                and executed_tasks_info.get('executed_actions', 0) > len(executed_tasks_info.get('marked_tasks', []))
                and executed_tasks_info.get('unmarked_actions')
            ):
                logger.warning(
                    f"⚠️ Found {executed_tasks_info['executed_actions']} executed actions, but only {len(executed_tasks_info['marked_tasks'])} tasks were explicitly marked complete")
                logger.warning(f"⚠️ Unmarked actions: {executed_tasks_info['unmarked_actions']}")
                logger.warning("⚠️ This indicates the AI agent did not follow the 'mark_task_complete' rule properly.")

        return history

    def _find_executed_tasks(self, history):
        """
        通过分析执行历史找出已执行但未标记完成的任务
        """
        if not history or not hasattr(history, 'steps'):
            return []

        executed_actions = {}  # 已执行的操作类型和索引，以及对应的步骤
        marked_tasks = set()  # 已标记完成的任务ID

        # 分析执行历史
        for step_idx, step in enumerate(getattr(history, 'steps', [])):
            # 检查每一步中的actions
            actions = getattr(step, 'actions', [])
            for action in actions:
                # 记录已执行的操作
                if hasattr(action, 'input'):
                    action_key = f"input_{action.input.index}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'input',
                        'index': action.input.index
                    }
                elif hasattr(action, 'click'):
                    action_key = f"click_{action.click.index}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'click',
                        'index': action.click.index
                    }
                elif hasattr(action, 'switch_tab'):
                    action_key = f"switch_tab_{action.switch_tab.tab_id}"
                    executed_actions[action_key] = {
                        'step': step_idx,
                        'action': 'switch_tab',
                        'tab_id': action.switch_tab.tab_id
                    }

                # 记录已标记完成的任务
                if hasattr(action, 'mark_task_complete'):
                    marked_tasks.add(action.mark_task_complete.task_id)

        # 理想情况下应该有一个映射机制来关联操作和任务，但由于我们没有这个映射，
        # 我们只能记录未标记完成的执行操作作为调试信息
        unmarked_actions = []
        for action_key, action_info in executed_actions.items():
            unmarked_actions.append({
                'action': action_info['action'],
                'step': action_info['step'],
                'details': action_key
            })

        return {
            'marked_tasks': list(marked_tasks),
            'executed_actions': len(executed_actions),
            'unmarked_actions': unmarked_actions
        }

    async def run_full_process(self, task_description: str, analysis_callback=None, step_callback=None,
                               should_stop=None):
        planned_tasks = await self.analyze_task(task_description)
        if analysis_callback:
            if asyncio.iscoroutinefunction(analysis_callback):
                await analysis_callback(planned_tasks)
            else:
                analysis_callback(planned_tasks)

        try:
            return await self.run_task(task_description, planned_tasks, step_callback, should_stop)
        finally:
            await self._close_wallet_controller()
