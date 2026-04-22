import asyncio
import os
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from apps.requirement_analysis.models import AIModelConfig
from apps.ui_automation.models import AIExecutionRecord, WalletActionLog, WalletBrowserConfig, WalletSession

User = get_user_model()


class WalletBrowserConfigApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='wallet-api-user', password='test-password')
        self.client.force_login(self.user)

    @patch(
        'apps.ui_automation.views_config.run_wallet_runtime_preflight',
        return_value={
            'cdp_connected': True,
            'extension_pages_visible': True,
            'supported': True,
            'unsupported_reason': '',
            'pages': [{'page_kind': 'unknown', 'url': 'chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html'}],
        },
    )
    @patch('apps.ui_automation.views_config.prepare_wallet_browser_session')
    def test_wallet_browser_config_crud_and_prepare_session(
        self,
        mock_prepare_wallet_browser_session,
        mock_run_wallet_runtime_preflight,
    ):
        mock_prepare_wallet_browser_session.return_value = SimpleNamespace(
            id=99,
            wallet_provider='metamask',
            launch_mode='global_profile',
            debugger_address='127.0.0.1:9222',
            cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            runtime_user_data_dir=r'C:\Temp\testhub_wallet_profiles\session-99',
            profile_directory='Default',
            status='running',
        )

        create_response = self.client.post(
            '/api/ui-automation/config/wallet-browser/',
            data={
                'name': 'Chrome MetaMask',
                'wallet_provider': 'metamask',
                'chrome_executable_path': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'user_data_dir': r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
                'profile_directory': 'Default',
                'launch_mode': 'global_profile',
                'remote_debugging_port': 9222,
                'force_close_existing_chrome': True,
                'is_active': True,
            },
            content_type='application/json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(WalletBrowserConfig.objects.count(), 1)
        self.assertEqual(WalletBrowserConfig.objects.get().launch_mode, 'global_profile')

        prepare_response = self.client.post(
            '/api/ui-automation/config/wallet-browser/prepare_session/',
            data={'force_close_existing_chrome': False},
            content_type='application/json',
        )

        self.assertEqual(prepare_response.status_code, 200)
        self.assertEqual(prepare_response.json()['wallet_provider'], 'metamask')
        self.assertEqual(prepare_response.json()['debugger_address'], '127.0.0.1:9222')
        self.assertEqual(prepare_response.json()['launch_mode'], 'global_profile')
        self.assertTrue(prepare_response.json()['cdp_connected'])
        self.assertTrue(prepare_response.json()['extension_pages_visible'])
        self.assertTrue(prepare_response.json()['supported'])
        self.assertEqual(
            prepare_response.json()['runtime_user_data_dir'],
            r'C:\Temp\testhub_wallet_profiles\session-99',
        )
        mock_prepare_wallet_browser_session.assert_called_once()
        mock_run_wallet_runtime_preflight.assert_called_once()

    @patch('apps.ui_automation.views_config.is_default_chrome_user_data_dir', return_value=False)
    @patch(
        'apps.ui_automation.views_config.probe_wallet_cdp_capabilities',
        return_value={
            'cdp_connected': True,
            'extension_pages_visible': True,
            'extension_page_urls': ['chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html'],
            'unsupported_reason': '',
        },
    )
    @patch('apps.ui_automation.views_config.is_supported_chrome_executable', return_value=True)
    @patch('apps.ui_automation.views_config.resolve_metamask_extension_id', return_value='nkbihfbeogaeaoehlefnkodbefgpgknn')
    @patch('apps.ui_automation.views_config.Path.exists', return_value=True)
    def test_wallet_browser_config_test_connection_returns_validation_result(
        self,
        mock_path_exists,
        mock_resolve_metamask_extension_id,
        mock_is_supported_chrome_executable,
        mock_probe_wallet_cdp_capabilities,
        mock_is_default_chrome_user_data_dir,
    ):
        config = WalletBrowserConfig.objects.create(
            name='Chrome MetaMask',
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            launch_mode='runtime_clone',
            remote_debugging_port=9222,
            force_close_existing_chrome=True,
            is_active=True,
            created_by=self.user,
        )

        response = self.client.post(
            f'/api/ui-automation/config/wallet-browser/{config.id}/test_connection/',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['wallet_provider'], 'metamask')
        self.assertEqual(payload['launch_mode'], 'runtime_clone')
        self.assertEqual(payload['metamask_extension_id'], 'nkbihfbeogaeaoehlefnkodbefgpgknn')
        self.assertFalse(payload['uses_default_chrome_user_data_dir'])
        self.assertTrue(payload['chrome_executable_exists'])
        self.assertTrue(payload['browser_supported'])
        self.assertTrue(payload['user_data_dir_exists'])
        self.assertTrue(payload['cdp_connected'])
        self.assertTrue(payload['extension_pages_visible'])
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['unsupported_reason'], '')
        self.assertGreaterEqual(mock_path_exists.call_count, 2)
        mock_is_supported_chrome_executable.assert_called_once_with(config.chrome_executable_path)
        mock_probe_wallet_cdp_capabilities.assert_called_once_with(
            debugger_address=f'127.0.0.1:{config.remote_debugging_port}',
            remote_debugging_port=config.remote_debugging_port,
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
        )
        mock_resolve_metamask_extension_id.assert_called_once_with(config)
        mock_is_default_chrome_user_data_dir.assert_called_once_with(config.user_data_dir)

    @patch('apps.ui_automation.views_config.requests.post')
    def test_ai_model_saved_config_test_connection_uses_saved_model_settings(self, mock_requests_post):
        mock_requests_post.return_value = SimpleNamespace(status_code=200, text='{"ok":true}')
        config = AIModelConfig.objects.create(
            name='glm-5.1',
            model_type='other',
            role='browser_use_text',
            model_name='glm-5.1',
            api_key='test-api-key',
            base_url='https://api.z.ai/api/coding/paas/v4',
            is_active=True,
            created_by=self.user,
        )

        response = self.client.post(
            f'/api/ui-automation/ai-models/{config.id}/test_connection/',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], '连接成功')
        mock_requests_post.assert_called_once()
        call_args, call_kwargs = mock_requests_post.call_args
        self.assertEqual(call_args[0], 'https://api.z.ai/api/coding/paas/v4/chat/completions')
        self.assertEqual(call_kwargs['json']['model'], 'glm-5.1')

    @patch(
        'apps.ui_automation.views_config.run_wallet_runtime_preflight',
        return_value={
            'cdp_connected': True,
            'extension_pages_visible': True,
            'supported': True,
            'unsupported_reason': '',
            'pages': [{'page_kind': 'unknown', 'url': 'chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html'}],
        },
    )
    @patch('apps.ui_automation.views.prepare_wallet_browser_session')
    @patch('threading.Thread')
    def test_run_adhoc_persists_wallet_metadata(
        self,
        mock_thread,
        mock_prepare_wallet_browser_session,
        mock_run_wallet_runtime_preflight,
    ):
        thread_instance = mock_thread.return_value
        thread_instance.start.return_value = None
        mock_prepare_wallet_browser_session.return_value = WalletSession.objects.create(
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            launch_mode='runtime_clone',
            remote_debugging_port=9222,
            debugger_address='127.0.0.1:9222',
            cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            runtime_user_data_dir=r'C:\Temp\wallet-session',
            status='running',
            started_by=self.user,
        )
        fake_ai_agent = ModuleType('apps.ui_automation.ai_agent')
        fake_ai_agent.run_full_process_sync = lambda *args, **kwargs: None

        with patch.dict('sys.modules', {'apps.ui_automation.ai_agent': fake_ai_agent}):
            response = self.client.post(
                '/api/ui-automation/ai-execution-records/run_adhoc/',
                data={
                    'task_description': 'Connect wallet and sign message',
                    'execution_mode': 'text',
                    'enable_gif': False,
                    'wallet_mode': True,
                    'wallet_provider': 'metamask',
                    'wallet_target_chain': 'Ethereum Mainnet',
                    'wallet_force_close_existing_chrome': False,
                },
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        execution_record = AIExecutionRecord.objects.get(id=response.json()['execution_id'])
        self.assertTrue(execution_record.wallet_mode)
        self.assertEqual(execution_record.wallet_provider, 'metamask')
        self.assertEqual(execution_record.wallet_target_chain, 'Ethereum Mainnet')
        mock_prepare_wallet_browser_session.assert_called_once()
        mock_run_wallet_runtime_preflight.assert_called_once()


class WalletBrowserConfigApiTransactionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(username='wallet-api-transaction-user', password='test-password')
        self.client.force_login(self.user)

    @patch('threading.Thread')
    def test_run_adhoc_without_wallet_does_not_crash_on_missing_wallet_context(self, mock_thread):
        class ImmediateThread:
            def __init__(self, target=None, args=None, kwargs=None):
                self.target = target
                self.args = args or ()
                self.kwargs = kwargs or {}
                self.daemon = False

            def start(self):
                if self.target:
                    self.target(*self.args, **self.kwargs)

        mock_thread.side_effect = lambda target=None, args=(), kwargs=None: ImmediateThread(
            target=target,
            args=args,
            kwargs=kwargs,
        )

        fake_ai_agent = ModuleType('apps.ui_automation.ai_agent')
        fake_ai_agent.run_full_process_sync = lambda *args, **kwargs: None

        with patch.dict('sys.modules', {'apps.ui_automation.ai_agent': fake_ai_agent}):
            response = self.client.post(
                '/api/ui-automation/ai-execution-records/run_adhoc/',
                data={
                    'task_description': 'Open example.com and finish successfully',
                    'execution_mode': 'text',
                    'enable_gif': False,
                    'wallet_mode': False,
                },
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        execution_record = AIExecutionRecord.objects.get(id=response.json()['execution_id'])
        self.assertEqual(execution_record.status, 'passed')
        self.assertFalse(execution_record.wallet_mode)
        self.assertNotIn('wallet_context', execution_record.logs)

    @patch(
        'apps.ui_automation.views_config.run_wallet_runtime_preflight',
        return_value={
            'cdp_connected': True,
            'extension_pages_visible': True,
            'supported': True,
            'unsupported_reason': '',
            'pages': [{'page_kind': 'unknown', 'url': 'chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html'}],
        },
    )
    @patch('threading.Thread')
    def test_run_adhoc_wallet_callbacks_do_not_use_sync_to_async(
        self,
        mock_thread,
        mock_run_wallet_runtime_preflight,
    ):
        class ImmediateThread:
            def __init__(self, target=None, args=None, kwargs=None):
                self.target = target
                self.args = args or ()
                self.kwargs = kwargs or {}
                self.daemon = False

            def start(self):
                if self.target:
                    self.target(*self.args, **self.kwargs)

        mock_thread.side_effect = lambda target=None, args=(), kwargs=None: ImmediateThread(
            target=target,
            args=args,
            kwargs=kwargs,
        )

        wallet_action_calls = []

        def fake_prepare_wallet_browser_session(started_by=None, force_close_existing_chrome=None):
            return WalletSession.objects.create(
                wallet_provider='metamask',
                chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
                profile_directory='Default',
                launch_mode='runtime_clone',
                remote_debugging_port=9222,
                runtime_user_data_dir=r'C:\Temp\wallet-session',
                cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
                debugger_address='127.0.0.1:9222',
                metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
                status='running',
                started_by=started_by,
            )

        def fake_record_wallet_action(*args, **kwargs):
            wallet_action_calls.append({'args': args, 'kwargs': kwargs})
            return None

        def fake_sync_to_async(*args, **kwargs):
            raise AssertionError('run_adhoc callbacks should not use sync_to_async')

        fake_ai_agent = ModuleType('apps.ui_automation.ai_agent')

        def fake_run_full_process_sync(
            task_description,
            analysis_callback,
            step_callback,
            should_stop,
            **kwargs,
        ):
            planned_tasks = [
                {'id': 1, 'description': 'Connect wallet to the site', 'status': 'pending'}
            ]
            self.assertFalse(asyncio.run(should_stop()))
            asyncio.run(analysis_callback(planned_tasks))
            asyncio.run(step_callback({'type': 'log', 'content': 'wallet log\n'}))
            asyncio.run(step_callback({'task_id': 1, 'status': 'completed'}))
            return None

        fake_ai_agent.run_full_process_sync = fake_run_full_process_sync

        with (
            patch.dict('sys.modules', {'apps.ui_automation.ai_agent': fake_ai_agent}),
            patch('apps.ui_automation.views.prepare_wallet_browser_session', side_effect=fake_prepare_wallet_browser_session),
            patch('apps.ui_automation.views.record_wallet_action', side_effect=fake_record_wallet_action),
            patch('asgiref.sync.sync_to_async', side_effect=fake_sync_to_async),
            patch('apps.ui_automation.views.AIExecutionRecordViewSet._process_gif_recording', return_value=None),
        ):
            response = self.client.post(
                '/api/ui-automation/ai-execution-records/run_adhoc/',
                data={
                    'task_description': 'Connect wallet and finish successfully',
                    'execution_mode': 'text',
                    'enable_gif': False,
                    'wallet_mode': True,
                    'wallet_provider': 'metamask',
                    'wallet_target_chain': 'Ethereum Mainnet',
                },
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        execution_record = AIExecutionRecord.objects.get(id=response.json()['execution_id'])
        self.assertEqual(execution_record.status, 'passed')
        self.assertEqual(execution_record.wallet_session.wallet_provider, 'metamask')
        self.assertEqual(execution_record.planned_tasks[0]['status'], 'completed')
        self.assertIn('wallet log', execution_record.logs)
        self.assertEqual(len(wallet_action_calls), 1)
        mock_run_wallet_runtime_preflight.assert_called_once()

    @patch(
        'apps.ui_automation.views_config.run_wallet_runtime_preflight',
        return_value={
            'cdp_connected': True,
            'extension_pages_visible': True,
            'supported': True,
            'unsupported_reason': '',
            'pages': [{'page_kind': 'unknown', 'url': 'chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/home.html'}],
        },
    )
    @patch('threading.Thread')
    def test_run_adhoc_wallet_callbacks_persist_wallet_action_logs_from_async_context(
        self,
        mock_thread,
        mock_run_wallet_runtime_preflight,
    ):
        class ImmediateThread:
            def __init__(self, target=None, args=None, kwargs=None):
                self.target = target
                self.args = args or ()
                self.kwargs = kwargs or {}
                self.daemon = False

            def start(self):
                if self.target:
                    self.target(*self.args, **self.kwargs)

        mock_thread.side_effect = lambda target=None, args=(), kwargs=None: ImmediateThread(
            target=target,
            args=args,
            kwargs=kwargs,
        )

        def fake_prepare_wallet_browser_session(started_by=None, force_close_existing_chrome=None):
            return WalletSession.objects.create(
                wallet_provider='metamask',
                chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
                profile_directory='Default',
                launch_mode='runtime_clone',
                remote_debugging_port=9222,
                runtime_user_data_dir=r'C:\Temp\wallet-session',
                cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
                debugger_address='127.0.0.1:9222',
                metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
                status='running',
                started_by=started_by,
            )

        def fake_sync_to_async(*args, **kwargs):
            raise AssertionError('run_adhoc wallet callbacks should not require sync_to_async')

        fake_ai_agent = ModuleType('apps.ui_automation.ai_agent')

        def fake_run_full_process_sync(
            task_description,
            analysis_callback,
            step_callback,
            should_stop,
            **kwargs,
        ):
            planned_tasks = [
                {'id': 1, 'description': 'Connect wallet to the site', 'status': 'pending'}
            ]
            self.assertFalse(asyncio.run(should_stop()))
            asyncio.run(analysis_callback(planned_tasks))
            asyncio.run(step_callback({'task_id': 1, 'status': 'completed'}))
            return None

        fake_ai_agent.run_full_process_sync = fake_run_full_process_sync

        with (
            patch.dict('sys.modules', {'apps.ui_automation.ai_agent': fake_ai_agent}),
            patch('apps.ui_automation.views.prepare_wallet_browser_session', side_effect=fake_prepare_wallet_browser_session),
            patch('asgiref.sync.sync_to_async', side_effect=fake_sync_to_async),
            patch('apps.ui_automation.views.AIExecutionRecordViewSet._process_gif_recording', return_value=None),
        ):
            response = self.client.post(
                '/api/ui-automation/ai-execution-records/run_adhoc/',
                data={
                    'task_description': 'Connect wallet and finish successfully',
                    'execution_mode': 'text',
                    'enable_gif': False,
                    'wallet_mode': True,
                    'wallet_provider': 'metamask',
                    'wallet_target_chain': 'Ethereum Mainnet',
                },
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        execution_record = AIExecutionRecord.objects.get(id=response.json()['execution_id'])
        self.assertEqual(execution_record.status, 'passed')
        self.assertEqual(execution_record.planned_tasks[0]['status'], 'completed')
        self.assertEqual(
            WalletActionLog.objects.filter(execution_record=execution_record, action_name='connect_wallet').count(),
            1,
        )
        mock_run_wallet_runtime_preflight.assert_called_once()

    @patch('threading.Thread')
    def test_run_adhoc_restores_async_unsafe_env_flag(self, mock_thread):
        class ImmediateThread:
            def __init__(self, target=None, args=None, kwargs=None):
                self.target = target
                self.args = args or ()
                self.kwargs = kwargs or {}
                self.daemon = False

            def start(self):
                if self.target:
                    self.target(*self.args, **self.kwargs)

        mock_thread.side_effect = lambda target=None, args=(), kwargs=None: ImmediateThread(
            target=target,
            args=args,
            kwargs=kwargs,
        )

        fake_ai_agent = ModuleType('apps.ui_automation.ai_agent')
        fake_ai_agent.run_full_process_sync = lambda *args, **kwargs: None
        original_value = os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)

        try:
            with (
                patch.dict('sys.modules', {'apps.ui_automation.ai_agent': fake_ai_agent}),
                patch('apps.ui_automation.views.AIExecutionRecordViewSet._process_gif_recording', return_value=None),
            ):
                response = self.client.post(
                    '/api/ui-automation/ai-execution-records/run_adhoc/',
                    data={
                        'task_description': 'Open example.com and finish successfully',
                        'execution_mode': 'text',
                        'enable_gif': False,
                        'wallet_mode': False,
                    },
                    content_type='application/json',
                )

            self.assertEqual(response.status_code, 200)
            self.assertNotIn('DJANGO_ALLOW_ASYNC_UNSAFE', os.environ)
        finally:
            if original_value is not None:
                os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = original_value
