import logging

from .page_actions import (
    _fill_first_available_locator,
    _click_first_available_locator,
    _wait_for_metamask_page_transition,
    inspect_metamask_page_html,
)

logger = logging.getLogger(__name__)


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


def select_metamask_snapshot(snapshots, allowed_kinds):
    allowed = set(allowed_kinds or [])
    for snapshot in reversed(list(snapshots or [])):
        if snapshot.get('page_kind') in allowed:
            return snapshot
    return None


async def inspect_metamask_pages_action(wallet_context, wallet_controller=None):
    import json

    if wallet_controller is not None:
        return await wallet_controller.inspect_pages()

    from .metamask import MetaMaskWalletController, _with_metamask_pages

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
