from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import UnifiedAuditLog
from apps.ocr_service.models import OcrBatch, OcrEngineConfig, OcrTask
from apps.projects.models import Project


class OcrServiceBatchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.other_owner = User.objects.create_user(username='other-owner', password='pass')
        self.project = Project.objects.create(name='OCR Project', owner=self.owner)
        self.other_project = Project.objects.create(name='Other OCR Project', owner=self.other_owner)
        self.engine = OcrEngineConfig.objects.create(
            name='Text passthrough',
            engine_type=OcrEngineConfig.ENGINE_CUSTOM,
            base_url='https://ocr.example/extract',
            is_default=True,
            created_by=self.owner,
        )
        self.other_engine = OcrEngineConfig.objects.create(
            name='Other text passthrough',
            engine_type=OcrEngineConfig.ENGINE_CUSTOM,
            base_url='https://ocr.example/other',
            is_default=True,
            created_by=self.other_owner,
        )

    def test_batch_endpoint_creates_and_runs_text_tasks(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            '/api/ocr-service/tasks/batch/',
            {
                'project': self.project.id,
                'engine': self.engine.id,
                'name': 'Requirement OCR Batch',
                'run_immediately': True,
                'items': [
                    {'name': 'Page 1', 'source_type': 'text', 'input_text': 'first line\nsecond line'},
                    {'name': 'Page 2', 'source_type': 'text', 'input_text': 'third line'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        batch = OcrBatch.objects.get(id=response.data['batch']['id'])
        self.assertEqual(batch.status, OcrBatch.STATUS_SUCCEEDED)
        self.assertEqual(batch.total_tasks, 2)
        self.assertEqual(batch.succeeded_tasks, 2)

        task = OcrTask.objects.get(name='Page 1')
        self.assertEqual(task.status, OcrTask.STATUS_SUCCEEDED)
        self.assertEqual(task.attempt, 1)
        self.assertIsNotNone(task.started_at)
        self.assertIsNotNone(task.finished_at)
        self.assertEqual(task.result_json['schema_version'], '1.0')
        self.assertEqual(len(task.result_json['pages'][0]['blocks']), 2)

        list_response = self.client.get('/api/ocr-service/tasks/', {'batch': batch.id})
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data['count'], 2)

    def test_engine_preflight_persists_health_result(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(f'/api/ocr-service/engines/{self.engine.id}/preflight/')

        self.assertEqual(response.status_code, 200)
        self.engine.refresh_from_db()
        self.assertIsNotNone(self.engine.last_checked_at)
        self.assertEqual(self.engine.last_check_result['engine_type'], OcrEngineConfig.ENGINE_CUSTOM)
        self.assertTrue(self.engine.last_check_result['ready'])

    def test_batch_upload_endpoint_creates_file_tasks(self):
        self.client.force_authenticate(user=self.owner)
        first_file = SimpleUploadedFile('one.png', b'fake image one', content_type='image/png')
        second_file = SimpleUploadedFile('two.pdf', b'%PDF-1.4 fake', content_type='application/pdf')

        response = self.client.post(
            '/api/ocr-service/tasks/batch_upload/',
            {
                'project': str(self.project.id),
                'engine': str(self.engine.id),
                'name': 'File OCR Batch',
                'files': [first_file, second_file],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        batch = OcrBatch.objects.get(id=response.data['batch']['id'])
        self.assertEqual(batch.total_tasks, 2)
        self.assertEqual(batch.status, OcrBatch.STATUS_PENDING)
        self.assertEqual(
            set(batch.tasks.values_list('source_type', flat=True)),
            {OcrTask.SOURCE_IMAGE, OcrTask.SOURCE_PDF},
        )
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='ocr_service',
                object_type='ocr_batch',
                object_id=str(batch.id),
                actor=self.owner,
                metadata__operation='batch_upload',
            ).exists()
        )

    def test_run_pending_is_limited_to_accessible_tasks(self):
        owner_task = OcrTask.objects.create(
            project=self.project,
            engine=self.engine,
            name='Owner pending',
            source_type=OcrTask.SOURCE_TEXT,
            input_text='owner text',
            created_by=self.owner,
        )
        foreign_task = OcrTask.objects.create(
            project=self.other_project,
            engine=self.other_engine,
            name='Foreign pending',
            source_type=OcrTask.SOURCE_TEXT,
            input_text='foreign text',
            created_by=self.other_owner,
        )

        self.client.force_authenticate(user=self.owner)
        response = self.client.post('/api/ocr-service/tasks/run_pending/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['succeeded'], 1)
        owner_task.refresh_from_db()
        foreign_task.refresh_from_db()
        self.assertEqual(owner_task.status, OcrTask.STATUS_SUCCEEDED)
        self.assertEqual(foreign_task.status, OcrTask.STATUS_PENDING)
        self.assertEqual(foreign_task.attempt, 0)
        self.assertTrue(
            UnifiedAuditLog.objects.filter(
                domain='ocr_service',
                object_type='ocr_queue',
                actor=self.owner,
                metadata__operation='run_pending',
            ).exists()
        )
