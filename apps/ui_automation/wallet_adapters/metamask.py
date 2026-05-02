import asyncio
import json
import logging

from .chains import (
    _normalize_wallet_chain_id,
    resolve_wallet_target_chain_config,
)
from .page_actions import (
    _click_first_available_locator,
    _fill_first_available_locator,
    _is_metamask_blocking_auth_step,
    _is_metamask_provider_selection_step,
    _is_metamask_unlock_step,
    _wait_for_metamask_page_transition,
)
from .snapshot import (
    _collect_metamask_snapshots,
    _ensure_metamask_home_page,
    select_metamask_snapshot,
)

logger = logging.getLogger(__name__)


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
