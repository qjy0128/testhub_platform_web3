from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import UnifiedAuditLog
from apps.knowledge_base.models import KnowledgeBase, KnowledgeDocument
from apps.ocr_service.models import OcrEngineConfig, OcrTask
from apps.projects.models import Project, ProjectMember, ProjectModuleBinding, UnifiedTestAsset
from apps.testcases.models import TestCase as ManualTestCase
from apps.ui_automation.models import (
    TestCase as UiAutomationTestCase,
    TestCaseStep as UiAutomationTestCaseStep,
    TestSuite as UiAutomationTestSuite,
    TestSuiteTestCase as UiAutomationSuiteCase,
    UiProject,
)


class StarModuleBoundaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.other_owner = User.objects.create_user(username='other-owner', password='pass')

        self.project = Project.objects.create(name='Star Project', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member, role='tester')
        self.foreign_project = Project.objects.create(name='Hidden Project', owner=self.other_owner)

    def test_knowledge_base_is_limited_to_accessible_projects(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Project KB',
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        member_response = self.client.get('/api/knowledge-base/bases/')
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.data['count'], 1)

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/knowledge-base/bases/')
        self.assertEqual(outsider_response.status_code, 200)
        self.assertEqual(outsider_response.data['count'], 0)

        document_response = self.client.post(
            '/api/knowledge-base/documents/',
            {
                'knowledge_base': knowledge_base.id,
                'title': 'Leaked requirement',
                'source_type': 'text',
                'content_text': 'secret',
            },
            format='json',
        )
        self.assertEqual(document_response.status_code, 400)

    def test_knowledge_base_maintenance_indexes_only_accessible_documents(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Project KB',
            created_by=self.owner,
        )
        foreign_knowledge_base = KnowledgeBase.objects.create(
            project=self.foreign_project,
            name='Hidden KB',
            created_by=self.other_owner,
        )
        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title='Visible document',
            source_type=KnowledgeDocument.SOURCE_TEXT,
            content_text='login failure should display an error message',
            created_by=self.owner,
        )
        foreign_document = KnowledgeDocument.objects.create(
            knowledge_base=foreign_knowledge_base,
            title='Hidden document',
            source_type=KnowledgeDocument.SOURCE_TEXT,
            content_text='private roadmap content',
            created_by=self.other_owner,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.post('/api/knowledge-base/maintenance/index-pending/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['indexed'], 1)
        document.refresh_from_db()
        foreign_document.refresh_from_db()
        self.assertEqual(document.status, KnowledgeDocument.STATUS_INDEXED)
        self.assertEqual(foreign_document.status, KnowledgeDocument.STATUS_PENDING)
        self.assertEqual(foreign_document.chunk_count, 0)

    def test_knowledge_base_can_import_accessible_ocr_result(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Project KB',
            created_by=self.owner,
        )
        engine = OcrEngineConfig.objects.create(
            name='Owner OCR',
            engine_type='tesseract',
            is_default=True,
            created_by=self.owner,
        )
        task = OcrTask.objects.create(
            project=self.project,
            engine=engine,
            name='OCR Requirement',
            source_type='text',
            input_text='raw',
            extracted_text='checkout should show a payment confirmation',
            status=OcrTask.STATUS_SUCCEEDED,
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            '/api/knowledge-base/documents/import_ocr/',
            {
                'knowledge_base': knowledge_base.id,
                'ocr_task': task.id,
                'title': 'Imported OCR Requirement',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        document = KnowledgeDocument.objects.get(id=response.data['id'])
        self.assertEqual(document.status, KnowledgeDocument.STATUS_INDEXED)
        self.assertEqual(document.metadata['ocr_task_id'], task.id)
        self.assertEqual(document.chunks.count(), 1)
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='knowledge_base',
                object_type='knowledge_document',
                object_id=str(document.id),
                actor=self.member,
                metadata__operation='import_ocr',
            ).exists()
        )

    def test_ocr_tasks_are_limited_to_accessible_projects(self):
        engine = OcrEngineConfig.objects.create(
            name='Owner OCR',
            engine_type='tesseract',
            is_default=True,
            created_by=self.owner,
        )
        OcrTask.objects.create(
            project=self.project,
            engine=engine,
            name='Project OCR Task',
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        member_response = self.client.get('/api/ocr-service/tasks/')
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.data['count'], 1)

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/ocr-service/tasks/')
        self.assertEqual(outsider_response.status_code, 200)
        self.assertEqual(outsider_response.data['count'], 0)

        forbidden_project_response = self.client.post(
            '/api/ocr-service/tasks/',
            {
                'project': self.foreign_project.id,
                'name': 'Hidden OCR Task',
                'source_type': 'image',
            },
            format='json',
        )
        self.assertEqual(forbidden_project_response.status_code, 400)

    def test_unified_assets_include_bound_ui_automation_cases_and_suites(self):
        ui_project = UiProject.objects.create(
            name='Bound UI Project',
            base_url='https://example.test',
            owner=self.owner,
        )
        ProjectModuleBinding.objects.create(
            project=self.project,
            module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
            object_id=ui_project.id,
            display_name=ui_project.name,
        )
        ui_case = UiAutomationTestCase.objects.create(
            project=ui_project,
            name='UI Login Case',
            description='Login should work from the unified surface',
            status='ready',
            priority='high',
            created_by=self.owner,
        )
        UiAutomationTestCaseStep.objects.create(
            test_case=ui_case,
            step_number=1,
            action_type='click',
            description='Open login',
        )
        ui_suite = UiAutomationTestSuite.objects.create(
            project=ui_project,
            name='UI Smoke Suite',
            execution_status='not_run',
        )
        UiAutomationSuiteCase.objects.create(test_suite=ui_suite, test_case=ui_case)

        self.client.force_authenticate(user=self.member)
        case_response = self.client.get('/api/projects/star-assets/testcases/')
        self.assertEqual(case_response.status_code, 200)
        self.assertTrue(
            any(
                row['module'] == UnifiedTestAsset.MODULE_UI_AUTOMATION
                and row['title'] == ui_case.name
                and row['step_count'] == 1
                for row in case_response.data
            )
        )

        suite_response = self.client.get('/api/projects/star-assets/testsuites/')
        self.assertEqual(suite_response.status_code, 200)
        self.assertTrue(
            any(
                row['module'] == UnifiedTestAsset.MODULE_UI_AUTOMATION
                and row['title'] == ui_suite.name
                and row['case_count'] == 1
                for row in suite_response.data
            )
        )

    def test_unified_asset_detail_and_adoption_create_manual_testcase(self):
        ui_project = UiProject.objects.create(
            name='Bound UI Project',
            base_url='https://example.test',
            owner=self.owner,
        )
        ProjectModuleBinding.objects.create(
            project=self.project,
            module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
            object_id=ui_project.id,
            display_name=ui_project.name,
        )
        ui_case = UiAutomationTestCase.objects.create(
            project=ui_project,
            name='Checkout UI Case',
            description='Checkout button should work',
            status='ready',
            priority='high',
            created_by=self.owner,
        )
        UiAutomationTestCaseStep.objects.create(
            test_case=ui_case,
            step_number=1,
            action_type='click',
            description='Click checkout',
            assert_value='Checkout page opens',
        )

        self.client.force_authenticate(user=self.owner)
        case_response = self.client.get('/api/projects/star-assets/testcases/?source_module=ui_automation')
        self.assertEqual(case_response.status_code, 200)
        asset_row = next(row for row in case_response.data if row['title'] == ui_case.name)

        detail_response = self.client.get(f"/api/projects/star-assets/detail/{asset_row['asset_id']}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['asset_key'], asset_row['asset_key'])
        self.assertEqual(detail_response.data['latest_payload']['steps'][0]['description'], 'Click checkout')

        adopt_response = self.client.post(f"/api/projects/star-assets/detail/{asset_row['asset_id']}/adopt/")
        self.assertEqual(adopt_response.status_code, 201)
        manual_case = ManualTestCase.objects.get(id=adopt_response.data['id'])
        self.assertEqual(manual_case.project, self.project)
        self.assertEqual(manual_case.title, ui_case.name)
        self.assertEqual(manual_case.priority, 'high')
        self.assertEqual(manual_case.test_type, 'ui')
        self.assertIn('asset:ui_automation:testcase:', manual_case.tags[-1])
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='unified_assets',
                object_type='manual_testcase',
                object_id=str(manual_case.id),
                actor=self.owner,
                metadata__operation='adopt_asset',
            ).exists()
        )
