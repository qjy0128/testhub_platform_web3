import logging
import re

from .selectors import (
    METAMASK_CONFIRM_TEXT_BUTTONS,
    METAMASK_CONNECT_CONFIRM_SELECTOR,
    METAMASK_CONNECT_TEXT_BUTTONS,
    METAMASK_FOOTER_CONFIRM_SELECTOR,
    METAMASK_UNLOCK_PASSWORD_SELECTOR,
    METAMASK_UNLOCK_SUBMIT_SELECTOR,
    METAMASK_UNLOCK_TEXT_BUTTONS,
)

logger = logging.getLogger(__name__)


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
