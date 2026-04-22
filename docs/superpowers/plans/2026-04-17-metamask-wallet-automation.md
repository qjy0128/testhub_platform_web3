# MetaMask Wallet Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 TestHub 在 Windows 本机上使用用户真实 Chrome Profile 执行 MetaMask + EVM 钱包自动化，并把连接钱包、切链、签名消息、发送交易确认接入现有 AI UI 自动化链路。

**Architecture:** 后端在 `apps/ui_automation` 内新增钱包配置、受控 Chrome 会话、MetaMask 适配器和运行时编排层；AI 执行入口在创建 `AIExecutionRecord` 后根据钱包模式构建 `wallet_context` 并传给 `BaseBrowserAgent`；前端复用现有配置中心和 AI 智能测试页，只增加钱包模式配置和提交流程，不新增独立模块。

**Tech Stack:** Django 4.2、Django REST Framework、MySQL migrations、Chrome Remote Debugging Protocol、browser-use/Playwright、Vue 3 + Element Plus + vue-i18n、ESLint、Django test runner

---

### Task 1: 建立钱包领域模型与迁移

**Files:**
- Create: `apps/ui_automation/tests/__init__.py`
- Create: `apps/ui_automation/tests/test_wallet_models.py`
- Modify: `apps/ui_automation/models.py`
- Create: `apps/ui_automation/migrations/0002_wallet_automation.py`
- Test: `apps/ui_automation/tests/test_wallet_models.py`

- [ ] **Step 1: 先写失败的模型测试**

```python
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
        self.user = User.objects.create_user(
            username='wallet-model-user',
            password='<TEST_USER_PASSWORD>'
        )

    def test_defaults_are_applied(self):
        config = WalletBrowserConfig.objects.create(
            name='Chrome Default',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            created_by=self.user,
        )

        self.assertEqual(config.profile_directory, 'Default')
        self.assertTrue(config.force_close_existing_chrome)
        self.assertEqual(config.wallet_provider, 'metamask')
        self.assertEqual(config.remote_debugging_port, 9222)

    def test_only_one_active_wallet_config_is_allowed(self):
        WalletBrowserConfig.objects.create(
            name='A',
            chrome_executable_path='chrome-a.exe',
            user_data_dir='user-data-a',
            is_active=True,
            created_by=self.user,
        )
        second = WalletBrowserConfig(
            name='B',
            chrome_executable_path='chrome-b.exe',
            user_data_dir='user-data-b',
            is_active=True,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            second.full_clean()


class WalletExecutionLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wallet-execution-user',
            password='<TEST_USER_PASSWORD>'
        )

    def test_wallet_session_and_action_log_can_attach_to_ai_execution(self):
        session = WalletSession.objects.create(
            wallet_provider='metamask',
            chrome_executable_path='chrome.exe',
            user_data_dir='user-data',
            profile_directory='Default',
            remote_debugging_port=9222,
            started_by=self.user,
            status='running',
        )
        execution = AIExecutionRecord.objects.create(
            case_name='Wallet Case',
            task_description='连接钱包并签名',
            status='running',
            executed_by=self.user,
            wallet_mode=True,
            wallet_provider='metamask',
            wallet_session=session,
        )
        action_log = WalletActionLog.objects.create(
            execution_record=execution,
            session=session,
            action_name='connect_wallet',
            action_status='passed',
            detail_message='connected',
        )

        self.assertEqual(execution.wallet_session, session)
        self.assertEqual(action_log.execution_record, execution)
        self.assertEqual(action_log.action_name, 'connect_wallet')
```

- [ ] **Step 2: 运行测试，确认它先失败**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_models -v 2
```

Expected:

```text
ImportError or AttributeError because WalletBrowserConfig / WalletSession / WalletActionLog / AIExecutionRecord.wallet_mode do not exist yet
```

- [ ] **Step 3: 在 `models.py` 增加钱包模型和执行记录字段**

```python
class WalletBrowserConfig(models.Model):
    WALLET_PROVIDER_CHOICES = [
        ('metamask', 'MetaMask'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    wallet_provider = models.CharField(
        max_length=50,
        choices=WALLET_PROVIDER_CHOICES,
        default='metamask',
        verbose_name='钱包提供方'
    )
    chrome_executable_path = models.CharField(max_length=500, verbose_name='Chrome 可执行路径')
    user_data_dir = models.CharField(max_length=500, verbose_name='Chrome 用户数据目录')
    profile_directory = models.CharField(max_length=100, default='Default', verbose_name='Chrome Profile 目录')
    remote_debugging_port = models.PositiveIntegerField(default=9222, verbose_name='远程调试端口')
    metamask_extension_id = models.CharField(max_length=64, blank=True, default='', verbose_name='MetaMask 扩展 ID')
    force_close_existing_chrome = models.BooleanField(default=True, verbose_name='执行前关闭现有 Chrome')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ui_wallet_browser_configs'
        verbose_name = '钱包浏览器配置'
        verbose_name_plural = '钱包浏览器配置'
        ordering = ['-updated_at']

    def clean(self):
        if self.is_active:
            qs = WalletBrowserConfig.objects.filter(is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('仅允许一个启用中的钱包浏览器配置')


class WalletSession(models.Model):
    STATUS_CHOICES = [
        ('pending', '待启动'),
        ('running', '运行中'),
        ('passed', '成功'),
        ('failed', '失败'),
    ]

    wallet_provider = models.CharField(max_length=50, default='metamask', verbose_name='钱包提供方')
    chrome_executable_path = models.CharField(max_length=500, verbose_name='Chrome 可执行路径')
    user_data_dir = models.CharField(max_length=500, verbose_name='Chrome 用户数据目录')
    profile_directory = models.CharField(max_length=100, default='Default', verbose_name='Chrome Profile 目录')
    remote_debugging_port = models.PositiveIntegerField(default=9222, verbose_name='远程调试端口')
    cdp_url = models.CharField(max_length=500, blank=True, default='', verbose_name='CDP URL')
    debugger_address = models.CharField(max_length=100, blank=True, default='', verbose_name='调试地址')
    metamask_extension_id = models.CharField(max_length=64, blank=True, default='', verbose_name='MetaMask 扩展 ID')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='启动人')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')

    class Meta:
        db_table = 'ui_wallet_sessions'
        verbose_name = '钱包会话'
        verbose_name_plural = '钱包会话'
        ordering = ['-started_at']
```

```python
class WalletActionLog(models.Model):
    ACTION_CHOICES = [
        ('connect_wallet', '连接钱包'),
        ('switch_chain', '切链'),
        ('sign_message', '签名消息'),
        ('confirm_transaction', '确认交易'),
    ]
    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('passed', '成功'),
        ('failed', '失败'),
    ]

    execution_record = models.ForeignKey(
        'AIExecutionRecord',
        on_delete=models.CASCADE,
        related_name='wallet_action_logs',
        verbose_name='AI 执行记录'
    )
    session = models.ForeignKey(
        WalletSession,
        on_delete=models.CASCADE,
        related_name='action_logs',
        verbose_name='钱包会话'
    )
    action_name = models.CharField(max_length=50, choices=ACTION_CHOICES, verbose_name='动作名称')
    action_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='动作状态')
    detail_message = models.TextField(blank=True, default='', verbose_name='详情')
    payload = models.JSONField(default=dict, verbose_name='动作入参')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'ui_wallet_action_logs'
        verbose_name = '钱包动作日志'
        verbose_name_plural = '钱包动作日志'
        ordering = ['created_at']


class AIExecutionRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '执行中'),
        ('passed', '成功'),
        ('failed', '失败'),
        ('stopped', '已停止'),
    ]

    project = models.ForeignKey(UiProject, on_delete=models.CASCADE, null=True, blank=True, verbose_name='所属项目')
    ai_case = models.ForeignKey(AICase, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联AI用例')
    case_name = models.CharField(max_length=200, verbose_name='用例名称快照')
    task_description = models.TextField(blank=True, default='', verbose_name='任务描述')
    execution_mode = models.CharField(max_length=20, choices=[('text', '文本模式')], default='text', verbose_name='执行模式')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='执行状态')
    start_time = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    duration = models.FloatField(null=True, blank=True, verbose_name='执行时长(秒)')
    logs = models.TextField(blank=True, default='', verbose_name='执行日志')
    steps_completed = models.JSONField(default=list, verbose_name='已完成步骤')
    planned_tasks = models.JSONField(default=list, verbose_name='规划任务')
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='执行人')
    gif_path = models.CharField(max_length=500, null=True, blank=True, verbose_name='GIF录制路径')
    screenshots_sequence = models.JSONField(default=list, verbose_name='截图序列')
    wallet_mode = models.BooleanField(default=False, verbose_name='是否启用钱包模式')
    wallet_provider = models.CharField(max_length=50, blank=True, default='', verbose_name='钱包提供方')
    wallet_target_chain = models.CharField(max_length=100, blank=True, default='', verbose_name='目标链')
    wallet_session = models.ForeignKey(
        WalletSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='execution_records',
        verbose_name='钱包会话'
    )
```

- [ ] **Step 4: 生成并检查迁移**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py makemigrations ui_automation
.\.venv312\Scripts\python.exe manage.py sqlmigrate ui_automation 0002
```

Expected:

```text
Create model WalletBrowserConfig
Create model WalletSession
Create model WalletActionLog
Add field wallet_mode to aiexecutionrecord
Add field wallet_provider to aiexecutionrecord
Add field wallet_target_chain to aiexecutionrecord
Add field wallet_session to aiexecutionrecord
```

- [ ] **Step 5: 重新运行模型测试**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_models -v 2
```

Expected:

```text
Ran 3 tests
OK
```

- [ ] **Step 6: 提交这一组改动**

```bash
git add apps/ui_automation/models.py apps/ui_automation/migrations/0002_wallet_automation.py apps/ui_automation/tests/__init__.py apps/ui_automation/tests/test_wallet_models.py
git commit -m "feat: add wallet automation domain models"
```

### Task 2: 实现受控 Chrome 会话服务

**Files:**
- Create: `apps/ui_automation/wallet_session.py`
- Create: `apps/ui_automation/tests/test_wallet_session_service.py`
- Test: `apps/ui_automation/tests/test_wallet_session_service.py`

- [ ] **Step 1: 先写失败的服务测试**

```python
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ui_automation.wallet_session import (
    build_chrome_launch_args,
    detect_metamask_extension_id,
    wait_for_cdp_url,
)


class WalletSessionServiceTests(SimpleTestCase):
    def test_build_chrome_launch_args_preserves_extensions(self):
        args = build_chrome_launch_args(
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9333,
        )

        command = ' '.join(args)
        self.assertIn('--user-data-dir=', command)
        self.assertIn('--profile-directory=Default', command)
        self.assertIn('--remote-debugging-port=9333', command)
        self.assertNotIn('--disable-extensions', command)

    def test_detect_metamask_extension_id_from_profile_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_dir = Path(temp_dir) / 'Default' / 'Local Extension Settings' / 'nkbihfbeogaeaoehlefnkodbefgpgknn'
            profile_dir.mkdir(parents=True)

            extension_id = detect_metamask_extension_id(temp_dir, 'Default')

            self.assertEqual(extension_id, 'nkbihfbeogaeaoehlefnkodbefgpgknn')

    @patch('apps.ui_automation.wallet_session.httpx.get')
    def test_wait_for_cdp_url_reads_websocket_debugger_url(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/test'
        }
        mock_get.return_value = response

        cdp_url = wait_for_cdp_url(9222, attempts=1, sleep_seconds=0)

        self.assertEqual(cdp_url, 'ws://127.0.0.1:9222/devtools/browser/test')
```

- [ ] **Step 2: 运行测试，确认它先失败**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_session_service -v 2
```

Expected:

```text
ImportError because wallet_session.py does not exist yet
```

- [ ] **Step 3: 创建 `wallet_session.py`，封装 Chrome 关闭、启动、CDP 检测和扩展识别**

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time

import httpx


METAMASK_KNOWN_EXTENSION_IDS = [
    'nkbihfbeogaeaoehlefnkodbefgpgknn',
]


@dataclass
class ChromeLaunchResult:
    process_id: int
    cdp_url: str
    debugger_address: str
    metamask_extension_id: str


def build_chrome_launch_args(
    chrome_executable_path: str,
    user_data_dir: str,
    profile_directory: str,
    remote_debugging_port: int,
):
    return [
        chrome_executable_path,
        f'--user-data-dir={user_data_dir}',
        f'--profile-directory={profile_directory}',
        f'--remote-debugging-port={remote_debugging_port}',
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--disable-popup-blocking',
        '--start-maximized',
    ]


def terminate_existing_chrome():
    subprocess.run(
        ['taskkill', '/F', '/IM', 'chrome.exe'],
        capture_output=True,
        text=True,
        check=False,
    )


def wait_for_cdp_url(port: int, attempts: int = 15, sleep_seconds: float = 1.0) -> str:
    endpoint = f'http://127.0.0.1:{port}/json/version'
    for _ in range(attempts):
        try:
            response = httpx.get(endpoint, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            websocket_url = data.get('webSocketDebuggerUrl')
            if websocket_url:
                return websocket_url
        except Exception:
            time.sleep(sleep_seconds)
    raise RuntimeError(f'无法从 {endpoint} 获取 CDP 地址')
```

```python
from apps.ui_automation.models import WalletBrowserConfig, WalletSession


def detect_metamask_extension_id(user_data_dir: str, profile_directory: str) -> str:
    base_path = Path(user_data_dir) / profile_directory / 'Local Extension Settings'
    if not base_path.exists():
        return ''
    for extension_id in METAMASK_KNOWN_EXTENSION_IDS:
        if (base_path / extension_id).exists():
            return extension_id
    return ''


def launch_controlled_chrome(config: WalletBrowserConfig, started_by, force_close_existing_chrome=None):
    should_force_close = config.force_close_existing_chrome
    if force_close_existing_chrome is not None:
        should_force_close = bool(force_close_existing_chrome)

    if should_force_close:
        terminate_existing_chrome()

    args = build_chrome_launch_args(
        chrome_executable_path=config.chrome_executable_path,
        user_data_dir=config.user_data_dir,
        profile_directory=config.profile_directory,
        remote_debugging_port=config.remote_debugging_port,
    )
    process = subprocess.Popen(args)
    cdp_url = wait_for_cdp_url(config.remote_debugging_port)
    extension_id = config.metamask_extension_id or detect_metamask_extension_id(
        config.user_data_dir,
        config.profile_directory,
    )
    if not extension_id:
        raise RuntimeError('未检测到 MetaMask 扩展 ID')

    return WalletSession.objects.create(
        wallet_provider=config.wallet_provider,
        chrome_executable_path=config.chrome_executable_path,
        user_data_dir=config.user_data_dir,
        profile_directory=config.profile_directory,
        remote_debugging_port=config.remote_debugging_port,
        cdp_url=cdp_url,
        debugger_address=f'127.0.0.1:{config.remote_debugging_port}',
        metamask_extension_id=extension_id,
        status='running',
        started_by=started_by,
    )
```

- [ ] **Step 4: 重新运行服务测试**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_session_service -v 2
```

Expected:

```text
Ran 3 tests
OK
```

- [ ] **Step 5: 提交这一组改动**

```bash
git add apps/ui_automation/wallet_session.py apps/ui_automation/tests/test_wallet_session_service.py
git commit -m "feat: add controlled Chrome wallet session service"
```

### Task 3: 增加 MetaMask 适配器并接入 AI Agent

**Files:**
- Create: `apps/ui_automation/wallet_adapters/__init__.py`
- Create: `apps/ui_automation/wallet_adapters/base.py`
- Create: `apps/ui_automation/wallet_adapters/metamask.py`
- Create: `apps/ui_automation/wallet_runtime.py`
- Modify: `apps/ui_automation/ai_agent.py`
- Modify: `apps/ui_automation/ai_base.py`
- Create: `apps/ui_automation/tests/test_wallet_runtime.py`
- Test: `apps/ui_automation/tests/test_wallet_runtime.py`

- [ ] **Step 1: 先写失败的运行时委派测试**

```python
from unittest.mock import AsyncMock, MagicMock

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from apps.ui_automation.wallet_runtime import WalletRuntime


class WalletRuntimeTests(SimpleTestCase):
    def test_runtime_routes_connect_wallet_to_adapter(self):
        adapter = MagicMock()
        adapter.connect_wallet = AsyncMock(return_value={'status': 'passed', 'message': 'connected'})
        runtime = WalletRuntime(adapter=adapter)

        result = async_to_sync(runtime.execute)(
            action_name='connect_wallet',
            browser_session=MagicMock(),
            payload={'target_chain': ''},
        )

        self.assertEqual(result['status'], 'passed')
        adapter.connect_wallet.assert_awaited_once()

    def test_runtime_rejects_unknown_action(self):
        runtime = WalletRuntime(adapter=MagicMock())

        with self.assertRaises(ValueError):
            async_to_sync(runtime.execute)(
                action_name='unknown',
                browser_session=MagicMock(),
                payload={},
            )
```

- [ ] **Step 2: 运行测试，确认它先失败**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_runtime -v 2
```

Expected:

```text
ImportError because wallet_runtime.py and wallet_adapters package do not exist yet
```

- [ ] **Step 3: 创建适配器基础类和 MetaMask 适配器**

```python
class BaseWalletAdapter:
    async def connect_wallet(self, browser_session, payload):
        raise NotImplementedError

    async def switch_chain(self, browser_session, payload):
        raise NotImplementedError

    async def sign_message(self, browser_session, payload):
        raise NotImplementedError

    async def confirm_transaction(self, browser_session, payload):
        raise NotImplementedError
```

```python
import asyncio


class MetaMaskAdapter(BaseWalletAdapter):
    def __init__(self, extension_id: str):
        self.extension_id = extension_id

    async def _wait_for_popup(self, browser_session, attempts: int = 20, sleep_seconds: float = 0.5):
        for _ in range(attempts):
            pages = await browser_session.browser_context.get_pages()
            for page in pages:
                current_url = await page.get_url()
                if self.extension_id in current_url:
                    return page
            await asyncio.sleep(sleep_seconds)
        raise RuntimeError('未检测到 MetaMask 弹窗')

    async def _click_first_visible(self, page, texts):
        for text in texts:
            locator = page.locator(f'text={text}')
            if await locator.count() > 0:
                await locator.first.click()
                return
        raise RuntimeError(f'未找到可点击按钮: {texts}')

    async def connect_wallet(self, browser_session, payload):
        popup = await self._wait_for_popup(browser_session)
        await self._click_first_visible(popup, ['下一步', 'Next'])
        await self._click_first_visible(popup, ['连接', 'Connect'])
        return {'status': 'passed', 'message': 'MetaMask 已连接'}

    async def switch_chain(self, browser_session, payload):
        popup = await self._wait_for_popup(browser_session)
        await self._click_first_visible(popup, ['切换网络', 'Switch network'])
        return {'status': 'passed', 'message': 'MetaMask 已切链'}

    async def sign_message(self, browser_session, payload):
        popup = await self._wait_for_popup(browser_session)
        await self._click_first_visible(popup, ['签名', 'Sign'])
        return {'status': 'passed', 'message': 'MetaMask 已签名'}

    async def confirm_transaction(self, browser_session, payload):
        popup = await self._wait_for_popup(browser_session)
        await self._click_first_visible(popup, ['确认', 'Confirm'])
        return {'status': 'passed', 'message': 'MetaMask 已确认交易'}
```

- [ ] **Step 4: 创建钱包运行时并把动作注册到 `BaseBrowserAgent`**

```python
class WalletRuntime:
    def __init__(self, adapter):
        self.adapter = adapter

    async def execute(self, action_name: str, browser_session, payload: dict):
        actions = {
            'connect_wallet': self.adapter.connect_wallet,
            'switch_chain': self.adapter.switch_chain,
            'sign_message': self.adapter.sign_message,
            'confirm_transaction': self.adapter.confirm_transaction,
        }
        if action_name not in actions:
            raise ValueError(f'Unsupported wallet action: {action_name}')
        return await actions[action_name](browser_session, payload)
```

```python
class BrowserAgent(BaseBrowserAgent):
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        self.enable_gif = enable_gif
        self.case_name = case_name or "Adhoc Task"
        self.wallet_context = wallet_context or {}
        super().__init__(execution_mode='text')
```

```python
def run_full_process_sync(
    task_description: str,
    analysis_callback=None,
    step_callback=None,
    should_stop=None,
    execution_mode='text',
    enable_gif=True,
    case_name=None,
    wallet_context=None,
):
    agent = BrowserAgent(
        execution_mode='text',
        enable_gif=enable_gif,
        case_name=case_name,
        wallet_context=wallet_context,
    )
    return asyncio.run(agent.run_full_process(task_description, analysis_callback, step_callback, should_stop))
```

- [ ] **Step 5: 在 `wallet_runtime.py`、`ai_base.py`、`ai_agent.py` 完成钱包动作注册、日志回写和钱包模式浏览器配置**

```python
from asgiref.sync import sync_to_async

from apps.ui_automation.models import WalletActionLog
from apps.ui_automation.wallet_adapters.metamask import MetaMaskAdapter


class WalletRuntime:
    def __init__(self, adapter, execution_record=None, session=None):
        self.adapter = adapter
        self.execution_record = execution_record
        self.session = session

    async def execute(self, action_name: str, browser_session, payload: dict):
        actions = {
            'connect_wallet': self.adapter.connect_wallet,
            'switch_chain': self.adapter.switch_chain,
            'sign_message': self.adapter.sign_message,
            'confirm_transaction': self.adapter.confirm_transaction,
        }
        if action_name not in actions:
            raise ValueError(f'Unsupported wallet action: {action_name}')

        action_log = None
        if self.execution_record and self.session:
            action_log = await sync_to_async(WalletActionLog.objects.create)(
                execution_record=self.execution_record,
                session=self.session,
                action_name=action_name,
                action_status='pending',
                payload=payload,
            )

        try:
            result = await actions[action_name](browser_session, payload)
            if action_log:
                action_log.action_status = result.get('status', 'passed')
                action_log.detail_message = result.get('message', '')
                await sync_to_async(action_log.save)(update_fields=['action_status', 'detail_message'])
            return result
        except Exception as exc:
            if action_log:
                action_log.action_status = 'failed'
                action_log.detail_message = str(exc)
                await sync_to_async(action_log.save)(update_fields=['action_status', 'detail_message'])
            raise


def build_wallet_runtime(wallet_context: dict) -> WalletRuntime:
    wallet_provider = wallet_context.get('wallet_provider', 'metamask')
    if wallet_provider != 'metamask':
        raise ValueError(f'Unsupported wallet provider: {wallet_provider}')

    adapter = MetaMaskAdapter(
        extension_id=wallet_context['metamask_extension_id']
    )
    return WalletRuntime(
        adapter=adapter,
        execution_record=wallet_context.get('execution_record'),
        session=wallet_context.get('wallet_session'),
    )
```

```python
from apps.ui_automation.wallet_runtime import build_wallet_runtime
from apps.ui_automation.wallet_session import build_chrome_launch_args


class BaseBrowserAgent:
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        self.execution_mode = 'text'
        self.enable_gif = enable_gif
        self.case_name = case_name or "Adhoc Task"
        self.wallet_context = wallet_context or {}
        self.wallet_runtime = None

    def _create_wallet_browser_profile(self):
        session = self.wallet_context['wallet_session']
        launch_args = build_chrome_launch_args(
            chrome_executable_path=session.chrome_executable_path,
            user_data_dir=session.user_data_dir,
            profile_directory=session.profile_directory,
            remote_debugging_port=session.remote_debugging_port,
        )[1:]
        return BrowserProfile(
            headless=False,
            disable_security=True,
            executable_path=session.chrome_executable_path,
            args=launch_args,
            cdp_url=session.cdp_url,
            remote_debugging_port=session.remote_debugging_port,
            wait_for_network_idle_page_load_time=0.2,
            minimum_wait_page_load_time=0.05,
            wait_between_actions=0.1,
            enable_default_extensions=True,
        )
```

```python
    def _create_browser_profile(self):
        if self.wallet_context.get('enabled'):
            return self._create_wallet_browser_profile()
```

```python
        controller = Controller()
        if self.wallet_context.get('enabled'):
            self.wallet_runtime = build_wallet_runtime(self.wallet_context)

            @controller.action('connect_wallet')
            async def connect_wallet(browser_session=None):
                return await self.wallet_runtime.execute(
                    action_name='connect_wallet',
                    browser_session=browser_session,
                    payload={'target_chain': self.wallet_context.get('wallet_target_chain', '')},
                )

            @controller.action('switch_chain')
            async def switch_chain(target_chain: str = '', browser_session=None):
                return await self.wallet_runtime.execute(
                    action_name='switch_chain',
                    browser_session=browser_session,
                    payload={'target_chain': target_chain or self.wallet_context.get('wallet_target_chain', '')},
                )

            @controller.action('sign_message')
            async def sign_message(browser_session=None):
                return await self.wallet_runtime.execute(
                    action_name='sign_message',
                    browser_session=browser_session,
                    payload={},
                )

            @controller.action('confirm_transaction')
            async def confirm_transaction(browser_session=None):
                return await self.wallet_runtime.execute(
                    action_name='confirm_transaction',
                    browser_session=browser_session,
                    payload={},
                )
```

```python
        if self.wallet_context.get('enabled'):
            wallet_instruction = """

[Wallet Mode]
- 钱包提供方固定为 MetaMask。
- 当页面出现连接钱包、切链、签名、交易确认时，必须调用钱包动作工具，而不是直接点击扩展弹窗。
- 可用工具只有 connect_wallet / switch_chain / sign_message / confirm_transaction。
- 如果钱包弹窗没有出现，应等待并重试，不允许跳过钱包步骤。
"""
            final_task = f"{final_task}\n{wallet_instruction}"
```

```python
class BrowserAgent(BaseBrowserAgent):
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None, wallet_context=None):
        self.enable_gif = enable_gif
        self.case_name = case_name or "Adhoc Task"
        super().__init__(
            execution_mode='text',
            enable_gif=enable_gif,
            case_name=case_name,
            wallet_context=wallet_context,
        )
```

- [ ] **Step 6: 运行运行时测试，确认委派链路可用**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_runtime -v 2
```

Expected:

```text
Ran 2 tests
OK
```

- [ ] **Step 7: 提交这一组改动**

```bash
git add apps/ui_automation/wallet_adapters/__init__.py apps/ui_automation/wallet_adapters/base.py apps/ui_automation/wallet_adapters/metamask.py apps/ui_automation/wallet_runtime.py apps/ui_automation/ai_agent.py apps/ui_automation/ai_base.py apps/ui_automation/tests/test_wallet_runtime.py
git commit -m "feat: add MetaMask runtime for AI automation"
```

### Task 4: 暴露钱包配置 API 并把钱包上下文接入 AI 执行入口

**Files:**
- Modify: `apps/ui_automation/views_config.py`
- Modify: `apps/ui_automation/urls.py`
- Modify: `apps/ui_automation/serializers.py`
- Modify: `apps/ui_automation/views.py`
- Create: `apps/ui_automation/tests/test_wallet_api.py`
- Test: `apps/ui_automation/tests/test_wallet_api.py`

- [ ] **Step 1: 先写失败的接口测试**

```python
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.ui_automation.models import AIExecutionRecord, WalletBrowserConfig, WalletSession

User = get_user_model()


class WalletApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wallet-api-user',
            password='<TEST_USER_PASSWORD>'
        )
        self.client.force_authenticate(self.user)
        self.config = WalletBrowserConfig.objects.create(
            name='Chrome Wallet',
            chrome_executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            user_data_dir=r'C:\Users\tester\AppData\Local\Google\Chrome\User Data',
            profile_directory='Default',
            remote_debugging_port=9222,
            is_active=True,
            created_by=self.user,
        )

    @patch('apps.ui_automation.views_config.launch_controlled_chrome')
    def test_prepare_session_returns_wallet_session(self, mock_launch):
        session = WalletSession.objects.create(
            wallet_provider='metamask',
            chrome_executable_path=self.config.chrome_executable_path,
            user_data_dir=self.config.user_data_dir,
            profile_directory='Default',
            remote_debugging_port=9222,
            cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
            debugger_address='127.0.0.1:9222',
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            status='running',
            started_by=self.user,
        )
        mock_launch.return_value = session

        response = self.client.post('/ui-automation/config/wallet-browser/prepare_session/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['session_id'], session.id)
        self.assertEqual(response.data['wallet_provider'], 'metamask')

    @patch('apps.ui_automation.views.run_full_process_sync')
    @patch('apps.ui_automation.views.launch_controlled_chrome')
    def test_run_adhoc_with_wallet_mode_persists_wallet_context(self, mock_launch, mock_run):
        session = WalletSession.objects.create(
            wallet_provider='metamask',
            chrome_executable_path=self.config.chrome_executable_path,
            user_data_dir=self.config.user_data_dir,
            profile_directory='Default',
            remote_debugging_port=9222,
            cdp_url='ws://127.0.0.1:9222/devtools/browser/test',
            debugger_address='127.0.0.1:9222',
            metamask_extension_id='nkbihfbeogaeaoehlefnkodbefgpgknn',
            status='running',
            started_by=self.user,
        )
        mock_launch.return_value = session
        mock_run.return_value = []

        response = self.client.post('/ui-automation/ai-execution-records/run_adhoc/', {
            'task_description': '打开 dApp 并连接钱包',
            'execution_mode': 'text',
            'enable_gif': False,
            'wallet_mode': True,
            'wallet_provider': 'metamask',
            'wallet_target_chain': 'Ethereum Mainnet',
            'wallet_force_close_existing_chrome': True,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        record = AIExecutionRecord.objects.get(id=response.data['execution_id'])
        self.assertTrue(record.wallet_mode)
        self.assertEqual(record.wallet_provider, 'metamask')
        self.assertEqual(record.wallet_target_chain, 'Ethereum Mainnet')
        self.assertEqual(record.wallet_session, session)
```

- [ ] **Step 2: 运行测试，确认接口还不存在或字段未打通**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_api -v 2
```

Expected:

```text
FAIL because /config/wallet-browser/prepare_session/ does not exist and AI execution does not persist wallet fields yet
```

- [ ] **Step 3: 在配置中心后端增加钱包浏览器配置 CRUD 和会话预检查接口**

```python
from .models import WalletBrowserConfig
from .wallet_session import launch_controlled_chrome


class WalletBrowserConfigViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        configs = WalletBrowserConfig.objects.order_by('-updated_at')
        serializer_data = [{
            'id': config.id,
            'name': config.name,
            'wallet_provider': config.wallet_provider,
            'chrome_executable_path': config.chrome_executable_path,
            'user_data_dir': config.user_data_dir,
            'profile_directory': config.profile_directory,
            'remote_debugging_port': config.remote_debugging_port,
            'metamask_extension_id': config.metamask_extension_id,
            'force_close_existing_chrome': config.force_close_existing_chrome,
            'is_active': config.is_active,
            'created_at': config.created_at,
            'updated_at': config.updated_at,
        } for config in configs]
        return Response(serializer_data)

    def create(self, request):
        data = request.data
        if data.get('is_active', True):
            WalletBrowserConfig.objects.filter(is_active=True).update(is_active=False)

        config = WalletBrowserConfig.objects.create(
            name=data['name'],
            wallet_provider=data.get('wallet_provider', 'metamask'),
            chrome_executable_path=data['chrome_executable_path'],
            user_data_dir=data['user_data_dir'],
            profile_directory=data.get('profile_directory', 'Default'),
            remote_debugging_port=data.get('remote_debugging_port', 9222),
            metamask_extension_id=data.get('metamask_extension_id', ''),
            force_close_existing_chrome=data.get('force_close_existing_chrome', True),
            is_active=data.get('is_active', True),
            created_by=request.user,
        )
        return Response({'id': config.id, 'name': config.name}, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        config = WalletBrowserConfig.objects.get(pk=pk)
        data = request.data
        if data.get('is_active', config.is_active):
            WalletBrowserConfig.objects.exclude(pk=config.pk).filter(is_active=True).update(is_active=False)

        for field in [
            'name',
            'wallet_provider',
            'chrome_executable_path',
            'user_data_dir',
            'profile_directory',
            'remote_debugging_port',
            'metamask_extension_id',
            'force_close_existing_chrome',
            'is_active',
        ]:
            if field in data:
                setattr(config, field, data[field])
        config.full_clean()
        config.save()
        return Response({'id': config.id, 'name': config.name, 'is_active': config.is_active})

    def destroy(self, request, pk=None):
        config = WalletBrowserConfig.objects.get(pk=pk)
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def prepare_session(self, request):
        config = WalletBrowserConfig.objects.filter(is_active=True).first()
        if not config:
            return Response({'error': '请先启用钱包浏览器配置'}, status=status.HTTP_400_BAD_REQUEST)

        session = launch_controlled_chrome(
            config=config,
            started_by=request.user,
            force_close_existing_chrome=request.data.get('force_close_existing_chrome'),
        )
        return Response({
            'session_id': session.id,
            'wallet_provider': session.wallet_provider,
            'debugger_address': session.debugger_address,
            'metamask_extension_id': session.metamask_extension_id,
        })
```

```python
from .views_config import (
    AIIntelligentModeConfigViewSet,
    EnvironmentConfigViewSet,
    WalletBrowserConfigViewSet,
)

router.register(r'config/wallet-browser', WalletBrowserConfigViewSet, basename='config-wallet-browser')
```

- [ ] **Step 4: 更新执行记录序列化器并在 AI 执行入口构建 `wallet_context`**

```python
class AIExecutionRecordSerializer(serializers.ModelSerializer):
    wallet_action_logs = serializers.SerializerMethodField()

    class Meta:
        model = AIExecutionRecord
        fields = [
            'id', 'project', 'project_id', 'project_name', 'ai_case', 'ai_case_id', 'ai_case_name', 'case_name',
            'task_description', 'execution_mode', 'status', 'start_time', 'end_time', 'duration',
            'logs', 'steps_completed', 'planned_tasks', 'executed_by', 'executed_by_name',
            'gif_path', 'screenshots_sequence', 'wallet_mode', 'wallet_provider',
            'wallet_target_chain', 'wallet_session', 'wallet_action_logs'
        ]
        read_only_fields = (
            'start_time', 'end_time', 'duration', 'executed_by', 'gif_path',
            'screenshots_sequence', 'wallet_session', 'wallet_action_logs'
        )

    def get_wallet_action_logs(self, obj):
        return [{
            'action_name': log.action_name,
            'action_status': log.action_status,
            'detail_message': log.detail_message,
            'payload': log.payload,
            'created_at': log.created_at,
        } for log in obj.wallet_action_logs.all()]
```

```python
from django.utils import timezone
from .models import WalletBrowserConfig
from .wallet_session import launch_controlled_chrome


def build_wallet_context(execution_record, user, request_data):
    wallet_mode = bool(request_data.get('wallet_mode'))
    if not wallet_mode:
        return None

    wallet_provider = request_data.get('wallet_provider', 'metamask')
    active_config = WalletBrowserConfig.objects.filter(
        is_active=True,
        wallet_provider=wallet_provider,
    ).first()
    if not active_config:
        raise ValueError('未找到启用中的 MetaMask 钱包浏览器配置')

    session = launch_controlled_chrome(
        config=active_config,
        started_by=user,
        force_close_existing_chrome=request_data.get('wallet_force_close_existing_chrome'),
    )
    execution_record.wallet_mode = True
    execution_record.wallet_provider = wallet_provider
    execution_record.wallet_target_chain = request_data.get('wallet_target_chain', '')
    execution_record.wallet_session = session
    execution_record.logs += '[Wallet] 钱包模式已启用，准备接入受控 Chrome。\n'
    execution_record.save(update_fields=[
        'wallet_mode', 'wallet_provider', 'wallet_target_chain', 'wallet_session', 'logs'
    ])

    return {
        'enabled': True,
        'wallet_provider': wallet_provider,
        'wallet_target_chain': execution_record.wallet_target_chain,
        'wallet_session': session,
        'metamask_extension_id': session.metamask_extension_id,
        'execution_record': execution_record,
    }


def finalize_wallet_session(execution_record, status, error_message=''):
    session = execution_record.wallet_session
    if not session:
        return
    session.status = status
    session.error_message = error_message
    session.finished_at = timezone.now()
    session.save(update_fields=['status', 'error_message', 'finished_at'])
```

```python
        wallet_context = None
        try:
            wallet_context = build_wallet_context(execution_record, request.user, request.data)
        except Exception as exc:
            execution_record.status = 'failed'
            execution_record.logs += f"[Wallet] 预检查失败: {exc}\n"
            execution_record.save(update_fields=['status', 'logs'])
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

```python
                history = run_full_process_sync(
                    task_description,
                    analysis_callback=on_analysis_complete,
                    step_callback=on_step_update,
                    should_stop=should_stop_async,
                    execution_mode=execution_mode,
                    enable_gif=enable_gif,
                    case_name=task_description[:50] if task_description else "Adhoc Task",
                    wallet_context=wallet_context,
                )
                if should_stop_sync():
                    execution_record.status = 'stopped'
                    execution_record.logs += "\n[System] 任务已由用户停止。"
                else:
                    execution_record.status, task_summary = resolve_execution_status(execution_record.planned_tasks)
                    if execution_record.status == 'passed':
                        execution_record.logs += "\n执行完成。"
                    else:
                        execution_record.logs += "\n执行结束，但存在未完成或失败的子任务。"
                execution_record.end_time = timezone.now()
                execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
                safe_save(execution_record, update_fields=['status', 'logs', 'end_time', 'duration'])
                finalize_wallet_session(execution_record, 'passed' if execution_record.status == 'passed' else 'failed')
            except Exception as e:
                execution_record.status = 'failed'
                execution_record.logs += f"\n[Wallet] 执行异常: {e}"
                safe_save(execution_record, update_fields=['status', 'logs'])
                finalize_wallet_session(execution_record, 'failed', str(e))
```

- [ ] **Step 5: 重新运行接口测试，确认 CRUD、预检查和执行入口都打通**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_api -v 2
```

Expected:

```text
Ran 2 tests
OK
```

- [ ] **Step 6: 提交这一组改动**

```bash
git add apps/ui_automation/views_config.py apps/ui_automation/urls.py apps/ui_automation/serializers.py apps/ui_automation/views.py apps/ui_automation/tests/test_wallet_api.py
git commit -m "feat: wire wallet config APIs into AI execution"
```

### Task 5: 更新配置中心与 AI 测试页的钱包模式前端

**Files:**
- Modify: `frontend/src/api/ui_automation.js`
- Modify: `frontend/src/views/configuration/AIIntelligentModeConfig.vue`
- Modify: `frontend/src/views/ui-automation/ai/AITesting.vue`
- Modify: `frontend/src/locales/lang/zh-cn/configuration.js`
- Modify: `frontend/src/locales/lang/en/configuration.js`
- Modify: `frontend/src/locales/lang/zh-cn/ui-automation.js`
- Modify: `frontend/src/locales/lang/en/ui-automation.js`
- Test: `frontend/src/views/configuration/AIIntelligentModeConfig.vue`
- Test: `frontend/src/views/ui-automation/ai/AITesting.vue`

- [ ] **Step 1: 先在前端 API 层补齐钱包配置和会话预检查方法**

```javascript
export function getWalletBrowserConfigs() {
  return request({
    url: '/ui-automation/config/wallet-browser/',
    method: 'get'
  })
}

export function createWalletBrowserConfig(data) {
  return request({
    url: '/ui-automation/config/wallet-browser/',
    method: 'post',
    data
  })
}

export function updateWalletBrowserConfig(id, data) {
  return request({
    url: `/ui-automation/config/wallet-browser/${id}/`,
    method: 'put',
    data
  })
}

export function deleteWalletBrowserConfig(id) {
  return request({
    url: `/ui-automation/config/wallet-browser/${id}/`,
    method: 'delete'
  })
}

export function prepareWalletBrowserSession(data) {
  return request({
    url: '/ui-automation/config/wallet-browser/prepare_session/',
    method: 'post',
    data,
    timeout: 120000
  })
}
```

- [ ] **Step 2: 在 AI 智能模式配置页增加钱包浏览器配置区域**

```vue
<div class="wallet-config-section">
  <div class="section-header">
    <h2>{{ $t('configuration.aiMode.walletSectionTitle') }}</h2>
    <button class="add-config-btn" @click="openWalletModal">
      {{ $t('configuration.aiMode.editWalletConfig') }}
    </button>
  </div>

  <div class="config-card" v-if="walletConfig">
    <div class="config-details">
      <div class="detail-item">
        <label>{{ $t('configuration.aiMode.walletProvider') }}:</label>
        <span>{{ walletConfig.wallet_provider }}</span>
      </div>
      <div class="detail-item">
        <label>{{ $t('configuration.aiMode.chromeExecutablePath') }}:</label>
        <span>{{ walletConfig.chrome_executable_path }}</span>
      </div>
      <div class="detail-item">
        <label>{{ $t('configuration.aiMode.userDataDir') }}:</label>
        <span>{{ walletConfig.user_data_dir }}</span>
      </div>
      <div class="detail-item">
        <label>{{ $t('configuration.aiMode.profileDirectory') }}:</label>
        <span>{{ walletConfig.profile_directory }}</span>
      </div>
    </div>
    <div class="config-actions">
      <button class="test-btn" @click="prepareWalletSession" :disabled="walletPreparing">
        {{ walletPreparing ? $t('configuration.aiMode.walletPreparing') : $t('configuration.aiMode.prepareWalletSession') }}
      </button>
    </div>
  </div>
</div>

<div v-if="showWalletModal" class="config-modal" @keydown.esc="showWalletModal = false">
  <div class="modal-content" @click.stop>
    <div class="modal-header">
      <h3>{{ $t('configuration.aiMode.editWalletConfig') }}</h3>
      <button class="close-btn" @click="showWalletModal = false">×</button>
    </div>
    <div class="modal-body">
      <form @submit.prevent="saveWalletConfig">
        <div class="form-group">
          <label>{{ $t('configuration.aiMode.chromeExecutablePath') }}</label>
          <input v-model="walletForm.chrome_executable_path" class="form-input" required>
        </div>
        <div class="form-group">
          <label>{{ $t('configuration.aiMode.userDataDir') }}</label>
          <input v-model="walletForm.user_data_dir" class="form-input" required>
        </div>
        <div class="form-group">
          <label>{{ $t('configuration.aiMode.profileDirectory') }}</label>
          <input v-model="walletForm.profile_directory" class="form-input">
        </div>
        <div class="form-group">
          <label>{{ $t('configuration.aiMode.remoteDebuggingPort') }}</label>
          <input v-model.number="walletForm.remote_debugging_port" type="number" class="form-input">
        </div>
        <div class="modal-actions">
          <button type="button" class="delete-btn" v-if="walletConfig" @click="deleteWalletConfig">
            {{ $t('configuration.common.delete') }}
          </button>
          <button type="submit" class="confirm-btn">
            {{ $t('configuration.common.save') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</div>
```

```javascript
import {
  getWalletBrowserConfigs,
  createWalletBrowserConfig,
  deleteWalletBrowserConfig,
  updateWalletBrowserConfig,
  prepareWalletBrowserSession,
} from '@/api/ui_automation'

const walletPreparing = ref(false)
const walletConfig = ref(null)
const showWalletModal = ref(false)
const walletForm = ref({
  name: 'Chrome MetaMask',
  wallet_provider: 'metamask',
  chrome_executable_path: '',
  user_data_dir: '',
  profile_directory: 'Default',
  remote_debugging_port: 9222,
  metamask_extension_id: '',
  force_close_existing_chrome: true,
  is_active: true,
})

const loadWalletConfig = async () => {
  const response = await getWalletBrowserConfigs()
  walletConfig.value = response.data.find(item => item.is_active) || response.data[0] || null
  if (walletConfig.value) {
    walletForm.value = { ...walletConfig.value }
  }
}

const openWalletModal = () => {
  showWalletModal.value = true
}

const saveWalletConfig = async () => {
  const payload = { ...walletForm.value, wallet_provider: 'metamask', is_active: true }
  if (walletConfig.value?.id) {
    await updateWalletBrowserConfig(walletConfig.value.id, payload)
    ElMessage.success(t('configuration.aiMode.walletConfigUpdated'))
  } else {
    await createWalletBrowserConfig(payload)
    ElMessage.success(t('configuration.aiMode.walletConfigCreated'))
  }
  showWalletModal.value = false
  await loadWalletConfig()
}

const deleteWalletConfig = async () => {
  if (!walletConfig.value?.id) return
  await deleteWalletBrowserConfig(walletConfig.value.id)
  walletConfig.value = null
  showWalletModal.value = false
  ElMessage.success(t('configuration.aiMode.walletConfigDeleted'))
}

const prepareWalletSession = async () => {
  walletPreparing.value = true
  try {
    const response = await prepareWalletBrowserSession({
      force_close_existing_chrome: walletForm.value.force_close_existing_chrome
    })
    ElMessage.success(t('configuration.aiMode.walletPrepared', {
      debuggerAddress: response.data.debugger_address
    }))
  } catch (error) {
    ElMessage.error(error.response?.data?.error || t('configuration.aiMode.walletPrepareFailed'))
  } finally {
    walletPreparing.value = false
  }
}

onMounted(() => {
  loadConfigs()
  loadWalletConfig()
})
```

- [ ] **Step 3: 在 AI 测试页增加钱包模式表单，并把钱包元数据一起提交**

```vue
<el-divider>{{ $t('uiAutomation.ai.walletModeTitle') }}</el-divider>

<el-form-item :label="$t('uiAutomation.ai.walletModeEnabled')">
  <el-switch
    v-model="taskForm.walletMode"
    :active-text="$t('uiAutomation.ai.on')"
    :inactive-text="$t('uiAutomation.ai.off')"
  />
</el-form-item>

<template v-if="taskForm.walletMode">
  <el-alert
    :title="$t('uiAutomation.ai.walletWarningTitle')"
    type="warning"
    :closable="false"
    style="margin-bottom: 16px;"
  >
    <template #default>
      <div>{{ $t('uiAutomation.ai.walletWarningContent') }}</div>
    </template>
  </el-alert>

  <el-form-item :label="$t('uiAutomation.ai.walletProvider')">
    <el-select v-model="taskForm.walletProvider" style="width: 100%">
      <el-option label="MetaMask" value="metamask" />
    </el-select>
  </el-form-item>

  <el-form-item :label="$t('uiAutomation.ai.walletTargetChain')">
    <el-input
      v-model="taskForm.walletTargetChain"
      :placeholder="$t('uiAutomation.ai.walletTargetChainPlaceholder')"
    />
  </el-form-item>

  <el-form-item :label="$t('uiAutomation.ai.walletForceCloseChrome')">
    <el-switch
      v-model="taskForm.walletForceCloseExistingChrome"
      :active-text="$t('uiAutomation.ai.on')"
      :inactive-text="$t('uiAutomation.ai.off')"
    />
  </el-form-item>
</template>
```

```javascript
const taskForm = reactive({
  description: '',
  enableGif: true,
  walletMode: false,
  walletProvider: 'metamask',
  walletTargetChain: '',
  walletForceCloseExistingChrome: true,
})

const handleRun = async () => {
  running.value = true
  analyzing.value = true
  logs.value = t('uiAutomation.ai.messages.initAgent')
  plannedTasks.value = []

  try {
    const response = await runAdhocAITask({
      task_description: taskForm.description,
      execution_mode: 'text',
      enable_gif: taskForm.enableGif,
      wallet_mode: taskForm.walletMode,
      wallet_provider: taskForm.walletProvider,
      wallet_target_chain: taskForm.walletTargetChain,
      wallet_force_close_existing_chrome: taskForm.walletForceCloseExistingChrome,
    })
    currentExecutionId.value = response.data.execution_id
    ElMessage.success(t('uiAutomation.ai.messages.startSuccess'))
    pollLogs()
  } catch (error) {
    ElMessage.error(t('uiAutomation.ai.messages.startFailed') + ': ' + (error.response?.data?.error || error.message))
    running.value = false
    analyzing.value = false
  }
}
```

- [ ] **Step 4: 补齐中英文翻译并跑前端 lint**

```javascript
aiMode: {
  walletSectionTitle: 'MetaMask 钱包浏览器配置',
  editWalletConfig: '编辑钱包配置',
  walletProvider: '钱包提供方',
  chromeExecutablePath: 'Chrome 可执行路径',
  userDataDir: 'Chrome 用户数据目录',
  profileDirectory: 'Profile 目录',
  remoteDebuggingPort: '远程调试端口',
  prepareWalletSession: '检测 MetaMask',
  walletPreparing: '检测中...',
  walletPrepared: '钱包浏览器已接入，调试地址：{debuggerAddress}',
  walletPrepareFailed: 'MetaMask 检测失败',
  walletConfigCreated: '钱包配置创建成功',
  walletConfigUpdated: '钱包配置更新成功',
  walletConfigDeleted: '钱包配置删除成功'
}
```

```javascript
ai: {
  walletModeTitle: '钱包模式',
  walletModeEnabled: '启用 MetaMask 钱包模式',
  walletProvider: '钱包提供方',
  walletTargetChain: '目标链',
  walletTargetChainPlaceholder: '例如：Ethereum Mainnet / Base / Arbitrum One',
  walletForceCloseChrome: '执行前关闭现有 Chrome',
  walletWarningTitle: '钱包模式会关闭当前所有 Chrome 窗口',
  walletWarningContent: '执行开始后，系统会使用你当前配置的 Chrome 用户目录重新拉起浏览器，并接管 MetaMask 弹窗。'
}
```

```javascript
aiMode: {
  walletSectionTitle: 'MetaMask Wallet Browser Configuration',
  editWalletConfig: 'Edit Wallet Configuration',
  walletProvider: 'Wallet Provider',
  chromeExecutablePath: 'Chrome Executable Path',
  userDataDir: 'Chrome User Data Directory',
  profileDirectory: 'Profile Directory',
  remoteDebuggingPort: 'Remote Debugging Port',
  prepareWalletSession: 'Detect MetaMask',
  walletPreparing: 'Checking...',
  walletPrepared: 'Wallet browser connected, debugger address: {debuggerAddress}',
  walletPrepareFailed: 'MetaMask detection failed',
  walletConfigCreated: 'Wallet configuration created',
  walletConfigUpdated: 'Wallet configuration updated',
  walletConfigDeleted: 'Wallet configuration deleted'
}
```

```javascript
ai: {
  walletModeTitle: 'Wallet Mode',
  walletModeEnabled: 'Enable MetaMask Wallet Mode',
  walletProvider: 'Wallet Provider',
  walletTargetChain: 'Target Chain',
  walletTargetChainPlaceholder: 'Example: Ethereum Mainnet / Base / Arbitrum One',
  walletForceCloseChrome: 'Close existing Chrome before run',
  walletWarningTitle: 'Wallet mode will close all current Chrome windows',
  walletWarningContent: 'When execution starts, the system will relaunch Chrome with your configured user profile and take over MetaMask popups.'
}
```

Run:

```powershell
cd frontend
npm run lint -- src/views/configuration/AIIntelligentModeConfig.vue src/views/ui-automation/ai/AITesting.vue src/api/ui_automation.js src/locales/lang/zh-cn/configuration.js src/locales/lang/en/configuration.js src/locales/lang/zh-cn/ui-automation.js src/locales/lang/en/ui-automation.js
```

Expected:

```text
ESLint finished without errors
```

- [ ] **Step 5: 提交这一组改动**

```bash
git add frontend/src/api/ui_automation.js frontend/src/views/configuration/AIIntelligentModeConfig.vue frontend/src/views/ui-automation/ai/AITesting.vue frontend/src/locales/lang/zh-cn/configuration.js frontend/src/locales/lang/en/configuration.js frontend/src/locales/lang/zh-cn/ui-automation.js frontend/src/locales/lang/en/ui-automation.js
git commit -m "feat: add MetaMask wallet mode UI"
```

### Task 6: 做端到端验证并补充运行说明

**Files:**
- Create: `docs/superpowers/runbooks/metamask-wallet-automation-smoke-test.md`
- Test: `apps/ui_automation/tests/test_wallet_models.py`
- Test: `apps/ui_automation/tests/test_wallet_session_service.py`
- Test: `apps/ui_automation/tests/test_wallet_runtime.py`
- Test: `apps/ui_automation/tests/test_wallet_api.py`
- Test: `frontend/src/views/configuration/AIIntelligentModeConfig.vue`
- Test: `frontend/src/views/ui-automation/ai/AITesting.vue`

- [ ] **Step 1: 写一份最小运行手册，避免执行者忘记 MetaMask 前置条件**

````markdown
# MetaMask Wallet Automation Smoke Test

## 前置条件

1. Windows 本机已安装 Chrome。
2. `Default` Profile 中已安装并登录 MetaMask。
3. MetaMask 已提前解锁。
4. 测试前关闭所有 Chrome 窗口。

## 配置步骤

1. 打开 `配置中心 -> AI智能模式配置`。
2. 填写钱包浏览器配置：
   - `chrome_executable_path`
   - `user_data_dir`
   - `profile_directory`
   - `remote_debugging_port`
3. 点击“检测 MetaMask”，确认看到调试地址返回。

## 烟雾测试任务

在 `AI 智能测试` 页面输入：

```text
访问目标 dApp，点击 Connect Wallet，选择 MetaMask，连接钱包，切换到 Ethereum Mainnet，签名消息，并发起一笔测试交易直到 MetaMask 确认页。
```

## 预期结果

- `AIExecutionRecord.status` 为 `passed` 或在失败时带有明确钱包错误
- `wallet_action_logs` 至少出现一条结构化记录
- `WalletSession.status` 与执行结果同步
````

- [ ] **Step 2: 一次性跑完后端钱包相关测试**

Run:

```powershell
.\.venv312\Scripts\python.exe manage.py test apps.ui_automation.tests.test_wallet_models apps.ui_automation.tests.test_wallet_session_service apps.ui_automation.tests.test_wallet_runtime apps.ui_automation.tests.test_wallet_api -v 2
```

Expected:

```text
Ran 10 tests
OK
```

- [ ] **Step 3: 跑前端 lint，确认配置页和 AI 测试页都能过静态检查**

Run:

```powershell
cd frontend
npm run lint -- src/views/configuration/AIIntelligentModeConfig.vue src/views/ui-automation/ai/AITesting.vue src/api/ui_automation.js src/locales/lang/zh-cn/configuration.js src/locales/lang/en/configuration.js src/locales/lang/zh-cn/ui-automation.js src/locales/lang/en/ui-automation.js
```

Expected:

```text
ESLint finished without errors
```

- [ ] **Step 4: 手工做一次钱包模式验证**

Run:

```text
1. 在配置中心保存一条启用中的 MetaMask 钱包浏览器配置。
2. 点击“检测 MetaMask”，确认扩展 ID 与调试地址返回成功。
3. 在 AI 测试页开启钱包模式，提交一条包含“连接钱包、切链、签名、发交易确认”的任务。
4. 打开 Django Admin 或数据库，确认 `ui_wallet_sessions`、`ui_wallet_action_logs`、`ui_ai_execution_records` 的钱包字段都有记录。
```

Expected:

```text
- Chrome 被重新拉起到受控模式
- MetaMask 弹窗由结构化动作处理
- 执行记录里能看到 wallet_action_logs
- 失败时不会静默回退到普通 AI 点击模式
```

- [ ] **Step 5: 提交验证文档**

```bash
git add docs/superpowers/runbooks/metamask-wallet-automation-smoke-test.md
git commit -m "docs: add MetaMask wallet automation smoke test runbook"
```
