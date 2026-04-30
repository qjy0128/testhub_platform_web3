from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_testing.models import ApiProject, ScheduledTask as ApiScheduledTask, TestSuite as ApiTestSuite
from apps.api_testing.models import TaskExecutionLog as ApiTaskExecutionLog
from apps.app_automation.models import AppProject, AppScheduledTask, AppTestCase
from apps.core.models import (
    UnifiedAuditLog,
    UnifiedNotificationConfig,
    UnifiedSchedulerAlert,
    UnifiedScheduledJobDependency,
    UnifiedScheduledJobRun,
)
from apps.core.scheduler_engine import SchedulerExecutionError, run_due_scheduled_jobs
from apps.projects.models import Project, ProjectMember, ProjectModuleBinding, ProjectPermissionPolicy


class UnifiedScheduledJobApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')

        self.unified_project = Project.objects.create(
            name='Unified Project',
            description='Cross-module project',
            owner=self.owner,
        )
        ProjectMember.objects.create(
            project=self.unified_project,
            user=self.member,
            role='tester',
        )

        self.api_project = ApiProject.objects.create(
            name='API Module Project',
            description='API project',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.owner,
        )
        self.api_project.members.add(self.member)

        self.app_project = AppProject.objects.create(
            name='APP Module Project',
            description='APP project',
            owner=self.owner,
        )
        self.app_project.members.add(self.member)

        ProjectModuleBinding.objects.create(
            project=self.unified_project,
            module='api_testing',
            object_id=self.api_project.id,
        )
        ProjectModuleBinding.objects.create(
            project=self.unified_project,
            module='app_automation',
            object_id=self.app_project.id,
        )

        self.api_suite = ApiTestSuite.objects.create(
            project=self.api_project,
            name='API Suite',
            created_by=self.owner,
        )
        self.api_task = ApiScheduledTask.objects.create(
            name='API Job',
            task_type='TEST_SUITE',
            trigger_type='INTERVAL',
            interval_seconds=300,
            test_suite=self.api_suite,
            status='ACTIVE',
            next_run_time=timezone.now(),
            created_by=self.owner,
        )

        self.app_case = AppTestCase.objects.create(
            project=self.app_project,
            name='APP Case',
            created_by=self.owner,
        )
        self.app_task = AppScheduledTask.objects.create(
            project=self.app_project,
            name='APP Job',
            task_type='TEST_CASE',
            trigger_type='ONCE',
            execute_at=timezone.now(),
            test_case=self.app_case,
            status='ACTIVE',
            created_by=self.owner,
        )

        self.extra_api_project = ApiProject.objects.create(
            name='Extra API Project',
            description='Unbound project',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.owner,
        )
        self.extra_api_project.members.add(self.member)
        self.extra_api_suite = ApiTestSuite.objects.create(
            project=self.extra_api_project,
            name='Extra API Suite',
            created_by=self.owner,
        )
        self.extra_api_task = ApiScheduledTask.objects.create(
            name='Extra API Job',
            task_type='TEST_SUITE',
            trigger_type='INTERVAL',
            interval_seconds=600,
            test_suite=self.extra_api_suite,
            status='ACTIVE',
            created_by=self.owner,
        )

    def test_member_can_list_jobs_for_bound_unified_project(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(f'/api/core/scheduled-jobs/?project={self.unified_project.id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {job['job_key'] for job in response.data},
            {
                f'api_testing:{self.api_task.id}',
                f'app_automation:{self.app_task.id}',
            },
        )
        api_job = next(job for job in response.data if job['module'] == 'api_testing')
        self.assertEqual(api_job['unified_project_id'], self.unified_project.id)
        self.assertEqual(api_job['source_project_id'], self.api_project.id)
        self.assertEqual(api_job['source_project_name'], self.api_project.name)

    def test_member_can_read_accessible_dependency_graph(self):
        UnifiedScheduledJobDependency.objects.create(
            upstream_module='api_testing',
            upstream_source_id=self.api_task.id,
            downstream_module='app_automation',
            downstream_source_id=self.app_task.id,
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.get(f'/api/core/scheduled-jobs/graph/?project={self.unified_project.id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {node['id'] for node in response.data['nodes']},
            {
                f'api_testing:{self.api_task.id}',
                f'app_automation:{self.app_task.id}',
            },
        )
        self.assertEqual(
            {(edge['upstream_key'], edge['downstream_key']) for edge in response.data['edges']},
            {
                (
                    f'api_testing:{self.api_task.id}',
                    f'app_automation:{self.app_task.id}',
                ),
            },
        )
        app_node = next(node for node in response.data['nodes'] if node['id'] == f'app_automation:{self.app_task.id}')
        self.assertTrue(app_node['blocked'])

    def test_scheduler_health_reports_operational_alerts(self):
        now = timezone.now()
        self.api_task.next_run_time = now - timedelta(minutes=20)
        self.api_task.save(update_fields=['next_run_time'])
        UnifiedScheduledJobDependency.objects.create(
            upstream_module='api_testing',
            upstream_source_id=self.api_task.id,
            downstream_module='app_automation',
            downstream_source_id=self.app_task.id,
            created_by=self.owner,
        )
        UnifiedScheduledJobRun.objects.create(
            module='api_testing',
            source_id=self.api_task.id,
            job_name=self.api_task.name,
            status=UnifiedScheduledJobRun.STATUS_RUNNING,
            triggered_by=self.owner,
            started_at=now - timedelta(hours=1),
            locked_until=now - timedelta(minutes=5),
        )
        UnifiedScheduledJobRun.objects.create(
            module='app_automation',
            source_id=self.app_task.id,
            job_name=self.app_task.name,
            status=UnifiedScheduledJobRun.STATUS_FAILED,
            triggered_by=self.owner,
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            error_message='boom',
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            f'/api/core/scheduled-jobs/health/?project={self.unified_project.id}&stale_minutes=10'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'unhealthy')
        self.assertEqual(response.data['counts']['overdue'], 1)
        self.assertEqual(response.data['counts']['blocked'], 1)
        self.assertEqual(response.data['counts']['stale_running'], 1)
        self.assertEqual(response.data['counts']['recent_failed'], 1)
        alert_types = {alert['type'] for alert in response.data['alerts']}
        self.assertTrue({'overdue', 'blocked', 'stale_running', 'recent_failure'}.issubset(alert_types))
        persisted_types = set(
            UnifiedSchedulerAlert.objects.values_list('alert_type', flat=True)
        )
        self.assertTrue({'overdue', 'blocked', 'stale_running', 'recent_failure'}.issubset(persisted_types))

    def test_member_can_list_all_accessible_jobs_across_modules(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get('/api/core/scheduled-jobs/?module=api_testing')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {job['job_key'] for job in response.data},
            {
                f'api_testing:{self.api_task.id}',
                f'api_testing:{self.extra_api_task.id}',
            },
        )

    def test_outsider_cannot_read_unified_project_jobs(self):
        self.client.force_authenticate(user=self.outsider)

        response = self.client.get(f'/api/core/scheduled-jobs/?project={self.unified_project.id}')

        self.assertEqual(response.status_code, 404)

    def test_member_can_read_job_detail(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['job_key'], f'api_testing:{self.api_task.id}')
        self.assertEqual(response.data['name'], self.api_task.name)
        self.assertEqual(response.data['task_type'], self.api_task.task_type)

    def test_member_can_read_runs_for_accessible_jobs(self):
        run = UnifiedScheduledJobRun.objects.create(
            module='api_testing',
            source_id=self.api_task.id,
            job_name=self.api_task.name,
            status=UnifiedScheduledJobRun.STATUS_SUCCEEDED,
            triggered_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        list_response = self.client.get('/api/core/scheduled-job-runs/')
        summary_response = self.client.get('/api/core/scheduled-jobs/summary/')

        self.assertEqual(list_response.status_code, 200)
        run_rows = list_response.data['results'] if isinstance(list_response.data, dict) else list_response.data
        self.assertIn(run.id, {item['id'] for item in run_rows})
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data['runs']['succeeded'], 1)

    def test_member_can_read_audit_summary_and_export_for_project_logs(self):
        UnifiedAuditLog.objects.create(
            domain='knowledge_base',
            action=UnifiedAuditLog.ACTION_CREATE,
            object_type='knowledge_document',
            object_id='42',
            object_name='Imported OCR Document',
            project_id=self.unified_project.id,
            project_name=self.unified_project.name,
            actor=self.owner,
            summary='Imported OCR result into knowledge base.',
        )

        self.client.force_authenticate(user=self.member)
        summary_response = self.client.get('/api/core/audit-logs/summary/?domain=knowledge_base')
        export_response = self.client.get('/api/core/audit-logs/export/?domain=knowledge_base')

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data['total'], 1)
        self.assertEqual(summary_response.data['domains']['knowledge_base'], 1)
        self.assertEqual(export_response.status_code, 200)
        self.assertIn('Imported OCR Document', export_response.content.decode('utf-8'))

        self.client.force_authenticate(user=self.outsider)
        outsider_summary = self.client.get('/api/core/audit-logs/summary/?domain=knowledge_base')
        self.assertEqual(outsider_summary.status_code, 200)
        self.assertEqual(outsider_summary.data['total'], 0)

    def test_unified_project_membership_grants_access_to_bound_jobs(self):
        bound_only_api_project = ApiProject.objects.create(
            name='Bound Only API Project',
            description='Bound via unified project only',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.owner,
        )
        ProjectModuleBinding.objects.create(
            project=self.unified_project,
            module='api_testing',
            object_id=bound_only_api_project.id,
        )
        bound_only_suite = ApiTestSuite.objects.create(
            project=bound_only_api_project,
            name='Bound Only Suite',
            created_by=self.owner,
        )
        bound_only_task = ApiScheduledTask.objects.create(
            name='Bound Only API Job',
            task_type='TEST_SUITE',
            trigger_type='INTERVAL',
            interval_seconds=120,
            test_suite=bound_only_suite,
            status='ACTIVE',
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.get(f'/api/core/scheduled-jobs/?project={self.unified_project.id}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'api_testing:{bound_only_task.id}', {job['job_key'] for job in response.data})

    def test_owner_can_pause_and_resume_job_through_unified_actions(self):
        self.client.force_authenticate(user=self.owner)

        pause_response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/pause/',
            {},
            format='json',
        )

        self.assertEqual(pause_response.status_code, 200)
        self.api_task.refresh_from_db()
        self.assertEqual(self.api_task.status, 'PAUSED')
        self.assertEqual(pause_response.data['job']['status'], 'PAUSED')

        resume_response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/resume/',
            {},
            format='json',
        )

        self.assertEqual(resume_response.status_code, 200)
        self.api_task.refresh_from_db()
        self.assertEqual(self.api_task.status, 'ACTIVE')
        self.assertIsNotNone(self.api_task.next_run_time)
        self.assertEqual(resume_response.data['job']['status'], 'ACTIVE')
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='scheduler',
                action=UnifiedAuditLog.ACTION_PAUSE,
                module='api_testing',
                source_id=self.api_task.id,
                actor=self.owner,
            ).exists()
        )
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='scheduler',
                action=UnifiedAuditLog.ACTION_RESUME,
                module='api_testing',
                source_id=self.api_task.id,
                actor=self.owner,
            ).exists()
        )

    def test_member_can_read_accessible_scheduler_audit_logs(self):
        log = UnifiedAuditLog.objects.create(
            domain='scheduler',
            action=UnifiedAuditLog.ACTION_PAUSE,
            object_type='scheduled_job',
            object_id=str(self.api_task.id),
            object_name=self.api_task.name,
            module='api_testing',
            source_id=self.api_task.id,
            actor=self.owner,
            summary='Paused scheduled job.',
        )

        self.client.force_authenticate(user=self.member)
        member_response = self.client.get('/api/core/audit-logs/?domain=scheduler')
        member_rows = member_response.data['results'] if isinstance(member_response.data, dict) else member_response.data

        self.assertEqual(member_response.status_code, 200)
        self.assertIn(log.id, {row['id'] for row in member_rows})

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/core/audit-logs/?domain=scheduler')
        outsider_rows = outsider_response.data['results'] if isinstance(outsider_response.data, dict) else outsider_response.data

        self.assertEqual(outsider_response.status_code, 200)
        self.assertNotIn(log.id, {row['id'] for row in outsider_rows})

    def test_non_manager_cannot_pause_job_through_unified_actions(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/pause/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_permission_policy_can_grant_tester_pause_scheduler_job(self):
        ProjectPermissionPolicy.objects.create(
            project=self.unified_project,
            module='api_testing',
            action='scheduler.pause',
            allowed_roles=['tester'],
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/pause/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.api_task.refresh_from_db()
        self.assertEqual(self.api_task.status, 'PAUSED')

    def test_member_can_acknowledge_accessible_scheduler_alert(self):
        alert = UnifiedSchedulerAlert.objects.create(
            alert_key='overdue:job:api_testing:1',
            alert_type='overdue',
            severity='warning',
            status=UnifiedSchedulerAlert.STATUS_OPEN,
            module='api_testing',
            source_id=self.api_task.id,
            job_key=f'api_testing:{self.api_task.id}',
            job_name=self.api_task.name,
            project_id=self.unified_project.id,
            project_name=self.unified_project.name,
            message='Scheduled job is overdue.',
        )

        self.client.force_authenticate(user=self.member)
        list_response = self.client.get('/api/core/scheduler-alerts/')
        list_rows = list_response.data['results'] if isinstance(list_response.data, dict) else list_response.data
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(alert.id, {row['id'] for row in list_rows})

        ack_response = self.client.post(f'/api/core/scheduler-alerts/{alert.id}/acknowledge/', {}, format='json')
        self.assertEqual(ack_response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, UnifiedSchedulerAlert.STATUS_ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by_id, self.member.id)

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/core/scheduler-alerts/')
        outsider_rows = outsider_response.data['results'] if isinstance(outsider_response.data, dict) else outsider_response.data
        self.assertNotIn(alert.id, {row['id'] for row in outsider_rows})

    def test_owner_can_notify_open_scheduler_alerts(self):
        alert = UnifiedSchedulerAlert.objects.create(
            alert_key='overdue:job:api_testing:notify',
            alert_type='overdue',
            severity='warning',
            status=UnifiedSchedulerAlert.STATUS_OPEN,
            module='api_testing',
            source_id=self.api_task.id,
            job_key=f'api_testing:{self.api_task.id}',
            job_name=self.api_task.name,
            project_id=self.unified_project.id,
            project_name=self.unified_project.name,
            message='Scheduled job is overdue.',
        )
        UnifiedNotificationConfig.objects.create(
            name='Ops Bot',
            config_type='webhook_feishu',
            webhook_bots={
                'feishu': {
                    'name': 'Alert Bot',
                    'webhook_url': 'https://hooks.example.com/feishu',
                    'enabled': True,
                }
            },
            is_active=True,
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.owner)
        with patch('apps.core.notifications.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status.return_value = None
            response = self.client.post('/api/core/scheduler-alerts/notify/', {'status': 'open'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['sent'], 1)
        alert.refresh_from_db()
        self.assertEqual(alert.notify_count, 1)
        self.assertIsNotNone(alert.last_notified_at)

    def test_owner_can_run_api_job_through_unified_action(self):
        self.client.force_authenticate(user=self.owner)

        with patch('apps.api_testing.views.ScheduledTaskViewSet._execute_task_async') as execute_async:
            response = self.client.post(
                f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/run-now/',
                {},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ApiTaskExecutionLog.objects.filter(task=self.api_task).exists())
        execute_async.assert_called_once()
        self.assertEqual(response.data['job']['job_key'], f'api_testing:{self.api_task.id}')

        run = UnifiedScheduledJobRun.objects.get(module='api_testing', source_id=self.api_task.id)
        self.assertEqual(run.status, UnifiedScheduledJobRun.STATUS_SUCCEEDED)
        self.assertEqual(run.trigger_source, UnifiedScheduledJobRun.TRIGGER_MANUAL)

    def test_run_now_retries_failed_job_when_requested(self):
        self.client.force_authenticate(user=self.owner)

        with patch(
            'apps.core.scheduler_engine.run_module_task',
            side_effect=[
                SchedulerExecutionError({'detail': 'temporary failure'}),
                {'message': 'retry succeeded'},
            ],
        ) as run_module_task:
            response = self.client.post(
                f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/run-now/',
                {'max_attempts': 2},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_module_task.call_count, 2)
        self.assertEqual(response.data['attempts'], list(
            UnifiedScheduledJobRun.objects.filter(
                module='api_testing',
                source_id=self.api_task.id,
            ).order_by('attempt').values_list('id', flat=True)
        ))

        runs = list(UnifiedScheduledJobRun.objects.filter(
            module='api_testing',
            source_id=self.api_task.id,
        ).order_by('attempt'))
        self.assertEqual([run.status for run in runs], [
            UnifiedScheduledJobRun.STATUS_FAILED,
            UnifiedScheduledJobRun.STATUS_SUCCEEDED,
        ])
        self.assertEqual(runs[0].trigger_source, UnifiedScheduledJobRun.TRIGGER_MANUAL)
        self.assertEqual(runs[1].trigger_source, UnifiedScheduledJobRun.TRIGGER_RETRY)
        self.assertEqual(runs[1].retry_of_id, runs[0].id)

    def test_dependency_blocks_downstream_run_now_until_upstream_succeeds(self):
        UnifiedScheduledJobDependency.objects.create(
            upstream_module='api_testing',
            upstream_source_id=self.extra_api_task.id,
            downstream_module='api_testing',
            downstream_source_id=self.api_task.id,
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.owner)

        blocked_response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/run-now/',
            {},
            format='json',
        )
        self.assertEqual(blocked_response.status_code, 409)
        self.assertEqual(blocked_response.data['run']['status'], UnifiedScheduledJobRun.STATUS_SKIPPED)
        self.assertEqual(blocked_response.data['blocked_by'][0]['upstream_key'], f'api_testing:{self.extra_api_task.id}')

        UnifiedScheduledJobRun.objects.create(
            module='api_testing',
            source_id=self.extra_api_task.id,
            job_name=self.extra_api_task.name,
            status=UnifiedScheduledJobRun.STATUS_SUCCEEDED,
            triggered_by=self.owner,
        )
        with patch('apps.api_testing.views.ScheduledTaskViewSet._execute_task_async') as execute_async:
            allowed_response = self.client.post(
                f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/run-now/',
                {},
                format='json',
            )

        self.assertEqual(allowed_response.status_code, 200)
        execute_async.assert_called_once()

    def test_dependency_api_rejects_cycles(self):
        UnifiedScheduledJobDependency.objects.create(
            upstream_module='api_testing',
            upstream_source_id=self.api_task.id,
            downstream_module='app_automation',
            downstream_source_id=self.app_task.id,
            created_by=self.owner,
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            '/api/core/scheduled-job-dependencies/',
            {
                'upstream_module': 'app_automation',
                'upstream_source_id': self.app_task.id,
                'downstream_module': 'api_testing',
                'downstream_source_id': self.api_task.id,
                'is_active': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('cycle', str(response.data).lower())

    def test_dependency_api_writes_audit_and_requires_downstream_manager(self):
        self.client.force_authenticate(user=self.owner)

        create_response = self.client.post(
            '/api/core/scheduled-job-dependencies/',
            {
                'upstream_module': 'api_testing',
                'upstream_source_id': self.api_task.id,
                'downstream_module': 'app_automation',
                'downstream_source_id': self.app_task.id,
                'is_active': True,
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        dependency_id = create_response.data['id']
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='scheduler',
                action=UnifiedAuditLog.ACTION_CREATE,
                object_type='scheduled_job_dependency',
                object_id=str(dependency_id),
                actor=self.owner,
            ).exists()
        )

        self.client.force_authenticate(user=self.member)
        update_response = self.client.patch(
            f'/api/core/scheduled-job-dependencies/{dependency_id}/',
            {'is_active': False},
            format='json',
        )

        self.assertEqual(update_response.status_code, 403)

    def test_running_lock_blocks_duplicate_dispatch(self):
        UnifiedScheduledJobRun.objects.create(
            module='api_testing',
            source_id=self.api_task.id,
            job_name=self.api_task.name,
            status=UnifiedScheduledJobRun.STATUS_RUNNING,
            triggered_by=self.owner,
            started_at=timezone.now(),
            locked_until=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f'/api/core/scheduled-jobs/api_testing/{self.api_task.id}/run-now/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['run']['status'], UnifiedScheduledJobRun.STATUS_SKIPPED)
        self.assertIn('locked_by', response.data)

    def test_unified_scheduler_dispatches_due_jobs_with_scheduler_metadata(self):
        self.api_task.next_run_time = timezone.now()
        self.api_task.save(update_fields=['next_run_time'])

        with patch('apps.api_testing.views.ScheduledTaskViewSet._execute_task_async') as execute_async:
            summary = run_due_scheduled_jobs(modules=['api_testing'], limit=1, max_attempts=2)

        self.assertEqual(summary['due'], 1)
        self.assertEqual(summary['succeeded'], 1)
        execute_async.assert_called_once()

        run = UnifiedScheduledJobRun.objects.get(id=summary['runs'][0])
        self.assertEqual(run.status, UnifiedScheduledJobRun.STATUS_SUCCEEDED)
        self.assertEqual(run.trigger_source, UnifiedScheduledJobRun.TRIGGER_SCHEDULER)
        self.assertEqual(run.max_attempts, 2)
        self.assertIsNotNone(run.scheduled_for)
