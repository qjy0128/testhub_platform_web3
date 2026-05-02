import os
import importlib
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from apps.app_automation.consumers import AppExecutionConsumer
from apps.app_automation.utils.path_safety import (
    MAX_IMAGE_UPLOAD_SIZE,
    UnsafeTemplatePath,
    normalize_template_relative_path,
    safe_template_join,
    validate_image_upload,
)
from apps.app_automation.views.config_views import AppConfigViewSet
from apps.app_automation.views.device_views import AppDeviceViewSet, get_allowed_scrcpy_path
from apps.app_automation.views.execution_views import serve_report_file
from apps.app_automation.views.element_views import AppElementViewSet
from apps.app_automation.views.test_case_views import AppTestCaseViewSet
from apps.app_automation.views.scheduled_task_views import AppScheduledTaskViewSet
from apps.assistant.views import ChatViewSet
from apps.assistant.views_config import DifyConfigViewSet, validate_dify_api_url
from apps.api_testing.models import AIServiceConfig, ApiRequest
from apps.api_testing.serializers import (
    AIServiceConfigSerializer as ApiAIServiceConfigBoundarySerializer,
    ApiCollectionSerializer as ApiCollectionBoundarySerializer,
    ApiRequestSerializer as ApiRequestBoundarySerializer,
    EnvironmentSerializer as ApiEnvironmentBoundarySerializer,
    ScheduledTaskSerializer as ApiScheduledTaskBoundarySerializer,
    TaskNotificationSettingDetailSerializer,
    TestSuiteSerializer as ApiTestSuiteBoundarySerializer,
)
from apps.api_testing.utils import validate_api_request_url
from apps.api_testing.views import AIServiceConfigViewSet
from apps.api_testing.views import (
    ApiDashboardViewSet,
    EnvironmentViewSet,
    OperationLogViewSet,
    RequestHistoryViewSet,
    TestSuiteViewSet as ApiTestingTestSuiteViewSet,
    accessible_api_requests_for_user,
    accessible_environments_for_user,
)
import backend.urls as backend_urls
from apps.core.notification_safety import validate_notification_webhook_bots
from apps.core.models import UnifiedNotificationConfig
from apps.core.serializers import UnifiedNotificationConfigSerializer
from apps.core.views import UnifiedNotificationConfigViewSet
from apps.executions.views import (
    TestPlanViewSet,
    TestRunCaseHistoryViewSet,
    TestRunCaseViewSet,
    TestRunViewSet,
)
from apps.knowledge_base.serializers import KnowledgeBaseSerializer
from apps.knowledge_base.services import OpenAICompatibleEmbeddingProvider
from apps.ocr_service.serializers import OcrEngineConfigSerializer
from apps.ocr_service.services import build_chat_completions_url as build_ocr_chat_completions_url
from apps.app_automation.models import AppProject
from apps.projects.models import Project
from apps.projects.views import ProjectDetailView
from apps.reports.views import TestReportViewSet
from apps.requirement_analysis.models import AIModelService
from apps.requirement_analysis.serializers import AIModelConfigSerializer
from apps.requirement_analysis.views import (
    AIModelConfigViewSet,
    AnalysisTaskViewSet,
    BusinessRequirementViewSet,
    ConfigStatusViewSet,
    GeneratedTestCaseViewSet,
    GenerationConfigViewSet,
    PromptConfigViewSet,
    RequirementAnalysisViewSet,
    RequirementDocumentViewSet,
    TestCaseGenerationTaskViewSet,
    analyze_text,
    upload_and_analyze,
)
from apps.ui_automation.views_config import (
    AIIntelligentModeConfigViewSet,
    EnvironmentConfigViewSet,
    WalletBrowserConfigViewSet,
)
from apps.ui_automation.models import TestCase as UiTestCase
from apps.ui_automation.models import TestScript as UiTestScript
from apps.ui_automation.models import UiProject as UiAutomationProject
from apps.ui_automation.serializers import (
    ElementSerializer as UiElementBoundarySerializer,
    TestCaseSerializer as UiTestCaseBoundarySerializer,
    TestScriptCreateSerializer as UiTestScriptCreateBoundarySerializer,
    TestSuiteCreateSerializer as UiTestSuiteCreateBoundarySerializer,
    UiScheduledTaskSerializer as UiScheduledTaskBoundarySerializer,
    UiTaskNotificationSettingSerializer,
)
import apps.ui_automation.urls as ui_automation_urls
from apps.ui_automation.views import (
    ScriptElementUsageViewSet,
    TestCaseStepViewSet as UiTestCaseStepViewSet,
    TestCaseViewSet as UiTestCaseViewSet,
    TestSuiteViewSet as UiTestSuiteViewSet,
    accessible_test_cases_for_user as accessible_ui_test_cases_for_user,
    accessible_test_scripts_for_user as accessible_ui_test_scripts_for_user,
    accessible_ui_projects_for_user,
)
from apps.users.views import UserDetailView, UserListView


class WorkspaceTemporaryDirectory:
    def __init__(self):
        self.name = None

    def __enter__(self):
        root = Path.cwd() / '.tmp-tests'
        root.mkdir(exist_ok=True)
        path = root / f'tmp-{uuid.uuid4().hex}'
        path.mkdir()
        self.name = str(path)
        return self.name

    def __exit__(self, exc_type, exc, traceback):
        self.cleanup()

    def cleanup(self):
        if self.name:
            shutil.rmtree(self.name, ignore_errors=True)
            self.name = None


def temporary_directory():
    return WorkspaceTemporaryDirectory()


class ApiCsrfConfigurationTests(SimpleTestCase):
    def test_api_csrf_disable_middleware_is_not_installed(self):
        # backend.middleware.DisableCSRFMiddleware 已被彻底移除；保留断言防止回滚误装。
        self.assertNotIn('backend.middleware.DisableCSRFMiddleware', settings.MIDDLEWARE)
        self.assertFalse(
            any('DisableCSRF' in m for m in settings.MIDDLEWARE),
            'No CSRF-disabling middleware should be installed',
        )


class AppAutomationTemplatePathSafetyTests(SimpleTestCase):
    def test_template_relative_path_is_normalized_for_safe_images(self):
        self.assertEqual(
            normalize_template_relative_path(r'common\login.png'),
            'common/login.png',
        )

    def test_template_join_rejects_paths_outside_template_root(self):
        with temporary_directory() as tmp:
            with self.assertRaises(UnsafeTemplatePath):
                safe_template_join(Path(tmp), '../secret.png')
            with self.assertRaises(UnsafeTemplatePath):
                safe_template_join(Path(tmp), r'C:\secret.png')

    def test_template_join_rejects_non_image_extensions(self):
        with temporary_directory() as tmp:
            with self.assertRaises(UnsafeTemplatePath):
                safe_template_join(Path(tmp), 'common/payload.html')

    def test_image_upload_rejects_oversized_files(self):
        upload = SimpleNamespace(name='login.png', size=MAX_IMAGE_UPLOAD_SIZE + 1)
        with self.assertRaises(UnsafeTemplatePath):
            validate_image_upload(upload)

    def test_element_image_config_path_is_normalized_on_write(self):
        with temporary_directory() as tmp:
            serializer = SimpleNamespace(
                validated_data={
                    'element_type': 'image',
                    'config': {'image_path': r'common\login.png'},
                },
                instance=None,
            )
            view = AppElementViewSet()
            view.get_template_base_path = lambda: Path(tmp)

            view._validate_image_config(serializer)

            self.assertEqual(serializer.validated_data['config']['image_path'], 'common/login.png')

    def test_element_image_config_rejects_escaped_paths(self):
        with temporary_directory() as tmp:
            serializer = SimpleNamespace(
                validated_data={
                    'element_type': 'image',
                    'config': {'image_path': '../secret.png'},
                },
                instance=None,
            )
            view = AppElementViewSet()
            view.get_template_base_path = lambda: Path(tmp)

            with self.assertRaises(DRFValidationError):
                view._validate_image_config(serializer)


class ProjectDetailAuthorizationTests(SimpleTestCase):
    def test_project_detail_queryset_is_limited_to_owned_or_joined_projects(self):
        user = get_user_model()(id=42, username='owner')
        request = RequestFactory().get('/api/projects/1/')
        request.user = user

        view = ProjectDetailView()
        view.request = request

        sql = str(view.get_queryset().query)

        self.assertIn('owner_id', sql)
        self.assertIn('project_members', sql)


class RequirementAnalysisAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model()(id=202, username='requirements-user')

    def _attach_request(self, view, path):
        request = self.factory.get(path)
        request.user = self.user
        request.query_params = request.GET
        view.request = request
        return view

    def test_upload_and_text_analysis_require_authentication(self):
        self.assertEqual(upload_and_analyze.cls.permission_classes, [IsAuthenticated])
        self.assertEqual(analyze_text.cls.permission_classes, [IsAuthenticated])

    def test_requirement_document_queryset_is_limited_to_owner_or_accessible_project(self):
        view = self._attach_request(
            RequirementDocumentViewSet(),
            '/api/requirement-analysis/documents/',
        )

        with patch(
            'apps.requirement_analysis.views.accessible_projects_for_user',
            return_value=Project.objects.filter(id=123),
        ):
            sql = str(view.get_queryset().query)

        self.assertIn('uploaded_by_id', sql)
        self.assertIn('project_id', sql)

    def test_requirement_child_viewsets_use_document_scope(self):
        accessible_projects = Project.objects.filter(id=123)
        cases = [
            (RequirementAnalysisViewSet(), '/api/requirement-analysis/analyses/'),
            (BusinessRequirementViewSet(), '/api/requirement-analysis/requirements/'),
            (GeneratedTestCaseViewSet(), '/api/requirement-analysis/test-cases/'),
            (AnalysisTaskViewSet(), '/api/requirement-analysis/tasks/'),
        ]

        with patch(
            'apps.requirement_analysis.views.accessible_projects_for_user',
            return_value=accessible_projects,
        ):
            sql_statements = [
                str(self._attach_request(view, path).get_queryset().query)
                for view, path in cases
            ]

        for sql in sql_statements:
            self.assertIn('requirement_documents', sql)
            self.assertIn('uploaded_by_id', sql)
            self.assertIn('project_id', sql)


class UserManagementAuthorizationTests(SimpleTestCase):
    def test_user_management_requires_admin(self):
        self.assertEqual(UserListView.permission_classes, [IsAdminUser])
        self.assertEqual(UserDetailView.permission_classes, [IsAdminUser])


class AssistantConfigSecurityTests(SimpleTestCase):
    def test_dify_config_requires_admin(self):
        self.assertEqual(DifyConfigViewSet.permission_classes, [IsAdminUser])

    @override_settings(DEBUG=False)
    def test_dify_api_url_rejects_private_targets_in_production(self):
        with self.assertRaises(ValueError):
            validate_dify_api_url('http://127.0.0.1:5001')

    @override_settings(DEBUG=False)
    def test_chat_runtime_rejects_historical_private_dify_config(self):
        request = SimpleNamespace(
            data={'session_id': 'session-1', 'message': 'hello'},
            user=SimpleNamespace(id=1),
        )
        session = SimpleNamespace(conversation_id=None)
        dify_config = SimpleNamespace(api_url='http://127.0.0.1:5001', api_key='token')

        with (
            patch('apps.assistant.views.AssistantSession.objects.get', return_value=session),
            patch('apps.assistant.views.DifyConfig.get_active_config', return_value=dify_config),
            patch('apps.assistant.views.ChatMessage.objects.create', return_value=SimpleNamespace()),
            patch('apps.assistant.views.requests.post') as request_post,
        ):
            response = ChatViewSet().send_message(request)

        self.assertEqual(response.status_code, 400)
        request_post.assert_not_called()


class AIOutboundUrlSecurityTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_api_testing_ai_base_url_rejects_private_targets_in_production(self):
        view = AIServiceConfigViewSet()
        with self.assertRaises(ValueError):
            view._chat_completions_url('http://127.0.0.1:8000/v1')

    @override_settings(DEBUG=False)
    def test_api_testing_request_url_rejects_private_targets_in_production(self):
        with self.assertRaises(ValueError):
            validate_api_request_url('http://127.0.0.1:9000/internal')

    @override_settings(DEBUG=False)
    def test_ocr_engine_base_url_rejects_private_targets_in_production(self):
        with self.assertRaises(ValueError):
            build_ocr_chat_completions_url('http://127.0.0.1:9000/v1')

        serializer = OcrEngineConfigSerializer()
        with self.assertRaises(DRFValidationError):
            serializer.validate_base_url('http://127.0.0.1:9000/ocr')

    @override_settings(DEBUG=False)
    def test_knowledge_base_embedding_url_rejects_private_targets_in_production(self):
        provider = OpenAICompatibleEmbeddingProvider(SimpleNamespace(
            embedding_model='text-embedding-test',
            metadata={
                'embedding': {
                    'base_url': 'http://127.0.0.1:9001/v1',
                    'api_key': 'secret',
                }
            },
        ))

        with self.assertRaises(ValueError):
            provider._resolve_embeddings_url()

        serializer = KnowledgeBaseSerializer()
        with self.assertRaises(DRFValidationError):
            serializer.validate_metadata({
                'embedding': {
                    'base_url': 'http://127.0.0.1:9001/v1',
                }
            })

    @override_settings(DEBUG=False)
    def test_requirement_ai_base_url_rejects_private_targets_in_production(self):
        with self.assertRaises(ValueError):
            AIModelService.build_chat_completions_url('http://127.0.0.1:9002/v1')

        serializer = AIModelConfigSerializer()
        with self.assertRaises(DRFValidationError):
            serializer.validate_base_url('http://127.0.0.1:9002/v1')

    def test_requirement_global_ai_config_requires_admin(self):
        self.assertEqual(AIModelConfigViewSet.permission_classes, [IsAdminUser])
        self.assertEqual(PromptConfigViewSet.permission_classes, [IsAdminUser])
        self.assertEqual(GenerationConfigViewSet.permission_classes, [IsAdminUser])

    def test_ui_local_tooling_and_ai_config_require_admin(self):
        self.assertEqual(EnvironmentConfigViewSet.permission_classes, [IsAdminUser])
        self.assertEqual(AIIntelligentModeConfigViewSet.permission_classes, [IsAdminUser])
        self.assertEqual(WalletBrowserConfigViewSet.permission_classes, [IsAdminUser])

    def test_api_testing_ai_config_serializer_masks_api_key(self):
        config = AIServiceConfig(
            id=1,
            name='api-ai',
            service_type='openai',
            role='description',
            api_key='sk-secret-key-value',
            base_url='https://api.example.com/v1',
            model_name='gpt-test',
            created_by=get_user_model()(id=1, username='owner'),
        )

        data = ApiAIServiceConfigBoundarySerializer(config).data
        serialized = str(data)

        self.assertNotIn('api_key', data)
        self.assertIn('api_key_masked', data)
        self.assertIn('*', data['api_key_masked'])
        self.assertNotEqual(data['api_key_masked'], config.api_key)
        self.assertNotIn(config.api_key, serialized)

    def test_task_notification_detail_serializer_redacts_webhook_secrets(self):
        class EmptyRecipients:
            def all(self):
                return []

        notification_config = SimpleNamespace(
            id=7,
            pk=7,
            name='global webhook',
            config_type='webhook_feishu',
            get_webhook_bots=lambda: [
                {
                    'type': 'feishu',
                    'name': 'global feishu',
                    'webhook_url': 'https://open.feishu.cn/open-apis/bot/v2/hook/global-secret-token',
                    'enabled': True,
                    'secret': 'global-signing-secret',
                },
                {
                    'type': 'dingtalk',
                    'name': 'global dingtalk',
                    'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=global-access-token',
                    'enabled': True,
                    'secret': 'dingtalk-signing-secret',
                },
            ],
        )
        setting = SimpleNamespace(
            id=9,
            task=SimpleNamespace(pk=11),
            notification_type='webhook',
            notification_config=notification_config,
            is_enabled=True,
            notify_on_success=True,
            notify_on_failure=True,
            notify_on_timeout=False,
            notify_on_error=True,
            custom_webhook_bots={
                'feishu': {
                    'name': 'custom feishu',
                    'webhook_url': 'https://open.feishu.cn/open-apis/bot/v2/hook/custom-secret-token',
                    'enabled': True,
                    'secret': 'custom-signing-secret',
                }
            },
            custom_recipients=EmptyRecipients(),
            created_at=None,
            updated_at=None,
            get_notification_type_display=lambda: 'Webhook',
            get_notification_config=lambda: notification_config,
        )

        data = TaskNotificationSettingDetailSerializer(setting).data
        serialized = str(data)

        self.assertNotIn('custom_webhook_bots', data)
        self.assertNotIn('custom-secret-token', serialized)
        self.assertNotIn('global-secret-token', serialized)
        self.assertNotIn('global-access-token', serialized)
        self.assertNotIn('custom-signing-secret', serialized)
        self.assertNotIn('global-signing-secret', serialized)
        for bot in data['webhook_bots_display']:
            self.assertTrue(bot['webhook_url'].endswith('/***'))


class ApiTestingAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model()(id=303, username='api-user')

    def _attach_request(self, view, path, method='get'):
        request = getattr(self.factory, method)(path)
        request.user = self.user
        request.query_params = request.GET
        view.request = request
        return view

    def _serializer_context(self):
        request = self.factory.post('/api/api-testing/')
        request.user = self.user
        return {'request': request}

    def test_api_request_queryset_is_limited_to_accessible_projects_or_creator(self):
        sql = str(accessible_api_requests_for_user(self.user).query)

        self.assertIn('api_collections', sql)
        self.assertIn('project_id', sql)
        self.assertIn('created_by_id', sql)

    def test_request_history_queryset_uses_accessible_request_scope(self):
        view = self._attach_request(RequestHistoryViewSet(), '/api/api-testing/history/')

        sql = str(view.get_queryset().query)

        self.assertIn('api_request_histories', sql)
        self.assertIn('api_collections', sql)
        self.assertIn('created_by_id', sql)

    def test_environment_read_scope_includes_global_and_accessible_local(self):
        sql = str(accessible_environments_for_user(self.user).query)

        self.assertIn('scope', sql)
        self.assertIn('GLOBAL', sql)
        self.assertIn('project_id', sql)

    def test_global_environment_writes_are_admin_only(self):
        view = self._attach_request(EnvironmentViewSet(), '/api/api-testing/environments/', method='post')

        sql = str(view.get_queryset().query)

        self.assertIn('scope', sql)
        self.assertIn('GLOBAL', sql)
        with self.assertRaises(DRFPermissionDenied):
            view._ensure_global_environment_write_allowed('GLOBAL')

    def test_suite_request_addition_uses_accessible_request_scope(self):
        request = self.factory.post('/api/api-testing/ai-service/complete_parameter_descriptions/')
        request.user = self.user
        view = AIServiceConfigViewSet()
        view.request = request

        with patch('apps.api_testing.views.accessible_api_requests_for_user') as accessible:
            accessible.return_value.get.side_effect = ApiRequest.DoesNotExist
            with self.assertRaises(ApiRequest.DoesNotExist):
                view._get_accessible_api_request(123)

        accessible.assert_called_once_with(self.user)
        accessible.return_value.get.assert_called_once_with(id=123)

    def test_api_test_suite_queryset_is_project_scoped(self):
        view = self._attach_request(ApiTestingTestSuiteViewSet(), '/api/api-testing/test-suites/')

        sql = str(view.get_queryset().query)

        self.assertIn('project_id', sql)
        self.assertIn('api_projects', sql)

    def test_operation_log_queryset_is_limited_for_non_admins(self):
        view = self._attach_request(OperationLogViewSet(), '/api/api-testing/operation-logs/')

        sql = str(view.get_queryset().query)

        self.assertIn('user_id', sql)

    def test_api_dashboard_requires_authentication(self):
        self.assertEqual(ApiDashboardViewSet.permission_classes, [IsAuthenticated])

    def test_api_related_serializer_fields_are_scoped_to_accessible_projects(self):
        context = self._serializer_context()

        collection_serializer = ApiCollectionBoundarySerializer(context=context)
        request_serializer = ApiRequestBoundarySerializer(context=context)
        environment_serializer = ApiEnvironmentBoundarySerializer(context=context)
        suite_serializer = ApiTestSuiteBoundarySerializer(context=context)
        task_serializer = ApiScheduledTaskBoundarySerializer(context=context)

        self.assertIn('owner_id', str(collection_serializer.fields['project'].queryset.query))
        self.assertIn('api_projects_members', str(collection_serializer.fields['parent'].queryset.query))
        self.assertIn('api_projects', str(request_serializer.fields['collection'].queryset.query))
        self.assertIn('owner_id', str(environment_serializer.fields['project'].queryset.query))
        self.assertIn('GLOBAL', str(suite_serializer.fields['environment'].queryset.query))
        self.assertIn('api_test_suites', str(task_serializer.fields['test_suite'].queryset.query))
        self.assertIn('created_by_id', str(task_serializer.fields['api_request'].queryset.query))

    def test_api_environment_serializer_blocks_non_admin_global_writes(self):
        serializer = ApiEnvironmentBoundarySerializer(
            data={'name': 'global-env', 'scope': 'GLOBAL', 'variables': {}},
            context=self._serializer_context(),
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('scope', serializer.errors)


class BackendUrlExposureTests(SimpleTestCase):
    def test_app_automation_templates_are_debug_only(self):
        try:
            with override_settings(DEBUG=False):
                module = importlib.reload(backend_urls)
                routes = [str(pattern.pattern) for pattern in module.urlpatterns]

            self.assertNotIn('app-automation-templates/<path:path>', routes)
        finally:
            importlib.reload(backend_urls)


class UiAutomationAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model()(id=404, username='ui-user')

    def _attach_request(self, view, path, method='get'):
        request = getattr(self.factory, method)(path)
        request.user = self.user
        request.query_params = request.GET
        request.data = {}
        view.request = request
        return view

    def _serializer_context(self):
        request = self.factory.post('/api/ui-automation/')
        request.user = self.user
        return {'request': request}

    def test_ui_project_scope_uses_owner_or_membership(self):
        sql = str(accessible_ui_projects_for_user(self.user).query)

        self.assertIn('owner_id', sql)
        self.assertIn('ui_projects_members', sql)

    def test_ui_test_case_queryset_is_project_scoped(self):
        view = self._attach_request(UiTestCaseViewSet(), '/api/ui-automation/test-cases/')

        sql = str(view.get_queryset().query)

        self.assertIn('ui_test_cases', sql)
        self.assertIn('project_id', sql)

    def test_ui_test_case_steps_use_accessible_test_case_scope(self):
        view = self._attach_request(UiTestCaseStepViewSet(), '/api/ui-automation/test-case-steps/')

        sql = str(view.get_queryset().query)

        self.assertIn('ui_test_case_steps', sql)
        self.assertIn('ui_test_cases', sql)
        self.assertIn('project_id', sql)

    def test_script_analysis_uses_accessible_script_scope(self):
        request = self.factory.post('/api/ui-automation/script-usages/analyze_script/')
        request.user = self.user
        request.data = {'script_id': 123}
        view = ScriptElementUsageViewSet()

        # patch 实际调用点（views.scripts 模块内的本地绑定），而不是 views 包级 re-export，
        # 否则 mock 不会生效导致真正去查 DB。
        with patch('apps.ui_automation.views.scripts.accessible_test_scripts_for_user') as accessible:
            accessible.return_value.get.side_effect = UiTestScript.DoesNotExist
            response = view.analyze_script(request)

        accessible.assert_called_once_with(self.user)
        accessible.return_value.get.assert_called_once_with(id=123)
        self.assertEqual(response.status_code, 404)

    def test_suite_add_script_uses_accessible_script_scope(self):
        request = self.factory.post('/api/ui-automation/suites/1/add_script/')
        request.user = self.user
        request.data = {'test_script_id': 123}
        view = UiTestSuiteViewSet()
        project = SimpleNamespace(id=321)
        view.get_object = lambda: SimpleNamespace(project=project)

        with patch('apps.ui_automation.views.suites.accessible_test_scripts_for_user') as accessible:
            accessible.return_value.get.side_effect = UiTestScript.DoesNotExist
            response = view.add_script(request, pk=1)

        accessible.assert_called_once_with(self.user)
        accessible.return_value.get.assert_called_once_with(id=123, project=project)
        self.assertEqual(response.status_code, 404)

    def test_suite_add_test_case_uses_accessible_case_scope(self):
        request = self.factory.post('/api/ui-automation/suites/1/add_test_case/')
        request.user = self.user
        request.data = {'test_case_id': 456}
        view = UiTestSuiteViewSet()
        project = SimpleNamespace(id=654)
        view.get_object = lambda: SimpleNamespace(project=project)

        with patch('apps.ui_automation.views.suites.accessible_test_cases_for_user') as accessible:
            accessible.return_value.get.side_effect = UiTestCase.DoesNotExist
            response = view.add_test_case(request, pk=1)

        accessible.assert_called_once_with(self.user)
        accessible.return_value.get.assert_called_once_with(id=456, project=project)
        self.assertEqual(response.status_code, 404)

    def test_ui_related_serializer_fields_are_scoped_to_accessible_projects(self):
        context = self._serializer_context()

        script_serializer = UiTestScriptCreateBoundarySerializer(context=context)
        suite_serializer = UiTestSuiteCreateBoundarySerializer(context=context)
        case_serializer = UiTestCaseBoundarySerializer(context=context)
        task_serializer = UiScheduledTaskBoundarySerializer(context=context)

        self.assertIn('owner_id', str(script_serializer.fields['project'].queryset.query))
        self.assertIn('ui_projects_members', str(suite_serializer.fields['project'].queryset.query))
        self.assertIn('owner_id', str(case_serializer.fields['project'].queryset.query))
        self.assertIn('ui_test_suites', str(task_serializer.fields['test_suite'].queryset.query))

    def test_ui_element_project_id_validator_uses_accessible_project_scope(self):
        serializer = UiElementBoundarySerializer(context=self._serializer_context())

        with patch('apps.ui_automation.serializers._accessible_ui_projects_for_user') as accessible:
            accessible.return_value.get.side_effect = UiAutomationProject.DoesNotExist
            with self.assertRaises(DRFValidationError):
                serializer.validate_project_id(999)

        accessible.assert_called_once_with(self.user)

    def test_ui_task_notification_settings_route_is_registered(self):
        route_names = {url.name for url in ui_automation_urls.router.urls}

        self.assertIn('task-notification-settings-list', route_names)

    def test_ui_task_notification_setting_serializer_redacts_webhook_secrets(self):
        notification_config = SimpleNamespace(
            pk=7,
            name='global webhook',
            get_webhook_bots=lambda: [
                {
                    'type': 'feishu',
                    'name': 'global feishu',
                    'webhook_url': 'https://open.feishu.cn/open-apis/bot/v2/hook/global-token',
                    'enabled': True,
                    'secret': 'global-signing-secret',
                }
            ],
        )
        setting = SimpleNamespace(
            id=8,
            task=SimpleNamespace(pk=9),
            notification_type='webhook',
            notification_config=notification_config,
            is_enabled=True,
            notify_on_success=True,
            notify_on_failure=True,
            notify_on_timeout=False,
            notify_on_error=True,
            custom_webhook_bots={
                'dingtalk': {
                    'name': 'custom dingtalk',
                    'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=custom-token',
                    'enabled': True,
                    'secret': 'custom-signing-secret',
                }
            },
            created_at=None,
            updated_at=None,
            get_notification_type_display=lambda: 'Webhook',
            get_active_notification_types=lambda: ['webhook'],
            get_notification_config=lambda: notification_config,
        )

        data = UiTaskNotificationSettingSerializer(setting).data
        serialized = str(data)

        self.assertNotIn('custom_webhook_bots', data)
        self.assertNotIn('global-token', serialized)
        self.assertNotIn('custom-token', serialized)
        self.assertNotIn('global-signing-secret', serialized)
        self.assertNotIn('custom-signing-secret', serialized)
        for bot in data['webhook_bots_display']:
            self.assertTrue(bot['webhook_url'].endswith('/***'))


class CoreNotificationConfigSecurityTests(SimpleTestCase):
    def test_unified_notification_config_requires_admin(self):
        self.assertEqual(UnifiedNotificationConfigViewSet.permission_classes, [IsAdminUser])

    def test_unified_notification_serializer_redacts_webhook_bots(self):
        config = UnifiedNotificationConfig(
            id=12,
            name='global dingtalk',
            config_type='webhook_dingtalk',
            webhook_bots={
                'dingtalk': {
                    'name': 'prod dingtalk',
                    'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=plain-token',
                    'enabled': True,
                    'secret': 'plain-signing-secret',
                }
            },
            created_by=get_user_model()(id=1, username='admin'),
        )

        data = UnifiedNotificationConfigSerializer(config).data
        serialized = str(data)

        self.assertNotIn('webhook_bots', data)
        self.assertNotIn('plain-token', serialized)
        self.assertNotIn('plain-signing-secret', serialized)
        self.assertEqual(data['webhook_bots_display'][0]['webhook_url'], 'https://oapi.dingtalk.com/***')
        self.assertTrue(data['webhook_bots_display'][0]['has_secret'])

    def test_unified_notification_serializer_preserves_hidden_credentials_on_update(self):
        config = UnifiedNotificationConfig(
            name='global dingtalk',
            config_type='webhook_dingtalk',
            webhook_bots={
                'dingtalk': {
                    'name': 'prod dingtalk',
                    'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=plain-token',
                    'enabled': True,
                    'secret': 'plain-signing-secret',
                }
            },
        )
        serializer = UnifiedNotificationConfigSerializer()

        merged = serializer._merge_webhook_bots(config, {
            'dingtalk': {
                'name': 'renamed',
                'webhook_url': 'https://oapi.dingtalk.com/***',
                'enabled': False,
                'secret': '***',
            }
        })

        self.assertEqual(
            merged['dingtalk']['webhook_url'],
            'https://oapi.dingtalk.com/robot/send?access_token=plain-token',
        )
        self.assertEqual(merged['dingtalk']['secret'], 'plain-signing-secret')
        self.assertEqual(merged['dingtalk']['name'], 'renamed')
        self.assertFalse(merged['dingtalk']['enabled'])

    @override_settings(DEBUG=False)
    def test_webhook_bot_url_rejects_private_targets_in_production(self):
        with self.assertRaises(ValueError):
            validate_notification_webhook_bots({
                'generic': {
                    'name': 'local webhook',
                    'webhook_url': 'http://127.0.0.1:9000/hook',
                }
            })


class AppAutomationLocalToolingSecurityTests(SimpleTestCase):
    def test_app_config_requires_admin(self):
        self.assertEqual(AppConfigViewSet.permission_classes, [IsAdminUser])

    @override_settings(APP_AUTOMATION_ALLOWED_SCRCPY_PATHS=['scrcpy'])
    def test_scrcpy_path_must_be_server_allowlisted(self):
        self.assertEqual(get_allowed_scrcpy_path('scrcpy'), 'scrcpy')
        with self.assertRaises(DRFValidationError):
            get_allowed_scrcpy_path(r'C:\Windows\System32\calc.exe')

    def test_scrcpy_capabilities_requires_admin(self):
        request = RequestFactory().get('/api/app-automation/devices/scrcpy/capabilities/')
        request.user = SimpleNamespace(is_staff=False, is_superuser=False, is_authenticated=True)

        view = AppDeviceViewSet()

        with self.assertRaises(DRFPermissionDenied):
            view.scrcpy_capabilities(request)

    def test_adb_device_actions_require_admin(self):
        user = SimpleNamespace(is_staff=False, is_superuser=False, is_authenticated=True)
        view = AppDeviceViewSet()

        discover_request = RequestFactory().get('/api/app-automation/devices/discover/')
        discover_request.user = user
        with self.assertRaises(DRFPermissionDenied):
            view.discover(discover_request)

        connect_request = RequestFactory().post('/api/app-automation/devices/connect/', data={})
        connect_request.user = user
        with self.assertRaises(DRFPermissionDenied):
            view.connect(connect_request)

        view.get_object = MagicMock()
        detail_request = RequestFactory().post('/api/app-automation/devices/1/')
        detail_request.user = user

        with self.assertRaises(DRFPermissionDenied):
            view.disconnect(detail_request, pk=1)
        with self.assertRaises(DRFPermissionDenied):
            view.screenshot(detail_request, pk=1)
        view.get_object.assert_not_called()


class ExecutionProjectIsolationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model()(id=42, username='member')

    def _attach_request(self, view, path):
        request = self.factory.get(path)
        request.user = self.user
        view.request = request
        return view

    def test_test_plan_queryset_is_scoped_to_accessible_projects_or_creator(self):
        view = self._attach_request(TestPlanViewSet(), '/api/executions/test-plans/')
        accessible_projects = Project.objects.filter(id=123)

        with patch('apps.executions.views.accessible_projects_for_user', return_value=accessible_projects):
            sql = str(view.get_queryset().query)

        self.assertIn('test_plans_projects', sql)
        self.assertIn('creator_id', sql)

    def test_run_case_and_history_querysets_are_scoped_to_accessible_projects(self):
        accessible_projects = Project.objects.filter(id=123)

        with patch('apps.executions.views.accessible_projects_for_user', return_value=accessible_projects):
            run_sql = str(self._attach_request(TestRunViewSet(), '/api/executions/test-runs/').get_queryset().query)
            case_sql = str(
                self._attach_request(TestRunCaseViewSet(), '/api/executions/test-run-cases/').get_queryset().query
            )
            history_sql = str(
                self._attach_request(
                    TestRunCaseHistoryViewSet(),
                    '/api/executions/test-run-case-history/',
                ).get_queryset().query
            )

        self.assertIn('project_id', run_sql)
        self.assertIn('project_id', case_sql)
        self.assertIn('project_id', history_sql)


class ReportProjectIsolationTests(SimpleTestCase):
    def test_report_queryset_is_scoped_to_accessible_projects(self):
        request = RequestFactory().get('/api/reports/')
        request.user = get_user_model()(id=77, username='reporter')
        view = TestReportViewSet()
        view.request = request

        with patch(
            'apps.reports.views.accessible_projects_for_user',
            return_value=Project.objects.filter(id=321),
        ):
            sql = str(view.get_queryset().query)

        self.assertIn('project_id', sql)


class AppAutomationAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_test_case_queryset_is_limited_to_accessible_projects_or_creator(self):
        user = get_user_model()(id=42, username='tester')
        request = self.factory.get('/api/app-automation/test-cases/')
        request.user = user

        view = AppTestCaseViewSet()
        view.request = request

        with patch(
            'apps.app_automation.views.test_case_views.accessible_app_projects_for_user',
            return_value=AppProject.objects.none(),
        ):
            sql = str(view.get_queryset().query)

        self.assertIn('project_id', sql)
        self.assertIn('created_by_id', sql)

    def test_scheduled_task_queryset_is_limited_to_accessible_projects_or_creator(self):
        user = get_user_model()(id=84, username='scheduler')
        request = self.factory.get('/api/app-automation/scheduled-tasks/')
        request.user = user

        view = AppScheduledTaskViewSet()
        view.request = request

        with patch(
            'apps.app_automation.views.scheduled_task_views.accessible_app_projects_for_user',
            return_value=AppProject.objects.none(),
        ):
            sql = str(view.get_queryset().query)

        self.assertIn('project_id', sql)
        self.assertIn('created_by_id', sql)


class RequirementGenerationTaskAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_generation_task_queryset_is_limited_to_creator_or_accessible_project(self):
        user = get_user_model()(id=101, username='owner')
        request = self.factory.get('/api/requirement-analysis/generation-tasks/')
        request.user = user

        view = TestCaseGenerationTaskViewSet()
        view.request = request

        with patch(
            'apps.requirement_analysis.views.accessible_projects_for_user',
            return_value=Project.objects.none(),
        ):
            sql = str(view.get_queryset().query)

        self.assertIn('created_by_id', sql)
        self.assertIn('project_id', sql)

    def test_stream_progress_action_declares_authentication(self):
        action_permissions = TestCaseGenerationTaskViewSet.stream_progress_sse.kwargs.get('permission_classes')
        self.assertEqual(action_permissions, [IsAuthenticated])

    def test_stream_progress_rejects_anonymous_user(self):
        request = self.factory.get('/api/requirement-analysis/generation-tasks/TASK_1/stream_progress/')
        request.user = AnonymousUser()
        request.META['HTTP_ORIGIN'] = 'http://localhost:3000'

        response = TestCaseGenerationTaskViewSet().stream_progress_sse(request, task_id='TASK_1')

        self.assertEqual(response.status_code, 401)

    def test_stream_progress_uses_filtered_queryset_lookup(self):
        request = self.factory.get('/api/requirement-analysis/generation-tasks/TASK_2/stream_progress/')
        request.user = SimpleNamespace(is_authenticated=True, username='member')
        request.META['HTTP_ORIGIN'] = 'http://localhost:3000'

        view = TestCaseGenerationTaskViewSet()
        filtered_queryset = MagicMock()
        filtered_queryset.filter.return_value.first.return_value = None

        with patch.object(TestCaseGenerationTaskViewSet, 'get_queryset', return_value=filtered_queryset):
            response = view.stream_progress_sse(request, task_id='TASK_2')

        filtered_queryset.filter.assert_called_once_with(task_id='TASK_2')
        self.assertEqual(response.status_code, 404)

    def test_config_status_view_requires_authentication(self):
        self.assertEqual(ConfigStatusViewSet.permission_classes, [IsAuthenticated])


class AppAutomationReportAccessTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _report_dir(self):
        tmp = temporary_directory()
        tmp.__enter__()
        self.addCleanup(tmp.cleanup)
        report_dir = Path(tmp.name) / 'report'
        report_dir.mkdir()
        (report_dir / 'index.html').write_text('<html>report</html>', encoding='utf-8')
        return report_dir

    def _mock_execution(self, report_dir, user=None):
        return SimpleNamespace(
            report_path=str(report_dir),
            user=user,
            test_case=None,
            test_suite=None,
        )

    def test_report_rejects_anonymous_user(self):
        report_dir = self._report_dir()
        request = self.factory.get('/api/app-automation/executions/1/report/')
        request.user = AnonymousUser()

        with patch(
            'apps.app_automation.views.execution_views.AppTestExecution.objects.get',
            return_value=self._mock_execution(report_dir),
        ):
            try:
                response = serve_report_file(request, execution_id=1)
            except PermissionDenied:
                return
            finally:
                response = locals().get('response')
                if response is not None:
                    response.close()
            self.fail('PermissionDenied not raised')

    def test_report_rejects_authenticated_user_without_execution_access(self):
        report_dir = self._report_dir()
        request = self.factory.get('/api/app-automation/executions/1/report/')
        request.user = SimpleNamespace(
            id=2,
            is_authenticated=True,
            is_staff=False,
            is_superuser=False,
        )
        owner = SimpleNamespace(id=1)

        with patch(
            'apps.app_automation.views.execution_views.AppTestExecution.objects.get',
            return_value=self._mock_execution(report_dir, user=owner),
        ):
            try:
                response = serve_report_file(request, execution_id=1)
            except PermissionDenied:
                return
            finally:
                response = locals().get('response')
                if response is not None:
                    response.close()
            self.fail('PermissionDenied not raised')

    def test_report_rejects_paths_outside_report_directory_with_shared_prefix(self):
        with temporary_directory() as tmp:
            root = Path(tmp)
            report_dir = root / 'report'
            report_dir.mkdir()
            sibling = root / 'report_evil'
            sibling.mkdir()
            (sibling / 'secret.txt').write_text('secret', encoding='utf-8')

            user = SimpleNamespace(
                id=1,
                is_authenticated=True,
                is_staff=False,
                is_superuser=False,
            )
            request = self.factory.get('/api/app-automation/executions/1/report/../report_evil/secret.txt')
            request.user = user

            with patch(
                'apps.app_automation.views.execution_views.AppTestExecution.objects.get',
                return_value=self._mock_execution(report_dir, user=user),
            ):
                try:
                    response = serve_report_file(
                        request,
                        execution_id=1,
                        file_path=os.path.join('..', 'report_evil', 'secret.txt'),
                    )
                except Http404:
                    return
                finally:
                    response = locals().get('response')
                    if response is not None:
                        response.close()
                self.fail('Http404 not raised')


class AppAutomationWebSocketAccessTests(SimpleTestCase):
    def test_anonymous_execution_subscriber_is_closed_before_group_join(self):
        consumer = AppExecutionConsumer()
        consumer.scope = {
            'url_route': {'kwargs': {'execution_id': 1}},
            'user': AnonymousUser(),
        }
        consumer.channel_layer = SimpleNamespace(group_add=AsyncMock(), group_discard=AsyncMock())
        consumer.channel_name = 'test-channel'
        consumer.accept = AsyncMock()
        consumer.close = AsyncMock()

        async_to_sync(consumer.connect)()

        consumer.channel_layer.group_add.assert_not_called()
        consumer.accept.assert_not_called()
        consumer.close.assert_called_once()
