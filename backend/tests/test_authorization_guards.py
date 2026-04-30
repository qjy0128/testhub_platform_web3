from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied

from apps.app_automation.views.scheduled_task_views import AppScheduledTaskViewSet
from apps.app_automation.views.suite_views import AppTestSuiteViewSet
from apps.app_automation.views.test_case_views import AppTestCaseViewSet


class AppTestCaseWriteGuardTests(SimpleTestCase):
    def test_rejects_inaccessible_project_on_write(self):
        view = AppTestCaseViewSet()
        view.request = SimpleNamespace(user=SimpleNamespace(id=1, is_authenticated=True))
        serializer = SimpleNamespace(
            validated_data={'project': SimpleNamespace(id=100), 'app_package': None},
            instance=None,
        )

        with patch('apps.app_automation.views.test_case_views.user_can_access_app_project', return_value=False):
            with self.assertRaises(PermissionDenied):
                view._validate_write_access(serializer)

    def test_rejects_inaccessible_package_on_write(self):
        view = AppTestCaseViewSet()
        view.request = SimpleNamespace(user=SimpleNamespace(id=1, is_authenticated=True))
        serializer = SimpleNamespace(
            validated_data={
                'project': SimpleNamespace(id=100),
                'app_package': SimpleNamespace(id=200),
            },
            instance=None,
        )

        with patch('apps.app_automation.views.test_case_views.user_can_access_app_project', return_value=True), patch(
            'apps.app_automation.views.test_case_views.user_can_access_app_package',
            return_value=False,
        ):
            with self.assertRaises(PermissionDenied):
                view._validate_write_access(serializer)


class AppTestSuiteWriteGuardTests(SimpleTestCase):
    def test_rejects_binding_test_case_from_other_project(self):
        view = AppTestSuiteViewSet()
        suite_project = SimpleNamespace(id=10)
        foreign_case = SimpleNamespace(project_id=99)

        with self.assertRaises(PermissionDenied):
            view._validate_suite_case_binding(suite_project, foreign_case)


class AppScheduledTaskWriteGuardTests(SimpleTestCase):
    def test_rejects_related_resource_outside_task_project(self):
        view = AppScheduledTaskViewSet()
        with self.assertRaises(PermissionDenied):
            view._validate_project_relation(SimpleNamespace(id=1), related_project_id=2)

    def test_rejects_inaccessible_project_on_write(self):
        view = AppScheduledTaskViewSet()
        view.request = SimpleNamespace(user=SimpleNamespace(id=1, is_authenticated=True))
        serializer = SimpleNamespace(
            instance=None,
            validated_data={
                'project': SimpleNamespace(id=10),
                'app_package': None,
                'test_suite': None,
                'test_case': None,
            },
        )

        with patch('apps.app_automation.views.scheduled_task_views.user_can_access_app_project', return_value=False):
            with self.assertRaises(PermissionDenied):
                view._validate_write_access(serializer)

    def test_rejects_inaccessible_package_on_write(self):
        view = AppScheduledTaskViewSet()
        view.request = SimpleNamespace(user=SimpleNamespace(id=1, is_authenticated=True))
        serializer = SimpleNamespace(
            instance=None,
            validated_data={
                'project': SimpleNamespace(id=10),
                'app_package': SimpleNamespace(id=20),
                'test_suite': None,
                'test_case': None,
            },
        )

        with patch('apps.app_automation.views.scheduled_task_views.user_can_access_app_project', return_value=True), patch(
            'apps.app_automation.views.scheduled_task_views.user_can_access_app_package',
            return_value=False,
        ):
            with self.assertRaises(PermissionDenied):
                view._validate_write_access(serializer)
