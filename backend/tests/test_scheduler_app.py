from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class SchedulerAppTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username='scheduler-owner', password='pass')
        # /api/scheduler/run-due/ 仅 admin 可调用（参见 SchedulerRunDueJobsView）
        self.admin = get_user_model().objects.create_user(
            username='scheduler-admin', password='pass', is_staff=True, is_superuser=True
        )

    def test_capabilities_requires_authentication(self):
        response = self.client.get('/api/scheduler/capabilities/')
        self.assertIn(response.status_code, {401, 403})

    def test_capabilities_exposes_independent_scheduler_boundary(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/scheduler/capabilities/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['independent_app'])
        self.assertTrue(response.data['supports_dependencies'])
        self.assertTrue(response.data['supports_retries'])
        self.assertIn(response.data['backend'], {'local', 'django_q2'})

    def test_run_due_rejects_non_admin(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post('/api/scheduler/run-due/', {'dry_run': True}, format='json')

        self.assertEqual(response.status_code, 403)

    def test_run_due_supports_dry_run(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post('/api/scheduler/run-due/', {'dry_run': True}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['queued'])
        self.assertEqual(response.data['summary']['due'], 0)
