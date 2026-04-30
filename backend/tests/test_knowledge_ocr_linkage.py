from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.knowledge_base.models import KnowledgeBase, KnowledgeDocument
from apps.ocr_service.models import OcrEngineConfig, OcrPage, OcrTask
from apps.ocr_service.services import run_ocr_task
from apps.projects.models import Project, ProjectMember


class KnowledgeOcrLinkageTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.project = Project.objects.create(name='Knowledge OCR Project', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member, role='tester')
        self.knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Requirement OCR KB',
            created_by=self.owner,
        )
        self.engine = OcrEngineConfig.objects.create(
            name='Local text OCR',
            engine_type=OcrEngineConfig.ENGINE_EASYOCR,
            is_default=True,
            created_by=self.owner,
        )

    def test_text_ocr_run_creates_page_rows_and_page_endpoint(self):
        task = OcrTask.objects.create(
            project=self.project,
            engine=self.engine,
            name='Requirement Page',
            source_type=OcrTask.SOURCE_TEXT,
            input_text='first requirement\nsecond requirement',
            created_by=self.owner,
        )

        run_ocr_task(task)

        task.refresh_from_db()
        self.assertEqual(task.status, OcrTask.STATUS_SUCCEEDED)
        self.assertEqual(task.pages.count(), 1)
        self.assertEqual(task.pages.first().page_number, 1)

        self.client.force_authenticate(user=self.member)
        response = self.client.get(f'/api/ocr-service/tasks/{task.id}/pages/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertIn('first requirement', response.data[0]['text'])

    def test_import_ocr_preserves_page_metadata_in_knowledge_chunks(self):
        task = OcrTask.objects.create(
            project=self.project,
            engine=self.engine,
            name='Scanned Requirement',
            source_type=OcrTask.SOURCE_PDF,
            extracted_text='login page must reject invalid passwords\n\ncheckout page must show confirmation',
            status=OcrTask.STATUS_SUCCEEDED,
            created_by=self.owner,
        )
        OcrPage.objects.create(
            task=task,
            page_number=1,
            text='login page must reject invalid passwords',
            confidence=0.91,
        )
        OcrPage.objects.create(
            task=task,
            page_number=2,
            text='checkout page must show confirmation',
            confidence=0.93,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            '/api/knowledge-base/documents/import_ocr/',
            {
                'knowledge_base': self.knowledge_base.id,
                'ocr_task': task.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        document = KnowledgeDocument.objects.get(id=response.data['id'])
        self.assertEqual(document.metadata['ocr_page_count'], 2)
        self.assertEqual(document.status, KnowledgeDocument.STATUS_INDEXED)
        self.assertEqual(document.chunks.count(), 2)
        self.assertEqual(
            set(document.chunks.values_list('metadata__page_number', flat=True)),
            {1, 2},
        )

        search_response = self.client.get(
            '/api/knowledge-base/queries/search/',
            {'knowledge_base': self.knowledge_base.id, 'question': 'checkout confirmation'},
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertTrue(any(hit['page_number'] == 2 for hit in search_response.data))

    def test_import_ocr_batch_creates_multiple_documents(self):
        first = OcrTask.objects.create(
            project=self.project,
            engine=self.engine,
            name='First OCR',
            source_type=OcrTask.SOURCE_TEXT,
            extracted_text='first requirement text',
            status=OcrTask.STATUS_SUCCEEDED,
            created_by=self.owner,
        )
        second = OcrTask.objects.create(
            project=self.project,
            engine=self.engine,
            name='Second OCR',
            source_type=OcrTask.SOURCE_TEXT,
            extracted_text='second requirement text',
            status=OcrTask.STATUS_SUCCEEDED,
            created_by=self.owner,
        )

        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            '/api/knowledge-base/documents/import_ocr/',
            {
                'knowledge_base': self.knowledge_base.id,
                'ocr_tasks': [first.id, second.id],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            KnowledgeDocument.objects.filter(knowledge_base=self.knowledge_base).count(),
            2,
        )
