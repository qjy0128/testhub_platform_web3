from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from .models import Version
from .serializers import VersionSerializer, VersionCreateSerializer
from apps.projects.models import Project


def _accessible_projects_for_user(user):
    return Project.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()

# 版本管理视图
class VersionListCreateView(generics.ListCreateAPIView):
    """版本列表和创建视图"""
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_baseline']  # 移除projects，手动处理
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return VersionCreateSerializer
        return VersionSerializer
    
    def get_queryset(self):
        # 只显示用户有权限访问的项目的版本
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return Version.objects.none()
        accessible_projects = Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        
        queryset = Version.objects.filter(projects__in=accessible_projects).distinct()
        
        # 手动处理项目筛选
        project_id = self.request.query_params.get('projects')
        if project_id and project_id.strip():  # 检查是否为空或空字符串
            try:
                project_id = int(project_id)
                queryset = queryset.filter(projects__id=project_id)
            except (ValueError, TypeError):
                # 如果无法转换为整数，忽略此筛选条件
                pass
        
        return queryset
    
    def perform_create(self, serializer):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return Version.objects.none()
        project_ids = serializer.validated_data.get('project_ids')
        
        # 检查项目权限
        accessible_projects = Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        
        # 验证用户对所有指定项目都有权限
        accessible_project_ids = set(accessible_projects.values_list('id', flat=True))
        requested_project_ids = set(project_ids)
        
        if not requested_project_ids.issubset(accessible_project_ids):
            from rest_framework.exceptions import ValidationError
            raise ValidationError("没有权限访问部分项目")
        
        serializer.save(created_by=user)

class VersionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """版本详情视图"""
    serializer_class = VersionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        accessible_projects = Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return Version.objects.filter(projects__in=accessible_projects).distinct()

@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_project_versions(request, project_id):
    """获取指定项目的版本列表"""
    user = request.user
    
    # 检查项目权限
    accessible_projects = Project.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()
    
    if not accessible_projects.filter(id=project_id).exists():
        return Response({'error': '没有权限访问该项目'}, status=status.HTTP_403_FORBIDDEN)
    
    versions = Version.objects.filter(projects__id=project_id).order_by('-created_at')
    serializer = VersionSerializer(versions, many=True)
    return Response(serializer.data)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def version_traceability(request, pk):
    accessible_projects = _accessible_projects_for_user(request.user)
    version = Version.objects.filter(pk=pk, projects__in=accessible_projects).distinct().first()
    if version is None:
        return Response({'detail': 'Version not found.'}, status=status.HTTP_404_NOT_FOUND)

    from apps.executions.models import TestPlan, TestRun
    from apps.reports.models import TestReport
    from apps.testcases.models import TestCase
    from apps.testsuites.models import TestSuite

    project_ids = list(version.projects.filter(id__in=accessible_projects.values('id')).values_list('id', flat=True))
    testcase_qs = TestCase.objects.filter(project_id__in=project_ids, versions=version).distinct()
    suite_qs = TestSuite.objects.filter(project_id__in=project_ids, testcases__versions=version).distinct()
    plan_qs = TestPlan.objects.filter(projects__id__in=project_ids, version=version).distinct()
    run_qs = TestRun.objects.filter(project_id__in=project_ids, version=version).distinct()
    report_qs = TestReport.objects.filter(project_id__in=project_ids, execution__version=version).distinct()

    def count_by(queryset, field):
        return {
            item[field] or 'blank': item['count']
            for item in queryset.values(field).annotate(count=models.Count('id')).order_by(field)
        }

    recent_runs = [
        {
            'id': run.id,
            'name': run.name,
            'status': run.status,
            'progress_stats': run.progress_stats,
            'started_at': run.started_at,
            'completed_at': run.completed_at,
        }
        for run in run_qs.order_by('-created_at')[:8]
    ]
    suites = [
        {
            'id': suite.id,
            'name': suite.name,
            'project_name': suite.project.name,
            'testcase_count': suite.testcases.filter(versions=version).distinct().count(),
        }
        for suite in suite_qs.select_related('project').order_by('-created_at')[:8]
    ]
    reports = [
        {
            'id': report.id,
            'title': report.name,
            'project_name': report.project.name,
            'execution_name': report.execution.name if report.execution_id else '',
            'created_at': report.created_at,
        }
        for report in report_qs.select_related('project', 'execution').order_by('-created_at')[:8]
    ]

    return Response({
        'version': VersionSerializer(version).data,
        'counts': {
            'testcases': testcase_qs.count(),
            'suites': suite_qs.count(),
            'plans': plan_qs.count(),
            'runs': run_qs.count(),
            'reports': report_qs.count(),
        },
        'breakdowns': {
            'status': count_by(testcase_qs, 'status'),
            'priority': count_by(testcase_qs, 'priority'),
            'test_type': count_by(testcase_qs, 'test_type'),
            'run_status': count_by(run_qs, 'status'),
        },
        'recent_runs': recent_runs,
        'suites': suites,
        'reports': reports,
    })
