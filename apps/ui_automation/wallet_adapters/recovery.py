import asyncio
import logging
from urllib.parse import urlsplit

from .selectors import is_bootstrap_placeholder_tab_url

logger = logging.getLogger(__name__)


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

    from browser_use.browser.events import SwitchTabEvent, TabCreatedEvent

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
