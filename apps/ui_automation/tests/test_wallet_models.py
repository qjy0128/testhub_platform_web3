from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.ui_automation.models import (
    AIExecutionRecord,
    WalletActionLog,
    WalletBrowserConfig,
    WalletSession,
)

User = get_user_model()


class WalletBrowserConfigModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='wallet-tester', password='test-password')

    def test_wallet_browser_config_defaults(self):
        config = WalletBrowserConfig.objects.create(
            name='Primary MetaMask Config',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\wallet\AppData\Local\Google\Chrome\User Data',
            created_by=self.user,
        )

        self.assertEqual(config.profile_directory, 'Default')
        self.assertTrue(config.force_close_existing_chrome)
        self.assertEqual(config.wallet_provider, 'metamask')
        self.assertEqual(config.remote_debugging_port, 9222)
        self.assertEqual(config.launch_mode, 'runtime_clone')

    def test_only_one_active_wallet_config_allowed(self):
        WalletBrowserConfig.objects.create(
            name='Active Config',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\wallet\AppData\Local\Google\Chrome\User Data',
            is_active=True,
            created_by=self.user,
        )

        second = WalletBrowserConfig(
            name='Second Active Config',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\wallet\AppData\Local\Google\Chrome\User Data',
            is_active=True,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            second.full_clean()


class WalletExecutionRecordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='wallet-execution', password='test-password')

    def test_wallet_session_and_action_log_attach_to_ai_execution_record(self):
        session = WalletSession.objects.create(
            wallet_provider='metamask',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\wallet\AppData\Local\Google\Chrome\User Data',
            started_by=self.user,
        )

        record = AIExecutionRecord.objects.create(
            case_name='Wallet flow',
            task_description='Connect wallet and sign message',
            executed_by=self.user,
            wallet_mode=True,
            wallet_provider='metamask',
            wallet_target_chain='Ethereum Mainnet',
            wallet_session=session,
        )

        log = WalletActionLog.objects.create(
            execution_record=record,
            session=session,
            action_name='connect_wallet',
            detail_message='Wallet connected successfully',
        )

        self.assertEqual(record.wallet_session, session)
        self.assertEqual(log.execution_record, record)
        self.assertEqual(log.session, session)
