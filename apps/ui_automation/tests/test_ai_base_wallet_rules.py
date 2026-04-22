from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock
from types import SimpleNamespace

from browser_use.browser.events import SwitchTabEvent

from apps.ui_automation.ai_base import (
    activate_browser_session_focus_target,
    build_wallet_mode_rules,
    reload_browser_session_focus_target,
)


class WalletModeRulesTests(TestCase):
    def test_wallet_mode_rules_include_connect_wallet_entrypoint_and_empty_shell_recovery(self):
        rules = build_wallet_mode_rules(wallet_provider='metamask', target_chain='evm')

        self.assertIn("Connect Wallet", rules)
        self.assertIn("Wait for the provider picker", rules)
        self.assertIn("fresh foreground tab", rules)
        self.assertIn("MetaMask popup/tab opens", rules)
        self.assertIn("meaningful text or controls are visible", rules)


class BrowserSessionFocusActivationTests(IsolatedAsyncioTestCase):
    async def test_activates_current_focus_target(self):
        dispatch = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id='good-target',
            event_bus=SimpleNamespace(dispatch=dispatch),
        )

        changed = await activate_browser_session_focus_target(browser_session)

        self.assertTrue(changed)
        self.assertEqual(dispatch.await_count, 1)
        event = dispatch.await_args_list[0].args[0]
        self.assertIsInstance(event, SwitchTabEvent)
        self.assertEqual(event.target_id, 'good-target')

    async def test_skips_activation_without_focus_target(self):
        dispatch = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id=None,
            event_bus=SimpleNamespace(dispatch=dispatch),
        )

        changed = await activate_browser_session_focus_target(browser_session)

        self.assertFalse(changed)
        dispatch.assert_not_awaited()


class BrowserSessionReloadTests(IsolatedAsyncioTestCase):
    async def test_reloads_current_focus_target_via_cdp(self):
        cdp_send = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id='wallet-target',
            get_or_create_cdp_session=AsyncMock(
                return_value=SimpleNamespace(
                    session_id='cdp-session-1',
                    cdp_client=SimpleNamespace(send=SimpleNamespace(Page=SimpleNamespace(reload=cdp_send))),
                )
            ),
        )

        changed = await reload_browser_session_focus_target(browser_session)

        self.assertTrue(changed)
        browser_session.get_or_create_cdp_session.assert_awaited_once_with(
            target_id='wallet-target',
            focus=False,
        )
        cdp_send.assert_awaited_once_with(
            params={'ignoreCache': False},
            session_id='cdp-session-1',
        )

    async def test_skips_reload_without_focus_target(self):
        browser_session = SimpleNamespace(
            agent_focus_target_id=None,
            get_or_create_cdp_session=AsyncMock(),
        )

        changed = await reload_browser_session_focus_target(browser_session)

        self.assertFalse(changed)
        browser_session.get_or_create_cdp_session.assert_not_awaited()
