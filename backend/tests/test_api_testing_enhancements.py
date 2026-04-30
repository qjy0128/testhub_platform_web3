from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.api_testing.extractors import extract_response_variables
from apps.api_testing.models import ApiCollection, ApiProject, ApiRequest, Environment, TestSuite


class FakeResponse:
    status_code = 200
    headers = {'content-type': 'application/json', 'X-Trace': 'trace-1'}
    text = '{"token": "abc123", "items": [{"id": 7}]}'

    def json(self):
        return {'token': 'abc123', 'items': [{'id': 7}]}


class ApiTestingEnhancementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username='api-owner', password='pass')
        self.client.force_authenticate(user=self.user)
        self.project = ApiProject.objects.create(
            name='API Star Project',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=self.user,
        )
        self.collection = ApiCollection.objects.create(project=self.project, name='Users')

    def test_response_extractors_support_jsonpath_and_headers(self):
        values, details = extract_response_variables(FakeResponse(), [
            {'name': 'token', 'type': 'jsonpath', 'expression': '$.token'},
            {'name': 'trace', 'type': 'header', 'expression': 'X-Trace'},
        ])

        self.assertEqual(values['token'], 'abc123')
        self.assertEqual(values['trace'], 'trace-1')
        self.assertEqual(len(details), 2)

    def test_single_request_execute_persists_extracted_variables_to_environment(self):
        api_request = ApiRequest.objects.create(
            collection=self.collection,
            name='Login',
            method='POST',
            url='https://example.test/login',
            extractors=[{'name': 'token', 'type': 'jsonpath', 'expression': '$.token'}],
            created_by=self.user,
        )
        environment = Environment.objects.create(
            name='Local',
            scope='LOCAL',
            project=self.project,
            variables={},
            created_by=self.user,
        )

        with patch('apps.api_testing.views.requests.request', return_value=FakeResponse()):
            response = self.client.post(
                f'/api/api-testing/requests/{api_request.id}/execute/',
                {'environment_id': environment.id},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['extracted_variables']['token'], 'abc123')
        environment.refresh_from_db()
        self.assertEqual(environment.variables['token'], 'abc123')

    def test_project_imports_postman_and_exports_openapi(self):
        postman_payload = {
            'info': {'name': 'Imported Collection'},
            'item': [
                {
                    'name': 'Get Users',
                    'request': {
                        'method': 'GET',
                        'url': {
                            'raw': 'https://example.test/users?page=1',
                            'query': [{'key': 'page', 'value': '1'}],
                        },
                        'header': [{'key': 'Accept', 'value': 'application/json'}],
                    },
                }
            ],
        }

        import_response = self.client.post(
            f'/api/api-testing/projects/{self.project.id}/import-postman/',
            postman_payload,
            format='json',
        )
        self.assertEqual(import_response.status_code, 201)
        self.assertEqual(import_response.data['requests'], 1)

        imported_request = ApiRequest.objects.get(name='Get Users')
        imported_request.extractors = [{'name': 'user_id', 'type': 'jsonpath', 'expression': '$.id'}]
        imported_request.save(update_fields=['extractors'])

        export_response = self.client.get(f'/api/api-testing/projects/{self.project.id}/export-openapi/')
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.data['openapi'], '3.0.3')
        self.assertIn('/users', export_response.data['paths'])
        self.assertEqual(
            export_response.data['paths']['/users']['get']['x-testhub-extractors'][0]['name'],
            'user_id',
        )

    def test_project_imports_har_entries(self):
        har_payload = {
            'log': {
                'entries': [
                    {
                        'request': {
                            'method': 'POST',
                            'url': 'https://example.test/orders',
                            'headers': [{'name': 'Content-Type', 'value': 'application/json'}],
                            'postData': {'text': '{"sku": "A-1"}'},
                        }
                    }
                ]
            }
        }

        response = self.client.post(
            f'/api/api-testing/projects/{self.project.id}/import-har/',
            har_payload,
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['requests'], 1)
        self.assertTrue(ApiRequest.objects.filter(collection__project=self.project, name='POST /orders').exists())

    def test_suite_parameterized_views_can_store_data_sets(self):
        suite = TestSuite.objects.create(project=self.project, name='Parameterized Suite', created_by=self.user)

        response = self.client.post(
            f'/api/api-testing/test-suites/{suite.id}/parameterized-views/',
            {'enabled': True, 'data_sets': [{'username': 'alice'}, {'username': 'bob'}]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['enabled'])
        self.assertEqual(response.data['count'], 2)
        suite.refresh_from_db()
        self.assertEqual(suite.parameterized_data[1]['username'], 'bob')
