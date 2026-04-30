from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.api_testing.models import ApiProject, ScheduledTask as ApiScheduledTask, TestSuite as ApiTestSuite
from apps.projects.models import MetaProject, Project, ProjectMember, ProjectModuleBinding, UnifiedTestAsset, UnifiedTestAssetSnapshot
from apps.testcases.models import TestCase as ManualTestCase
from apps.testsuites.models import TestSuite as ManualTestSuite, TestSuiteCase


class UnifiedProjectApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.other_owner = User.objects.create_user(username='other-owner', password='pass')

        self.project = Project.objects.create(
            name='Unified Project',
            description='Main project',
            owner=self.owner,
        )
        ProjectMember.objects.create(project=self.project, user=self.member, role='tester')

        self.api_project = ApiProject.objects.create(
            name='API Workspace',
            description='API module project',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.owner,
        )
        self.foreign_api_project = ApiProject.objects.create(
            name='Foreign API Workspace',
            description='No access',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.other_owner,
        )

    def test_owner_can_bind_module_project_and_read_unified_detail(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f'/api/projects/{self.project.id}/modules/',
            {'module': 'api_testing', 'object_id': self.api_project.id},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProjectModuleBinding.objects.count(), 1)

        api_suite = ApiTestSuite.objects.create(
            project=self.api_project,
            name='Unified API Suite',
            created_by=self.owner,
        )
        ApiScheduledTask.objects.create(
            name='Unified API Job',
            task_type='TEST_SUITE',
            trigger_type='INTERVAL',
            interval_seconds=300,
            test_suite=api_suite,
            status='ACTIVE',
            next_run_time=timezone.now(),
            created_by=self.owner,
        )

        detail_response = self.client.get(f'/api/projects/unified/{self.project.id}/')

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['id'], self.project.id)
        self.assertEqual(detail_response.data['module_summary']['total'], 1)
        self.assertEqual(detail_response.data['modules'][0]['module'], 'api_testing')
        self.assertEqual(detail_response.data['modules'][0]['object_id'], self.api_project.id)
        self.assertEqual(detail_response.data['modules'][0]['module_name'], self.api_project.name)
        self.assertEqual(detail_response.data['meta_project']['node_type'], 'meta_project')
        self.assertEqual(detail_response.data['meta_project']['name'], self.project.name)
        self.assertEqual(detail_response.data['meta_project']['children'][0]['module'], 'api_testing')
        self.assertEqual(detail_response.data['meta_project']['children'][0]['object_id'], self.api_project.id)
        self.assertEqual(detail_response.data['scheduled_job_summary']['total'], 1)
        self.assertEqual(detail_response.data['scheduled_job_summary']['active'], 1)
        self.assertEqual(detail_response.data['scheduled_job_summary']['by_module']['api_testing'], 1)

    def test_project_member_can_read_unified_detail_but_outsider_cannot(self):
        ProjectModuleBinding.objects.create(
            project=self.project,
            module='api_testing',
            object_id=self.api_project.id,
        )

        self.client.force_authenticate(user=self.member)
        member_response = self.client.get(f'/api/projects/unified/{self.project.id}/')
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.data['modules'][0]['module_name'], self.api_project.name)

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get(f'/api/projects/unified/{self.project.id}/')
        self.assertEqual(outsider_response.status_code, 404)

    def test_meta_project_tree_is_access_limited_and_syncs_bindings(self):
        ProjectModuleBinding.objects.create(
            project=self.project,
            module='api_testing',
            object_id=self.api_project.id,
        )

        self.client.force_authenticate(user=self.member)
        member_sync_response = self.client.post(f'/api/projects/{self.project.id}/meta/sync/')
        self.assertEqual(member_sync_response.status_code, 403)

        self.client.force_authenticate(user=self.owner)
        sync_response = self.client.post(f'/api/projects/{self.project.id}/meta/sync/')
        self.assertEqual(sync_response.status_code, 200)
        self.assertEqual(sync_response.data['children'][0]['name'], self.api_project.name)

        list_response = self.client.get(f'/api/projects/meta/?project={self.project.id}')
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.data.get('results', list_response.data)
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]['project'], self.project.id)
        self.assertEqual(MetaProject.objects.filter(project=self.project).count(), 2)

        self.client.force_authenticate(user=self.outsider)
        outsider_list_response = self.client.get(f'/api/projects/meta/?project={self.project.id}')
        self.assertEqual(outsider_list_response.status_code, 200)
        outsider_payload = outsider_list_response.data.get('results', outsider_list_response.data)
        self.assertEqual(outsider_payload, [])

    def test_owner_cannot_bind_module_project_without_module_access(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f'/api/projects/{self.project.id}/modules/',
            {'module': 'api_testing', 'object_id': self.foreign_api_project.id},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProjectModuleBinding.objects.exists())

    def test_all_projects_dropdown_is_limited_to_accessible_projects(self):
        Project.objects.create(
            name='Hidden Project',
            description='Not visible',
            owner=self.other_owner,
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.get('/api/projects/all/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([project['id'] for project in response.data], [self.project.id])

    def test_module_catalog_exposes_star_and_bindable_metadata(self):
        self.client.force_authenticate(user=self.owner)

        catalog_response = self.client.get('/api/projects/modules/catalog/')
        self.assertEqual(catalog_response.status_code, 200)
        module_keys = {module['key'] for module in catalog_response.data}
        self.assertIn('ai_testing', module_keys)
        self.assertIn('knowledge_base', module_keys)
        self.assertIn('api_testing', module_keys)

        bindable_response = self.client.get('/api/projects/modules/catalog/?bindable=true')
        self.assertEqual(bindable_response.status_code, 200)
        self.assertEqual(
            {module['key'] for module in bindable_response.data},
            {'api_testing', 'ui_automation', 'app_automation'},
        )

    def test_owner_can_manage_project_permission_policies(self):
        self.client.force_authenticate(user=self.owner)

        create_response = self.client.post(
            f'/api/projects/{self.project.id}/permission-policies/',
            {
                'module': 'api_testing',
                'action': 'scheduler.run_now',
                'allowed_roles': ['tester'],
                'description': 'Allow testers to run API schedules',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)

        policy_id = create_response.data['id']
        update_response = self.client.patch(
            f'/api/projects/{self.project.id}/permission-policies/{policy_id}/',
            {'allowed_roles': ['tester', 'admin']},
            format='json',
        )
        self.assertEqual(update_response.status_code, 200)

        self.client.force_authenticate(user=self.member)
        forbidden_response = self.client.post(
            f'/api/projects/{self.project.id}/permission-policies/',
            {
                'module': 'api_testing',
                'action': 'scheduler.pause',
                'allowed_roles': ['tester'],
            },
            format='json',
        )
        self.assertEqual(forbidden_response.status_code, 403)

    def test_star_asset_sync_indexes_manual_cases_suites_and_snapshots(self):
        testcase = ManualTestCase.objects.create(
            project=self.project,
            title='Login succeeds',
            expected_result='User lands on dashboard',
            priority='critical',
            status='active',
            test_type='functional',
            author=self.owner,
        )
        suite = ManualTestSuite.objects.create(
            project=self.project,
            name='Smoke Suite',
            author=self.owner,
        )
        TestSuiteCase.objects.create(testsuite=suite, testcase=testcase, order=1)

        self.client.force_authenticate(user=self.owner)
        summary_response = self.client.get('/api/projects/star-assets/summary/')

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data['assets'], 2)
        self.assertEqual(summary_response.data['testcases']['total'], 1)
        self.assertEqual(summary_response.data['testcases']['critical'], 1)
        self.assertEqual(summary_response.data['testsuites']['with_cases'], 1)

        list_response = self.client.get('/api/projects/star-assets/all/')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual({row['asset_type'] for row in list_response.data}, {'testcase', 'testsuite'})
        self.assertTrue(UnifiedTestAsset.objects.filter(project=self.project).exists())
        self.assertEqual(UnifiedTestAssetSnapshot.objects.count(), 2)
