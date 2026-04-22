from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from browser_use.browser.events import SwitchTabEvent, TabCreatedEvent

from apps.ui_automation import ai_base
from apps.ui_automation.ai_base import (
    navigate_browser_session_via_new_target,
    recover_empty_wallet_dapp_tab,
    should_fallback_navigation_with_new_target,
    should_open_url_in_new_target,
    stabilize_browser_session_initial_focus,
)


class BrowserSessionFocusStabilizationTests(IsolatedAsyncioTestCase):
    async def test_switches_from_newtab_footer_to_existing_blank_tab(self):
        dispatch = AsyncMock()
        focus_target_id = 'bad-target'
        browser_session = SimpleNamespace(
            agent_focus_target_id=focus_target_id,
            session_manager=SimpleNamespace(
                get_target=MagicMock(return_value=SimpleNamespace(url='chrome://newtab-footer/'))
            ),
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='chrome://newtab-footer/', target_id=focus_target_id),
                    SimpleNamespace(url='about:blank', target_id='blank-target'),
                ]
            ),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=None,
        )

        changed = await stabilize_browser_session_initial_focus(browser_session)

        self.assertTrue(changed)
        self.assertEqual(browser_session.agent_focus_target_id, 'blank-target')
        self.assertEqual(dispatch.await_count, 1)
        event = dispatch.await_args_list[0].args[0]
        self.assertIsInstance(event, SwitchTabEvent)
        self.assertEqual(event.target_id, 'blank-target')

    async def test_creates_blank_tab_when_only_bad_placeholder_exists(self):
        dispatch = AsyncMock()
        create_target = AsyncMock(return_value={'targetId': 'new-blank-target'})
        browser_session = SimpleNamespace(
            agent_focus_target_id='bad-target',
            session_manager=SimpleNamespace(
                get_target=MagicMock(return_value=SimpleNamespace(url='chrome://newtab-footer/'))
            ),
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='chrome://newtab-footer/', target_id='bad-target'),
                ]
            ),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=SimpleNamespace(
                send=SimpleNamespace(
                    Target=SimpleNamespace(
                        createTarget=create_target,
                    )
                )
            ),
        )

        changed = await stabilize_browser_session_initial_focus(browser_session)

        self.assertTrue(changed)
        self.assertEqual(browser_session.agent_focus_target_id, 'new-blank-target')
        create_target.assert_awaited_once_with(params={'url': 'about:blank'})
        self.assertEqual(dispatch.await_count, 2)
        created_event = dispatch.await_args_list[0].args[0]
        switch_event = dispatch.await_args_list[1].args[0]
        self.assertIsInstance(created_event, TabCreatedEvent)
        self.assertEqual(created_event.target_id, 'new-blank-target')
        self.assertIsInstance(switch_event, SwitchTabEvent)
        self.assertEqual(switch_event.target_id, 'new-blank-target')

    async def test_keeps_existing_focus_when_current_tab_is_usable(self):
        dispatch = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id='good-target',
            session_manager=SimpleNamespace(
                get_target=MagicMock(return_value=SimpleNamespace(url='https://example.com'))
            ),
            get_tabs=AsyncMock(return_value=[]),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=None,
        )

        changed = await stabilize_browser_session_initial_focus(browser_session)

        self.assertFalse(changed)
        dispatch.assert_not_awaited()


class WalletDappRecoveryTests(IsolatedAsyncioTestCase):
    async def test_switches_to_existing_loaded_tab_with_same_url_when_active_wallet_page_is_empty(self):
        dispatch = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id='empty-target',
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='https://safuskill.ai/login', target_id='empty-target'),
                    SimpleNamespace(url='https://safuskill.ai/login', target_id='loaded-target'),
                ]
            ),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=None,
        )

        async def fake_body_text_fetcher(_browser_session, target_id):
            if target_id == 'empty-target':
                return ''
            if target_id == 'loaded-target':
                return 'SafuSkill Wallet Connect'
            return ''

        changed = await recover_empty_wallet_dapp_tab(
            browser_session,
            body_text_fetcher=fake_body_text_fetcher,
        )

        self.assertTrue(changed)
        self.assertEqual(browser_session.agent_focus_target_id, 'loaded-target')
        self.assertEqual(dispatch.await_count, 1)
        event = dispatch.await_args_list[0].args[0]
        self.assertIsInstance(event, SwitchTabEvent)
        self.assertEqual(event.target_id, 'loaded-target')

    async def test_creates_fresh_tab_for_empty_wallet_page_when_no_loaded_duplicate_exists(self):
        dispatch = AsyncMock()
        create_target = AsyncMock(return_value={'targetId': 'fresh-target'})
        browser_session = SimpleNamespace(
            agent_focus_target_id='empty-target',
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='https://safuskill.ai/login', target_id='empty-target'),
                ]
            ),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=SimpleNamespace(
                send=SimpleNamespace(
                    Target=SimpleNamespace(
                        createTarget=create_target,
                    )
                )
            ),
        )

        changed = await recover_empty_wallet_dapp_tab(
            browser_session,
            body_text_fetcher=AsyncMock(return_value=''),
        )

        self.assertTrue(changed)
        self.assertEqual(browser_session.agent_focus_target_id, 'fresh-target')
        create_target.assert_awaited_once_with(params={'url': 'https://safuskill.ai/login'})
        self.assertEqual(dispatch.await_count, 2)
        created_event = dispatch.await_args_list[0].args[0]
        switch_event = dispatch.await_args_list[1].args[0]
        self.assertIsInstance(created_event, TabCreatedEvent)
        self.assertEqual(created_event.target_id, 'fresh-target')
        self.assertEqual(created_event.url, 'https://safuskill.ai/login')
        self.assertIsInstance(switch_event, SwitchTabEvent)
        self.assertEqual(switch_event.target_id, 'fresh-target')

    async def test_switches_to_non_modal_sibling_with_same_origin_and_path_when_wallet_picker_is_stuck(self):
        dispatch = AsyncMock()
        browser_session = SimpleNamespace(
            agent_focus_target_id='stuck-target',
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='https://pancakeswap.finance/swap?chain=bscTestnet', target_id='stuck-target'),
                    SimpleNamespace(url='https://pancakeswap.finance/swap', target_id='clean-target'),
                ]
            ),
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=None,
        )

        async def fake_body_text_fetcher(_browser_session, target_id):
            if target_id == 'stuck-target':
                return (
                    'Connect Wallet\n'
                    'Metamask\n'
                    'Select Chain\n'
                    'Metamask supports multiple ecosystems. Please select which chain(s) to connect to.\n'
                    'EVM\nSolana\nConnect'
                )
            if target_id == 'clean-target':
                return 'Trade\nSwap\nFrom:\n0xc557...bE98\ntBNB\nTo:\nCAKE2\nSwap Now'
            return ''

        changed = await recover_empty_wallet_dapp_tab(
            browser_session,
            body_text_fetcher=fake_body_text_fetcher,
        )

        self.assertTrue(changed)
        self.assertEqual(browser_session.agent_focus_target_id, 'clean-target')
        self.assertEqual(dispatch.await_count, 1)
        event = dispatch.await_args_list[0].args[0]
        self.assertIsInstance(event, SwitchTabEvent)
        self.assertEqual(event.target_id, 'clean-target')


class BrowserSessionDirectTargetNavigationTests(IsolatedAsyncioTestCase):
    def test_patched_navigation_handler_name_matches_browser_use_requirement(self):
        handler_name = ai_base.PATCHED_NAVIGATE_HANDLER_NAME

        self.assertTrue(handler_name.startswith('on_'))
        self.assertTrue(handler_name.endswith('NavigateToUrlEvent'))

    def test_prefers_new_target_navigation_when_current_tab_is_blank(self):
        self.assertTrue(
            should_open_url_in_new_target(
                current_url='about:blank',
                target_url='https://safuskill.ai/login',
                new_tab=False,
            )
        )

    def test_skips_new_target_navigation_for_normal_loaded_page(self):
        self.assertFalse(
            should_open_url_in_new_target(
                current_url='https://example.com/dashboard',
                target_url='https://safuskill.ai/login',
                new_tab=False,
            )
        )

    def test_matches_err_invalid_argument_navigation_failure(self):
        self.assertTrue(
            should_fallback_navigation_with_new_target(
                RuntimeError('Navigation failed: net::ERR_INVALID_ARGUMENT'),
                target_url='https://safuskill.ai/login',
            )
        )

    async def test_creates_and_switches_to_new_target_for_direct_navigation(self):
        dispatch = AsyncMock()
        create_target = AsyncMock(return_value={'targetId': 'fresh-target'})
        browser_session = SimpleNamespace(
            agent_focus_target_id='old-target',
            event_bus=SimpleNamespace(dispatch=dispatch),
            _cdp_client_root=SimpleNamespace(
                send=SimpleNamespace(
                    Target=SimpleNamespace(
                        createTarget=create_target,
                    )
                )
            ),
        )

        target_id = await navigate_browser_session_via_new_target(
            browser_session,
            'https://safuskill.ai/login',
        )

        self.assertEqual(target_id, 'fresh-target')
        self.assertEqual(browser_session.agent_focus_target_id, 'fresh-target')
        create_target.assert_awaited_once_with(params={'url': 'https://safuskill.ai/login'})
        self.assertEqual(dispatch.await_count, 2)
        created_event = dispatch.await_args_list[0].args[0]
        switch_event = dispatch.await_args_list[1].args[0]
        self.assertIsInstance(created_event, TabCreatedEvent)
        self.assertEqual(created_event.target_id, 'fresh-target')
        self.assertEqual(created_event.url, 'https://safuskill.ai/login')
        self.assertIsInstance(switch_event, SwitchTabEvent)
        self.assertEqual(switch_event.target_id, 'fresh-target')
