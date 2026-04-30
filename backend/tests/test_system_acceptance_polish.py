from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.executions.models import TestPlan, TestRun
from apps.knowledge_base.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from apps.ocr_service.models import OcrEngineConfig, OcrPage, OcrTask
from apps.projects.models import Project, ProjectMember
from apps.reports.models import TestReport
from apps.reviews.models import ReviewAssignment, TestCaseReview
from apps.testcases.models import TestCase as ManualTestCase
from apps.testsuites.models import TestSuite, TestSuiteCase
from apps.versions.models import Version


class ProductAcceptancePolishTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.project = Project.objects.create(name='Acceptance Project', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member, role='tester')

    def test_ocr_revision_can_import_revised_or_original_text(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Acceptance KB',
            created_by=self.owner,
        )
        engine = OcrEngineConfig.objects.create(
            name='Acceptance OCR',
            engine_type=OcrEngineConfig.ENGINE_TESSERACT,
            created_by=self.owner,
        )
        task = OcrTask.objects.create(
            project=self.project,
            engine=engine,
            name='OCR Requirement',
            source_type=OcrTask.SOURCE_TEXT,
            extracted_text='orignal typo',
            status=OcrTask.STATUS_SUCCEEDED,
            created_by=self.owner,
        )
        page = OcrPage.objects.create(task=task, page_number=1, text='orignal typo', confidence=0.7)

        self.client.force_authenticate(user=self.owner)
        revise_response = self.client.post(
            f'/api/ocr-service/tasks/{task.id}/revise-page/',
            {'page_id': page.id, 'text': 'original fixed'},
            format='json',
        )

        self.assertEqual(revise_response.status_code, 200)
        task.refresh_from_db()
        page.refresh_from_db()
        self.assertEqual(task.extracted_text, 'original fixed')
        self.assertEqual(page.metadata['original_text'], 'orignal typo')
        self.assertEqual(len(page.metadata['revisions']), 1)

        revised_import = self.client.post(
            '/api/knowledge-base/documents/import_ocr/',
            {'knowledge_base': knowledge_base.id, 'ocr_task': task.id, 'text_version': 'revised'},
            format='json',
        )
        original_import = self.client.post(
            '/api/knowledge-base/documents/import_ocr/',
            {'knowledge_base': knowledge_base.id, 'ocr_task': task.id, 'text_version': 'original'},
            format='json',
        )

        self.assertEqual(revised_import.status_code, 201)
        self.assertEqual(original_import.status_code, 201)
        self.assertEqual(KnowledgeDocument.objects.get(id=revised_import.data['id']).content_text, 'original fixed')
        self.assertEqual(KnowledgeDocument.objects.get(id=original_import.data['id']).content_text, 'orignal typo')

    def test_knowledge_governance_actions_update_metadata_and_chunks(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Governance KB',
            created_by=self.owner,
        )
        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title='Duplicate Spec',
            source_type=KnowledgeDocument.SOURCE_TEXT,
            content_text='valid content',
            status=KnowledgeDocument.STATUS_INDEXED,
            chunk_count=2,
            created_by=self.owner,
        )
        KnowledgeChunk.objects.create(document=document, chunk_index=1, content='   ')
        KnowledgeChunk.objects.create(document=document, chunk_index=2, content='valid content')

        self.client.force_authenticate(user=self.owner)
        clean_response = self.client.post(
            f'/api/knowledge-base/documents/{document.id}/clean-chunks/',
            {'reindex': False, 'remove_failed': False},
            format='json',
        )
        duplicate_response = self.client.post(
            f'/api/knowledge-base/documents/{document.id}/mark-duplicate/',
            {'duplicate_of': document.id, 'duplicate_group': 'duplicate spec'},
            format='json',
        )
        archive_response = self.client.post(
            f'/api/knowledge-base/documents/{document.id}/archive-governance/',
            {'reason': 'accepted duplicate'},
            format='json',
        )

        self.assertEqual(clean_response.status_code, 200)
        self.assertEqual(clean_response.data['deleted_chunks'], 1)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(archive_response.status_code, 200)
        document.refresh_from_db()
        self.assertTrue(document.metadata['duplicate_ignored'])
        self.assertTrue(document.metadata['governance_archived'])
        self.assertEqual(document.chunks.count(), 1)

    def test_version_traceability_links_cases_suites_runs_and_reports(self):
        version = Version.objects.create(name='Release 1.0', created_by=self.owner)
        version.projects.add(self.project)
        testcase = ManualTestCase.objects.create(
            project=self.project,
            title='Login works',
            expected_result='User is logged in',
            author=self.owner,
            status='active',
            priority='high',
            test_type='functional',
        )
        testcase.versions.add(version)
        suite = TestSuite.objects.create(project=self.project, name='Smoke Suite', author=self.owner)
        TestSuiteCase.objects.create(testsuite=suite, testcase=testcase, order=1)
        plan = TestPlan.objects.create(name='Release Plan', version=version, creator=self.owner)
        plan.projects.add(self.project)
        run = TestRun.objects.create(
            name='Release Run',
            test_plan=plan,
            project=self.project,
            version=version,
            assignee=self.member,
            creator=self.owner,
            status='completed',
        )
        TestReport.objects.create(
            project=self.project,
            name='Release Report',
            execution=run,
            generated_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.get(f'/api/versions/{version.id}/traceability/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['testcases'], 1)
        self.assertEqual(response.data['counts']['suites'], 1)
        self.assertEqual(response.data['counts']['runs'], 1)
        self.assertEqual(response.data['counts']['reports'], 1)
        self.assertEqual(response.data['reports'][0]['title'], 'Release Report')

    def test_review_center_is_project_scoped_and_shows_my_overdue_work(self):
        review = TestCaseReview.objects.create(
            title='Review Login',
            creator=self.owner,
            status='pending',
            priority='urgent',
            deadline=timezone.now() - timezone.timedelta(days=1),
        )
        review.projects.add(self.project)
        ReviewAssignment.objects.create(review=review, reviewer=self.member)

        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/reviews/reviews/center/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['my_pending'], 1)
        self.assertEqual(response.data['summary']['overdue'], 1)
        self.assertEqual(response.data['my_pending_reviews'][0]['title'], 'Review Login')

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get('/api/reviews/reviews/center/')
        self.assertEqual(outsider_response.status_code, 200)
        self.assertEqual(outsider_response.data['summary']['total'], 0)
