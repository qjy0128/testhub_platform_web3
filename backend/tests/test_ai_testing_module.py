from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from types import SimpleNamespace
from unittest.mock import patch

from apps.core.models import UnifiedAuditLog
from apps.ai_testing.models import AiTestingRun, AiTestingTask
from apps.ai_testing.services import execute_ai_testing_run, map_execution_mode, run_pending_ai_testing_runs
from apps.projects.models import Project, ProjectMember
from apps.requirement_analysis.models import AIModelConfig


class AiTestingModuleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.project = Project.objects.create(name='AI Testing Project', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member, role='tester')

    def test_project_member_can_list_ai_testing_tasks_but_outsider_cannot(self):
        AiTestingTask.objects.create(
            project=self.project,
            name='Checkout flow',
            instruction='Open checkout\nPay with test card',
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        member_response = self.client.get('/api/ai-testing/tasks/')
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.data['count'], 1)

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/ai-testing/tasks/')
        self.assertEqual(outsider_response.status_code, 200)
        self.assertEqual(outsider_response.data['count'], 0)

    def test_owner_can_create_run_and_cancel_it(self):
        self.client.force_authenticate(user=self.owner)

        create_response = self.client.post(
            '/api/ai-testing/tasks/',
            {
                'project': self.project.id,
                'name': 'Login smoke',
                'instruction': 'Open login page\nSubmit valid credentials',
                'target_url': 'https://example.test/login',
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)

        run_response = self.client.post(
            f"/api/ai-testing/tasks/{create_response.data['id']}/run/",
            {},
            format='json',
        )
        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(run_response.data['status'], AiTestingRun.STATUS_PENDING)
        self.assertEqual(len(run_response.data['planned_steps']), 2)

        cancel_response = self.client.post(
            f"/api/ai-testing/runs/{run_response.data['id']}/cancel/",
            {},
            format='json',
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data['status'], AiTestingRun.STATUS_CANCELLED)
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='ai_testing',
                object_type='ai_testing_run',
                object_id=str(run_response.data['id']),
                actor=self.owner,
                metadata__operation='create_run',
            ).exists()
        )
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='ai_testing',
                object_type='ai_testing_run',
                object_id=str(run_response.data['id']),
                actor=self.owner,
                metadata__operation='cancel_run',
            ).exists()
        )

    def test_start_immediately_dispatches_ai_testing_run(self):
        task = AiTestingTask.objects.create(
            project=self.project,
            name='Checkout flow',
            instruction='Open checkout\nPay with test card',
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.owner)

        with patch('apps.ai_testing.services.dispatch_ai_testing_run') as dispatch:
            response = self.client.post(
                f'/api/ai-testing/tasks/{task.id}/run/',
                {'start_immediately': True},
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], AiTestingRun.STATUS_RUNNING)
        self.assertIsNotNone(response.data['started_at'])
        dispatch.assert_called_once()

    def test_pending_run_can_be_started_from_run_endpoint(self):
        task = AiTestingTask.objects.create(
            project=self.project,
            name='Login flow',
            instruction='Open login page',
            created_by=self.owner,
        )
        run = AiTestingRun.objects.create(
            task=task,
            project=self.project,
            instruction_snapshot=task.instruction,
            execution_mode=task.execution_mode,
            planned_steps=[{'id': 1, 'index': 1, 'description': 'Open login page', 'title': 'Open login page', 'status': 'pending'}],
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.owner)

        with patch('apps.ai_testing.services.dispatch_ai_testing_run') as dispatch:
            response = self.client.post(f'/api/ai-testing/runs/{run.id}/start/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], AiTestingRun.STATUS_RUNNING)
        dispatch.assert_called_once_with(run.id)

    def test_execute_ai_testing_run_persists_callback_updates(self):
        task = AiTestingTask.objects.create(
            project=self.project,
            name='Smoke flow',
            instruction='Open home page',
            target_url='https://example.test',
            created_by=self.owner,
        )
        run = AiTestingRun.objects.create(
            task=task,
            project=self.project,
            status=AiTestingRun.STATUS_RUNNING,
            instruction_snapshot=task.instruction,
            target_url_snapshot=task.target_url,
            execution_mode=task.execution_mode,
            planned_steps=[],
            artifacts={'screenshots': [], 'recordings': [], 'reports': []},
            created_by=self.owner,
            started_at=timezone.now(),
        )

        def fake_runner(task_description, analysis_callback=None, step_callback=None, should_stop=None, **kwargs):
            self.assertIn('https://example.test', task_description)
            analysis_callback([{'id': 1, 'description': 'Open home page', 'status': 'pending'}])
            step_callback({'task_id': 1, 'status': 'completed'})
            step_callback({'type': 'log', 'content': '[Agent] done\n'})
            return SimpleNamespace(steps=[SimpleNamespace(action='open-page')])

        execute_ai_testing_run(run.id, runner=fake_runner, manage_connections=False)

        run.refresh_from_db()
        self.assertEqual(run.status, AiTestingRun.STATUS_SUCCEEDED)
        self.assertEqual(run.planned_steps[0]['status'], 'completed')
        self.assertEqual(run.executed_steps[0]['task_id'], 1)
        self.assertEqual(run.artifacts['history_steps'][0]['action'], 'open-page')

    def test_pending_queue_runner_consumes_pending_runs(self):
        task = AiTestingTask.objects.create(
            project=self.project,
            name='Queued smoke',
            instruction='Open home page',
            created_by=self.owner,
        )
        run = AiTestingRun.objects.create(
            task=task,
            project=self.project,
            status=AiTestingRun.STATUS_PENDING,
            instruction_snapshot=task.instruction,
            execution_mode=task.execution_mode,
            planned_steps=[{'id': 1, 'index': 1, 'description': 'Open home page', 'title': 'Open home page', 'status': 'pending'}],
            artifacts={'screenshots': [], 'recordings': [], 'reports': []},
            created_by=self.owner,
        )

        def fake_runner(task_description, analysis_callback=None, step_callback=None, should_stop=None, **kwargs):
            step_callback({'task_id': 1, 'status': 'completed'})
            return SimpleNamespace(steps=[])

        result = run_pending_ai_testing_runs(runner=fake_runner, manage_connections=False)

        run.refresh_from_db()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual(run.status, AiTestingRun.STATUS_SUCCEEDED)

    def test_run_pending_endpoint_consumes_only_accessible_runs(self):
        task = AiTestingTask.objects.create(
            project=self.project,
            name='Queued smoke',
            instruction='Open home page',
            created_by=self.owner,
        )
        run = AiTestingRun.objects.create(
            task=task,
            project=self.project,
            status=AiTestingRun.STATUS_PENDING,
            instruction_snapshot=task.instruction,
            execution_mode=task.execution_mode,
            planned_steps=[{'id': 1, 'index': 1, 'description': 'Open home page', 'title': 'Open home page', 'status': 'pending'}],
            artifacts={'screenshots': [], 'recordings': [], 'reports': []},
            created_by=self.owner,
        )
        hidden_project = Project.objects.create(name='Hidden AI Project', owner=self.outsider)
        hidden_task = AiTestingTask.objects.create(
            project=hidden_project,
            name='Hidden queued smoke',
            instruction='Open hidden page',
            created_by=self.outsider,
        )
        hidden_run = AiTestingRun.objects.create(
            task=hidden_task,
            project=hidden_project,
            status=AiTestingRun.STATUS_PENDING,
            instruction_snapshot=hidden_task.instruction,
            execution_mode=hidden_task.execution_mode,
            created_by=self.outsider,
        )

        def fake_runner(task_description, analysis_callback=None, step_callback=None, should_stop=None, **kwargs):
            step_callback({'task_id': 1, 'status': 'completed'})
            return SimpleNamespace(steps=[])

        self.client.force_authenticate(user=self.member)
        with patch('apps.ai_testing.services.load_browser_runner', return_value=fake_runner):
            response = self.client.post('/api/ai-testing/runs/run_pending/', {'limit': 10}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        run.refresh_from_db()
        hidden_run.refresh_from_db()
        self.assertEqual(run.status, AiTestingRun.STATUS_SUCCEEDED)
        self.assertEqual(hidden_run.status, AiTestingRun.STATUS_PENDING)
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='ai_testing',
                object_type='ai_testing_queue',
                actor=self.member,
                metadata__operation='run_pending',
            ).exists()
        )

    def test_browser_vision_mode_maps_to_browser_use_vision(self):
        self.assertEqual(map_execution_mode(AiTestingTask.MODE_BROWSER_TEXT), 'text')
        self.assertEqual(map_execution_mode(AiTestingTask.MODE_BROWSER_VISION), 'vision')
        self.assertEqual(map_execution_mode('browser_use_vision'), 'vision')


class BrowserAiModeConfigTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='config-user', password='pass', is_staff=True)
        self.client.force_authenticate(user=self.user)

    def _create_config(self, name, role, is_active=True):
        return self.client.post(
            '/api/ui-automation/ai-models/',
            {
                'name': name,
                'model_type': 'deepseek',
                'role': role,
                'model_name': 'deepseek-chat',
                'api_key': 'test-key',
                'base_url': 'https://example.test/v1',
                'is_active': is_active,
            },
            format='json',
        )

    def test_text_and_vision_model_configs_have_independent_active_slots(self):
        text_response = self._create_config('Text config', 'browser_use_text')
        vision_response = self._create_config('Vision config', 'browser_use_vision')

        self.assertEqual(text_response.status_code, 201)
        self.assertEqual(vision_response.status_code, 201)
        self.assertTrue(AIModelConfig.objects.get(role='browser_use_text').is_active)
        self.assertTrue(AIModelConfig.objects.get(role='browser_use_vision').is_active)

        list_response = self.client.get('/api/ui-automation/ai-models/')
        self.assertEqual(list_response.status_code, 200)
        roles = {item['role'] for item in list_response.data}
        self.assertEqual(roles, {'browser_use_text', 'browser_use_vision'})

    def test_enabling_new_config_disables_only_same_browser_role(self):
        self._create_config('Text config 1', 'browser_use_text')
        self._create_config('Vision config', 'browser_use_vision')
        text_response = self._create_config('Text config 2', 'browser_use_text')

        self.assertEqual(text_response.status_code, 201)
        self.assertIn('Text config 1', text_response.data['disabled_configs'])
        self.assertFalse(AIModelConfig.objects.get(name='Text config 1').is_active)
        self.assertTrue(AIModelConfig.objects.get(name='Text config 2').is_active)
        self.assertTrue(AIModelConfig.objects.get(name='Vision config').is_active)
