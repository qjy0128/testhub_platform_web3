from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import MetaProject, Project, ProjectModuleBinding
from apps.ui_automation.models import Element, LocatorStrategy, TestExecution, UiProject


class UiAutomationEnhancementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='ui-owner', password='pass')
        self.other_user = User.objects.create_user(username='ui-outsider', password='pass')
        self.client.force_authenticate(user=self.user)
        self.ui_project = UiProject.objects.create(
            name='UI Project',
            description='UI automation project',
            base_url='https://example.com',
            owner=self.user,
        )
        self.strategy = LocatorStrategy.objects.create(name='css', description='CSS selector')
        self.element_a = Element.objects.create(
            project=self.ui_project,
            name='Login button',
            element_type='BUTTON',
            locator_strategy=self.strategy,
            locator_value='#login',
            page='Login',
            sort_order=20,
            created_by=self.user,
        )
        self.element_b = Element.objects.create(
            project=self.ui_project,
            name='Username input',
            element_type='INPUT',
            locator_strategy=self.strategy,
            locator_value='#username',
            page='Login',
            sort_order=10,
            created_by=self.user,
        )

    def test_project_serializer_exposes_unified_project_binding(self):
        unified_project = Project.objects.create(name='Unified UI', owner=self.user)
        binding = ProjectModuleBinding.objects.create(
            project=unified_project,
            module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
            object_id=self.ui_project.id,
            display_name='UI module',
        )
        meta_node = MetaProject.objects.create(
            project=unified_project,
            module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
            object_id=self.ui_project.id,
            name='UI Project',
            owner=self.user,
        )

        response = self.client.get(f'/api/ui-automation/projects/{self.ui_project.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unified_projects'][0]['binding_id'], binding.id)
        self.assertEqual(response.data['unified_projects'][0]['meta_project_id'], meta_node.id)

    def test_element_reorder_statistics_and_locator_feedback(self):
        add_response = self.client.post(
            f'/api/ui-automation/elements/{self.element_a.id}/add_backup_locator/',
            {'strategy': 'xpath', 'value': "//button[text()='Login']", 'priority': 5, 'name': 'text fallback'},
            format='json',
        )
        feedback_response = self.client.post(
            f'/api/ui-automation/elements/{self.element_a.id}/record_locator_result/',
            {'success': True, 'locator': {'strategy': 'xpath', 'value': "//button[text()='Login']"}},
            format='json',
        )
        reorder_response = self.client.post(
            '/api/ui-automation/elements/reorder/',
            {'items': [{'id': self.element_a.id, 'sort_order': 1}, {'id': self.element_b.id, 'sort_order': 2}]},
            format='json',
        )
        stats_response = self.client.get(f'/api/ui-automation/elements/statistics/?project={self.ui_project.id}')
        list_response = self.client.get(f'/api/ui-automation/elements/?project={self.ui_project.id}&page_name=Login')

        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(feedback_response.status_code, 200)
        self.assertEqual(feedback_response.data['locator_success_count'], 1)
        self.assertEqual(feedback_response.data['all_locators'][1]['priority'], 5)
        self.assertEqual(reorder_response.status_code, 200)
        self.assertEqual(reorder_response.data['updated'], 2)
        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(stats_response.data['total'], 2)
        rows = list_response.data.get('results', list_response.data)
        self.assertEqual([row['id'] for row in rows[:2]], [self.element_a.id, self.element_b.id])

    def test_test_execution_pdf_export(self):
        execution = TestExecution.objects.create(
            project=self.ui_project,
            executed_by=self.user,
            status='SUCCESS',
            total_cases=3,
            passed_cases=2,
            failed_cases=1,
            duration=12.5,
        )

        response = self.client.get(f'/api/ui-automation/test-executions/{execution.id}/export-pdf/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
