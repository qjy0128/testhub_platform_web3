from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.ui_automation.ai_base import (
    BaseBrowserAgent,
    MetaMaskWalletController,
    extract_browser_use_start_url_from_task,
    detect_business_blocker_for_active_task,
    detect_business_blocker_signal,
    inspect_metamask_page_html,
    reorder_wallet_planned_steps,
    resolve_wallet_target_chain_config,
    validate_wallet_task_completion_state,
)


class MetaMaskPageInspectionTests(SimpleTestCase):
    def test_detects_unlock_page_and_selectors(self):
        snapshot = inspect_metamask_page_html(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html#/unlock',
            html='''
                <form data-testid="unlock-page">
                    <input data-testid="unlock-password" type="password" placeholder="输入您的密码" />
                    <button data-testid="unlock-submit" type="submit">登录</button>
                </form>
            ''',
        )

        self.assertEqual(snapshot['page_kind'], 'unlock')
        self.assertEqual(snapshot['password_selector'], '[data-testid="unlock-password"]')
        self.assertEqual(snapshot['primary_selector'], '[data-testid="unlock-submit"]')

    def test_detects_connect_page_primary_confirm(self):
        snapshot = inspect_metamask_page_html(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html#/connect/example',
            html='''
                <button data-testid="cancel-btn">取消</button>
                <button data-testid="confirm-btn">连接</button>
            ''',
        )

        self.assertEqual(snapshot['page_kind'], 'connect')
        self.assertEqual(snapshot['primary_selector'], '[data-testid="confirm-btn"]')
        self.assertIsNone(snapshot['password_selector'])

    def test_detects_signature_request_confirm(self):
        snapshot = inspect_metamask_page_html(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html#/confirm-transaction/abc/signature-request',
            html='''
                <div>登录请求</div>
                <button data-testid="confirm-footer-button">确认</button>
            ''',
        )

        self.assertEqual(snapshot['page_kind'], 'confirm')
        self.assertEqual(snapshot['primary_selector'], '[data-testid="confirm-footer-button"]')


    def test_detects_unlock_page_with_generic_password_field_fallback(self):
        snapshot = inspect_metamask_page_html(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/popup.html#/unlock',
            html='''
                <form>
                    <input type="password" placeholder="Enter your password" />
                    <button type="submit">Unlock</button>
                </form>
            ''',
        )

        self.assertEqual(snapshot['page_kind'], 'unlock')
        self.assertEqual(snapshot['password_selector'], 'input[type="password"]')
        self.assertEqual(snapshot['primary_selector'], 'button:has-text("Unlock")')

    def test_detects_confirmation_page_with_text_button_fallback(self):
        snapshot = inspect_metamask_page_html(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/popup.html#/confirmation',
            html='''
                <div>Signature request</div>
                <button type="button">Confirm</button>
            ''',
        )

        self.assertEqual(snapshot['page_kind'], 'confirm')
        self.assertEqual(snapshot['primary_selector'], 'button:has-text("Confirm")')


class WalletStepReorderTests(SimpleTestCase):
    def test_moves_unlock_before_authorization_for_metamask_login(self):
        steps = [
            '访问登录页面https://safuskill.ai/login',
            '选择MetaMask作为登录方式',
            '完成MetaMask身份授权验证',
            '输入登录密码<钱包密码>',
            '提交信息完成登录操作',
        ]

        self.assertEqual(
            reorder_wallet_planned_steps(steps, wallet_provider='metamask'),
            [
                '访问登录页面https://safuskill.ai/login',
                '选择MetaMask作为登录方式',
                '输入登录密码<钱包密码>',
                '完成MetaMask身份授权验证',
                '提交信息完成登录操作',
            ],
        )

    def test_preserves_existing_wallet_step_order_when_unlock_is_already_early(self):
        steps = [
            '访问https://safuskill.ai/login登录页面',
            '选择MetaMask作为登录方式',
            '输入MetaMask密码<钱包密码>',
            '完成登录操作',
        ]

        self.assertEqual(
            reorder_wallet_planned_steps(steps, wallet_provider='metamask'),
            steps,
        )


class WalletTaskCompletionValidationTests(SimpleTestCase):
    def test_rejects_connect_wallet_completion_without_connected_address(self):
        with self.assertRaisesRegex(RuntimeError, 'connected wallet address'):
            validate_wallet_task_completion_state(
                task_description='使用 MetaMask 连接钱包',
                wallet_context={
                    'enabled': True,
                    'wallet_target_chain': 'BNB Smart Chain Testnet',
                },
                ethereum_state={
                    'has_provider': True,
                    'chain_id': '0x61',
                    'selected_address': None,
                },
            )

    def test_allows_connect_wallet_completion_once_connected_address_exists(self):
        validate_wallet_task_completion_state(
            task_description='使用 MetaMask 连接钱包',
            wallet_context={
                'enabled': True,
                'wallet_target_chain': 'BNB Smart Chain Testnet',
            },
            ethereum_state={
                'has_provider': True,
                'chain_id': '0x61',
                'selected_address': '0xabc',
            },
        )


class BrowserUseStartUrlExtractionTests(SimpleTestCase):
    def test_prefers_real_http_url_over_wallet_rule_home_html_token(self):
        task = (
            'Visit https://pancakeswap.finance/swap?chain=bscTestnet and continue the swap. '
            'If MetaMask opens an unlock page (#/unlock or home.html#unlock), call metamask_unlock.'
        )

        self.assertEqual(
            extract_browser_use_start_url_from_task(task),
            'https://pancakeswap.finance/swap?chain=bscTestnet',
        )

    def test_ignores_bare_home_html_unlock_token(self):
        task = 'If MetaMask opens an unlock page (#/unlock or home.html#unlock), call metamask_unlock.'

        self.assertIsNone(extract_browser_use_start_url_from_task(task))


class BusinessBlockerDetectionTests(SimpleTestCase):
    def test_detects_price_impact_too_high_as_business_blocker(self):
        blocker = detect_business_blocker_signal(
            'Trade Swap Price impact too high. Proceed with caution. Price Impact 74.83%'
        )

        self.assertIsNotNone(blocker)
        self.assertEqual(blocker['code'], 'price_impact_too_high')
        self.assertIn('价格影响过高', blocker['message'])

    def test_ignores_transient_quote_loading_text(self):
        blocker = detect_business_blocker_signal('Searching For The Best Price')

        self.assertIsNone(blocker)


class BusinessBlockerBrowserDetectionTests(IsolatedAsyncioTestCase):
    async def test_detects_business_blocker_for_active_trade_page(self):
        browser_session = SimpleNamespace(
            agent_focus_target_id='trade-target',
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(url='https://pancakeswap.finance/swap?chain=bscTestnet', target_id='trade-target'),
                ]
            ),
            session_manager=SimpleNamespace(
                get_target=MagicMock(return_value=SimpleNamespace(url='https://pancakeswap.finance/swap?chain=bscTestnet'))
            ),
        )

        blocker = await detect_business_blocker_for_active_task(
            browser_session=browser_session,
            task_description='在发射台买入 0.001 BNB 的任意代币',
            body_text_fetcher=AsyncMock(
                return_value='Trade Swap Price impact too high. Proceed with caution. Price Impact 74.83%'
            ),
        )

        self.assertIsNotNone(blocker)
        self.assertEqual(blocker['code'], 'price_impact_too_high')
        self.assertEqual(blocker['url'], 'https://pancakeswap.finance/swap?chain=bscTestnet')

    async def test_ignores_extension_pages_even_if_text_contains_blocker(self):
        browser_session = SimpleNamespace(
            agent_focus_target_id='wallet-target',
            get_tabs=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html#/confirm',
                        target_id='wallet-target',
                    ),
                ]
            ),
            session_manager=SimpleNamespace(
                get_target=MagicMock(
                    return_value=SimpleNamespace(
                        url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/notification.html#/confirm'
                    )
                )
            ),
        )

        blocker = await detect_business_blocker_for_active_task(
            browser_session=browser_session,
            task_description='买入 0.001 BNB',
            body_text_fetcher=AsyncMock(return_value='Price impact too high'),
        )

        self.assertIsNone(blocker)


class FakeMetaMaskLocator:
    def __init__(self):
        self.first = self
        self.wait_for = AsyncMock(return_value=None)
        self.fill = AsyncMock(return_value=None)
        self.click = AsyncMock(return_value=None)
        self.count = AsyncMock(return_value=1)
        self.is_visible = AsyncMock(return_value=True)


class FakeMetaMaskPage:
    def __init__(self, url, html):
        self.url = url
        self._html = html
        self._locators = {}
        self.bring_to_front = AsyncMock(return_value=None)
        self.wait_for_timeout = AsyncMock(return_value=None)

    async def content(self):
        return self._html

    def locator(self, selector):
        if selector not in self._locators:
            self._locators[selector] = FakeMetaMaskLocator()
        return self._locators[selector]

    def is_closed(self):
        return False


class MetaMaskWalletControllerTests(IsolatedAsyncioTestCase):
    async def test_reuses_single_cdp_connection_across_multiple_wallet_actions(self):
        page = FakeMetaMaskPage(
            url='chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html#/unlock',
            html='''
                <form data-testid="unlock-page">
                    <input data-testid="unlock-password" type="password" />
                    <button data-testid="unlock-submit" type="submit">Unlock</button>
                </form>
            ''',
        )
        browser = SimpleNamespace(
            contexts=[SimpleNamespace(pages=[page])],
            close=AsyncMock(return_value=None),
        )
        chromium = SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser))
        playwright_runtime = SimpleNamespace(chromium=chromium, stop=AsyncMock(return_value=None))
        playwright_manager = SimpleNamespace(start=AsyncMock(return_value=playwright_runtime))

        controller = MetaMaskWalletController(
            wallet_context={
                'debugger_address': '127.0.0.1:9222',
                'metamask_extension_id': 'nkbihfbeogaeaoehlefnkodbefgpgknn',
            },
            playwright_factory=lambda: playwright_manager,
        )

        snapshots = await controller.collect_snapshots()
        self.assertEqual(len(snapshots), 1)

        await controller.collect_snapshots()
        await controller.unlock('12345678')
        await controller.close()

        chromium.connect_over_cdp.assert_awaited_once_with('http://127.0.0.1:9222')
        browser.close.assert_awaited_once()
        playwright_runtime.stop.assert_awaited_once()

    async def test_ensure_target_chain_skips_when_chain_already_matches(self):
        controller = MetaMaskWalletController(
            wallet_context={
                'wallet_target_chain': 'BNB Smart Chain Testnet',
                'debugger_address': '127.0.0.1:9222',
                'metamask_extension_id': 'nkbihfbeogaeaoehlefnkodbefgpgknn',
            }
        )
        page = object()

        with (
            patch.object(controller, '_find_wallet_capable_dapp_page', AsyncMock(return_value=page)),
            patch.object(
                controller,
                '_read_ethereum_state',
                AsyncMock(return_value={'has_provider': True, 'chain_id': '0x61', 'selected_address': '0xabc'}),
            ),
            patch.object(controller, '_request_switch_chain', AsyncMock()) as mock_switch,
            patch.object(controller, '_request_add_chain', AsyncMock()) as mock_add,
            patch.object(controller, 'confirm', AsyncMock()) as mock_confirm,
        ):
            result = await controller.ensure_target_chain()

        self.assertEqual(result['status'], 'already_on_target')
        self.assertEqual(result['chain_id'], '0x61')
        mock_switch.assert_not_awaited()
        mock_add.assert_not_awaited()
        mock_confirm.assert_not_awaited()

    async def test_ensure_target_chain_adds_missing_chain_and_confirms_popup(self):
        controller = MetaMaskWalletController(
            wallet_context={
                'wallet_target_chain': 'BNB Smart Chain Testnet',
                'debugger_address': '127.0.0.1:9222',
                'metamask_extension_id': 'nkbihfbeogaeaoehlefnkodbefgpgknn',
            }
        )
        page = object()

        with (
            patch.object(controller, '_find_wallet_capable_dapp_page', AsyncMock(return_value=page)),
            patch.object(
                controller,
                '_read_ethereum_state',
                AsyncMock(side_effect=[
                    {'has_provider': True, 'chain_id': '0x1', 'selected_address': '0xabc'},
                    {'has_provider': True, 'chain_id': '0x61', 'selected_address': '0xabc'},
                ]),
            ),
            patch.object(
                controller,
                '_request_switch_chain',
                AsyncMock(return_value={'ok': False, 'code': 4902, 'message': 'missing chain', 'chainId': '0x1'}),
            ) as mock_switch,
            patch.object(
                controller,
                '_request_add_chain',
                AsyncMock(return_value={'ok': True, 'result': None, 'chainId': '0x1'}),
            ) as mock_add,
            patch.object(controller, 'confirm', AsyncMock(return_value='Confirmed MetaMask chain add')) as mock_confirm,
        ):
            result = await controller.ensure_target_chain()

        self.assertEqual(result['status'], 'switched')
        self.assertEqual(result['chain_id'], '0x61')
        mock_switch.assert_awaited_once_with(page, '0x61')
        mock_add.assert_awaited_once()
        mock_confirm.assert_awaited()

    async def test_ensure_target_chain_handles_pending_add_chain_request(self):
        controller = MetaMaskWalletController(
            wallet_context={
                'wallet_target_chain': 'BNB Smart Chain Testnet',
                'debugger_address': '127.0.0.1:9222',
                'metamask_extension_id': 'nkbihfbeogaeaoehlefnkodbefgpgknn',
            }
        )
        page = object()

        with (
            patch.object(controller, '_find_wallet_capable_dapp_page', AsyncMock(return_value=page)),
            patch.object(
                controller,
                '_read_ethereum_state',
                AsyncMock(side_effect=[
                    {'has_provider': True, 'chain_id': '0x1', 'selected_address': '0xabc'},
                    {'has_provider': True, 'chain_id': '0x61', 'selected_address': '0xabc'},
                ]),
            ),
            patch.object(
                controller,
                '_request_switch_chain',
                AsyncMock(return_value={'ok': False, 'code': 4902, 'message': 'missing chain', 'chainId': '0x1'}),
            ) as mock_switch,
            patch.object(
                controller,
                '_request_add_chain',
                AsyncMock(return_value={'ok': False, 'pending': True, 'message': 'wallet request is still pending'}),
            ) as mock_add,
            patch.object(controller, 'confirm', AsyncMock(return_value='Confirmed MetaMask chain add')) as mock_confirm,
        ):
            result = await controller.ensure_target_chain()

        self.assertEqual(result['status'], 'switched')
        self.assertEqual(result['chain_id'], '0x61')
        mock_switch.assert_awaited_once_with(page, '0x61')
        mock_add.assert_awaited_once()
        mock_confirm.assert_awaited()

    async def test_waits_for_delayed_chain_confirmation_popup(self):
        controller = MetaMaskWalletController(
            wallet_context={
                'wallet_target_chain': 'BNB Smart Chain Testnet',
                'debugger_address': '127.0.0.1:9222',
                'metamask_extension_id': 'nkbihfbeogaeaoehlefnkodbefgpgknn',
            }
        )

        with patch.object(
            controller,
            'confirm',
            AsyncMock(side_effect=[
                RuntimeError('No actionable MetaMask confirmation page is available'),
                'Confirmed MetaMask chain prompt',
            ]),
        ) as mock_confirm:
            confirmations = await controller._confirm_pending_chain_prompt(attempts=1, wait_for_page_attempts=2)

        self.assertEqual(confirmations, ['Confirmed MetaMask chain prompt'])
        self.assertEqual(mock_confirm.await_count, 2)


class WalletTargetChainConfigTests(SimpleTestCase):
    def test_resolves_bnb_smart_chain_testnet_config(self):
        config = resolve_wallet_target_chain_config({'wallet_target_chain': 'BNB Smart Chain Testnet'})

        self.assertIsNotNone(config)
        self.assertEqual(config['chain_id'], '0x61')
        self.assertEqual(config['chain_name'], 'BNB Smart Chain Testnet')
        self.assertIn('https://data-seed-prebsc-1-s1.bnbchain.org:8545', config['rpc_urls'])


class BaseBrowserAgentInitializationTests(SimpleTestCase):
    @patch('apps.requirement_analysis.models.AIModelConfig.objects.filter')
    def test_initializes_wallet_controller_slot(self, mock_filter):
        mock_filter.return_value.first.return_value = SimpleNamespace(
            api_key='test-key',
            base_url='https://example.com/v1',
            model_name='test-model',
            model_type='openai',
            temperature=0,
        )

        with (
            patch('apps.ui_automation.ai_base.Agent', object()),
            patch('apps.ui_automation.ai_base.Controller', object()),
            patch('apps.ui_automation.ai_base.BrowserProfile', object()),
        ):
            agent = BaseBrowserAgent(wallet_context={'enabled': True})

        self.assertTrue(hasattr(agent, '_wallet_controller'))
        self.assertIsNone(agent._wallet_controller)
