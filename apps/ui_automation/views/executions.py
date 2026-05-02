"""TestExecution, Screenshot, OperationRecord ViewSets."""

import logging

from django.db import models
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import UiProject, TestExecution, Screenshot, OperationRecord
from ..serializers import (
    TestExecutionSerializer,
    TestExecutionCreateSerializer,
    ScreenshotSerializer,
    OperationRecordSerializer,
)
from ..operation_logger import log_operation
from ._common import StandardPagination

logger = logging.getLogger(__name__)


class TestExecutionViewSet(viewsets.ModelViewSet):
    queryset = TestExecution.objects.all()
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'test_suite', 'test_script', 'status', 'environment', 'executed_by']
    search_fields = ['error_message']
    ordering = ['-created_at']
    pagination_class = StandardPagination

    def get_queryset(self):
        # 只显示用户有权限访问的项目的测试执行记录
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return TestExecution.objects.filter(
            project__in=accessible_projects
        ).select_related('project', 'test_suite', 'test_script', 'executed_by')

    def get_serializer_class(self):
        if self.action == 'create':
            return TestExecutionCreateSerializer
        return TestExecutionSerializer

    def perform_destroy(self, instance):
        # 记录操作（删除测试报告）
        suite_name = instance.test_suite.name if instance.test_suite else f"执行记录#{instance.id}"
        log_operation('delete', 'report', instance.id, suite_name, self.request.user)
        instance.delete()

    @action(detail=True, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request, pk=None):
        """导出简版 PDF 执行报告。"""
        execution = self.get_object()
        title = f"UI Test Execution #{execution.id}"
        body = (
            f"Status: {execution.status}\\n"
            f"Total: {getattr(execution, 'total_cases', 0)}\\n"
            f"Passed: {getattr(execution, 'passed_cases', 0)}\\n"
            f"Failed: {getattr(execution, 'failed_cases', 0)}\\n"
        )
        text = (title + "\\n" + body).replace('(', '\\(').replace(')', '\\)')
        stream = f"BT /F1 12 Tf 72 740 Td ({text}) Tj ET"
        pdf = (
            b"%PDF-1.4\\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\\n"
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\\n"
            + f"5 0 obj << /Length {len(stream.encode('utf-8'))} >> stream\\n".encode('utf-8')
            + stream.encode('utf-8')
            + b"\\nendstream endobj\\ntrailer << /Root 1 0 R >>\\n%%EOF\\n"
        )
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=\"ui-test-execution-{execution.id}.pdf\"'
        return response


class ScreenshotViewSet(viewsets.ModelViewSet):
    queryset = Screenshot.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ScreenshotSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['execution']

    def get_queryset(self):
        # 只显示用户有权限访问的项目的截图
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        executions = TestExecution.objects.filter(project__in=accessible_projects)
        return Screenshot.objects.filter(execution__in=executions)


class OperationRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """操作记录视图集（只读）"""
    queryset = OperationRecord.objects.all()
    serializer_class = OperationRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['operation_type', 'resource_type', 'user']

    def get_queryset(self):
        # 返回最近的操作记录，按创建时间倒序
        # 过滤掉AI智能模式相关的操作记录
        queryset = OperationRecord.objects.exclude(
            resource_type__in=['ai_case', 'ai_execution']
        ).order_by('-created_at')

        # 支持通过查询参数限制返回数量
        limit = self.request.query_params.get('limit', None)
        if limit:
            try:
                limit = int(limit)
                queryset = queryset[:limit]
            except ValueError:
                pass

        return queryset
