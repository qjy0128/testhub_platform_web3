# -*- coding: utf-8 -*-
"""APP测试用例管理视图"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
import logging

from ..models import AppPackage, AppTestCase, AppDevice, AppTestExecution
from ..permissions import (
    accessible_app_projects_for_user,
    user_can_access_app_package,
    user_can_access_app_project,
)
from ..serializers import AppPackageSerializer, AppTestCaseSerializer, AppTestExecutionSerializer

logger = logging.getLogger(__name__)


class AppPagination(PageNumberPagination):
    """APP自动化模块通用分页"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AppPackageViewSet(viewsets.ModelViewSet):
    """APP应用包名管理 ViewSet"""
    queryset = AppPackage.objects.all()
    serializer_class = AppPackageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    search_fields = ['name', 'package_name']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return queryset
        return queryset.filter(created_by=user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AppTestCaseViewSet(viewsets.ModelViewSet):
    """APP测试用例 ViewSet"""
    queryset = AppTestCase.objects.all()
    serializer_class = AppTestCaseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['project', 'app_package']
    search_fields = ['name']

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

    def _validate_write_access(self, serializer):
        project = serializer.validated_data.get('project', getattr(serializer.instance, 'project', None))
        app_package = serializer.validated_data.get('app_package', getattr(serializer.instance, 'app_package', None))
        if project and not user_can_access_app_project(self.request.user, project):
            raise PermissionDenied('无权访问该 APP 项目')
        if app_package and not user_can_access_app_package(self.request.user, app_package):
            raise PermissionDenied('无权访问该应用包名')

    def perform_create(self, serializer):
        self._validate_write_access(serializer)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        self._validate_write_access(serializer)
        serializer.save()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """执行测试用例"""
        test_case = self.get_object()
        device_id = request.data.get('device_id')
        package_name = request.data.get('package_name')
        
        if not device_id:
            return Response({
                'success': False,
                'message': '请选择执行设备'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 检查设备是否可用
            device = AppDevice.objects.get(device_id=device_id)
            if device.status == 'locked' and device.locked_by != request.user:
                return Response({
                    'success': False,
                    'message': '设备已被其他用户锁定'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 创建执行记录
            execution = AppTestExecution.objects.create(
                test_case=test_case,
                device=device,
                user=request.user,
                status='pending'
            )
            
            # 调用 Celery 任务异步执行
            from ..tasks import execute_app_test_task
            task = execute_app_test_task.delay(execution.id, package_name=package_name)
            execution.task_id = task.id
            execution.save()
            
            logger.info(f"测试已提交执行: execution_id={execution.id}, task_id={task.id}")
            
            return Response({
                'success': True,
                'message': '测试已提交执行',
                'execution': AppTestExecutionSerializer(execution).data
            })
            
        except AppDevice.DoesNotExist:
            return Response({
                'success': False,
                'message': '设备不存在'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"执行测试失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'执行测试失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
