from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import RequestPerformanceMetric


class RequestPerformanceMonitoringTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='perf-user', password='pass')
        self.other_user = User.objects.create_user(username='other-perf-user', password='pass')
        self.staff = User.objects.create_user(username='perf-staff', password='pass', is_staff=True)

    @override_settings(REQUEST_PERFORMANCE_SLOW_THRESHOLD_MS=0)
    def test_middleware_records_request_metric_and_response_header(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/projects/all/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('X-TestHub-Response-Time-Ms', response)
        metric = RequestPerformanceMetric.objects.filter(path='/api/projects/all/').latest('created_at')
        self.assertEqual(metric.method, 'GET')
        self.assertEqual(metric.status_code, 200)
        self.assertEqual(metric.user, self.user)
        self.assertTrue(metric.is_slow)

    def test_summary_trends_slow_and_error_endpoints(self):
        RequestPerformanceMetric.objects.create(
            method='GET',
            path='/api/a/',
            status_code=200,
            response_time_ms=120,
            user=self.user,
        )
        RequestPerformanceMetric.objects.create(
            method='POST',
            path='/api/b/',
            status_code=500,
            response_time_ms=1500,
            is_slow=True,
            is_error=True,
            user=self.user,
        )
        RequestPerformanceMetric.objects.create(
            method='GET',
            path='/api/hidden/',
            status_code=404,
            response_time_ms=30,
            is_error=True,
            user=self.other_user,
        )
        self.client.force_authenticate(user=self.user)

        summary_response = self.client.get('/api/core/performance-metrics/summary/')
        trends_response = self.client.get('/api/core/performance-metrics/trends/')
        slow_response = self.client.get('/api/core/performance-metrics/slow-requests/')
        error_response = self.client.get('/api/core/performance-metrics/error-requests/')

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data['total'], 2)
        self.assertEqual(summary_response.data['slow_count'], 1)
        self.assertEqual(summary_response.data['error_count'], 1)
        self.assertEqual(summary_response.data['status_groups']['2xx'], 1)
        self.assertEqual(summary_response.data['status_groups']['5xx'], 1)
        self.assertEqual(trends_response.status_code, 200)
        self.assertGreaterEqual(len(trends_response.data), 1)
        self.assertEqual(len(slow_response.data), 1)
        self.assertEqual(slow_response.data[0]['path'], '/api/b/')
        self.assertEqual(len(error_response.data), 1)
        self.assertEqual(error_response.data[0]['status_code'], 500)

    def test_staff_can_see_all_metrics(self):
        RequestPerformanceMetric.objects.create(
            method='GET',
            path='/api/a/',
            status_code=200,
            response_time_ms=120,
            user=self.user,
        )
        RequestPerformanceMetric.objects.create(
            method='GET',
            path='/api/b/',
            status_code=200,
            response_time_ms=150,
            user=self.other_user,
        )
        self.client.force_authenticate(user=self.staff)

        response = self.client.get('/api/core/performance-metrics/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 2)
