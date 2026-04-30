# -*- coding: utf-8 -*-
"""APP自动化定时任务视图"""
import logging

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q

from .test_case_views import AppPagination
from ..models import (
    AppScheduledTask, AppNotificationLog,
    AppDevice,
)
from ..permissions import (
    accessible_app_projects_for_user,
    user_can_access_app_case,
    user_can_access_app_package,
    user_can_access_app_project,
    user_can_access_app_suite,
)
from ..serializers import (
    AppScheduledTaskSerializer,
    AppNotificationLogSerializer,
)

logger = logging.getLogger(__name__)


class AppScheduledTaskViewSet(viewsets.ModelViewSet):
    """APP定时任务视图集"""
    queryset = AppScheduledTask.objects.all()
    serializer_class = AppScheduledTaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['task_type', 'status', 'trigger_type', 'project']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'next_run_time', 'last_run_time']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return queryset
        accessible_projects = accessible_app_projects_for_user(user)
        return queryset.filter(
            Q(project__in=accessible_projects) |
            Q(project__isnull=True, created_by=user)
        ).distinct()

    def _validate_project_relation(self, task_project, related_project_id):
        if task_project and related_project_id != task_project.id:
            raise PermissionDenied('关联资源不属于该 APP 项目')

    def _validate_write_access(self, serializer):
        instance = serializer.instance
        data = serializer.validated_data
        project = data.get('project', getattr(instance, 'project', None))
        app_package = data.get('app_package', getattr(instance, 'app_package', None))
        test_suite = data.get('test_suite', getattr(instance, 'test_suite', None))
        test_case = data.get('test_case', getattr(instance, 'test_case', None))

        if project and not user_can_access_app_project(self.request.user, project):
            raise PermissionDenied('无权访问该 APP 项目')
        if app_package and not user_can_access_app_package(self.request.user, app_package):
            raise PermissionDenied('无权访问该应用包名')
        if test_suite and not user_can_access_app_suite(self.request.user, test_suite):
            raise PermissionDenied('无权访问该测试套件')
        if test_case and not user_can_access_app_case(self.request.user, test_case):
            raise PermissionDenied('无权访问该测试用例')

        if test_suite:
            self._validate_project_relation(project, test_suite.project_id)
        if test_case:
            self._validate_project_relation(project, test_case.project_id)

    def perform_create(self, serializer):
        self._validate_write_access(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validate_write_access(serializer)
        serializer.save()

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        task = self.get_object()
        task.status = 'PAUSED'
        task.save(update_fields=['status'])
        return Response({'success': True, 'message': '任务已暂停'})

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        task = self.get_object()
        task.status = 'ACTIVE'
        task.next_run_time = task.calculate_next_run()
        task.save(update_fields=['status', 'next_run_time'])
        return Response({'success': True, 'message': '任务已恢复'})

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """立即运行任务"""
        task = self.get_object()

        try:
            if not task.device:
                return Response({'success': False, 'message': '该任务未配置执行设备'},
                                status=status.HTTP_400_BAD_REQUEST)

            device = task.device
            if device.status == 'locked' and device.locked_by != request.user:
                return Response({'success': False, 'message': '设备已被其他用户锁定'},
                                status=status.HTTP_400_BAD_REQUEST)

            # 更新统计
            task.last_run_time = timezone.now()
            task.total_runs += 1
            task.next_run_time = task.calculate_next_run()
            task.save()

            package_name = task.app_package.package_name if task.app_package else ''

            if task.task_type == 'TEST_SUITE':
                if not task.test_suite:
                    return Response({'success': False, 'message': '该任务未配置测试套件'},
                                    status=status.HTTP_400_BAD_REQUEST)

                suite_cases = task.test_suite.suite_cases.select_related('test_case').all()
                if not suite_cases.exists():
                    return Response({'success': False, 'message': '测试套件没有用例'},
                                    status=status.HTTP_400_BAD_REQUEST)

                # 创建执行记录并调用 Celery
                from ..models import AppTestExecution
                from ..tasks import execute_app_suite_task

                executions = []
                for sc in suite_cases:
                    execution = AppTestExecution.objects.create(
                        test_case=sc.test_case,
                        test_suite=task.test_suite,
                        device=device,
                        user=request.user,
                        status='pending'
                    )
                    executions.append(execution)

                task.test_suite.execution_status = 'running'
                task.test_suite.save(update_fields=['execution_status'])

                celery_task = execute_app_suite_task.delay(
                    suite_id=task.test_suite.id,
                    execution_ids=[e.id for e in executions],
                    package_name=package_name,
                    scheduled_task_id=task.id,
                )

                return Response({
                    'success': True,
                    'message': f'测试套件开始执行，共 {len(executions)} 个用例',
                    'data': {'task_id': celery_task.id, 'test_case_count': len(executions)}
                })

            elif task.task_type == 'TEST_CASE':
                if not task.test_case:
                    return Response({'success': False, 'message': '该任务未配置测试用例'},
                                    status=status.HTTP_400_BAD_REQUEST)

                from ..models import AppTestExecution
                from ..tasks import execute_app_test_task

                execution = AppTestExecution.objects.create(
                    test_case=task.test_case,
                    device=device,
                    user=request.user,
                    status='pending'
                )
                celery_task = execute_app_test_task.delay(
                    execution.id,
                    package_name=package_name,
                    scheduled_task_id=task.id,
                )
                execution.task_id = celery_task.id
                execution.save(update_fields=['task_id'])

                return Response({
                    'success': True,
                    'message': '测试用例开始执行',
                    'data': {'task_id': celery_task.id}
                })

            return Response({'success': False, 'message': '不支持的任务类型'},
                            status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f'执行定时任务失败: {str(e)}', exc_info=True)
            return Response({'success': False, 'message': f'执行失败: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AppNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """APP通知日志视图集（只读）"""
    queryset = AppNotificationLog.objects.all()
    serializer_class = AppNotificationLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'notification_type']
    search_fields = ['task_name', 'notification_content']
    ordering_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return queryset
        accessible_projects = accessible_app_projects_for_user(user)
        return queryset.filter(
            Q(task__project__in=accessible_projects) |
            Q(task__project__isnull=True, task__created_by=user)
        ).distinct()

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        log = self.get_object()
        if log.status == 'failed':
            log.retry_count += 1
            log.is_retried = True
            log.save(update_fields=['retry_count', 'is_retried'])
            return Response({'success': True, 'message': '通知已加入重试队列'})
        return Response({'success': False, 'message': '只能重试失败的通知'},
                        status=status.HTTP_400_BAD_REQUEST)
