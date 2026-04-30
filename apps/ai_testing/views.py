from django.db import models
from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.audit import record_unified_audit
from apps.core.models import UnifiedAuditLog
from apps.projects.unified import accessible_projects_for_user, user_can_manage_project

from .models import AiTestingRun, AiTestingTask
from .serializers import AiTestingRunSerializer, AiTestingTaskSerializer
from .services import cancel_ai_testing_run, create_ai_testing_run, run_pending_ai_testing_runs, start_ai_testing_run


def _can_manage_task(user, task):
    return task.created_by_id == getattr(user, 'id', None) or user_can_manage_project(user, task.project)


class AiTestingTaskViewSet(viewsets.ModelViewSet):
    serializer_class = AiTestingTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'status', 'execution_mode']
    search_fields = ['name', 'description', 'instruction', 'target_url']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-updated_at']

    def get_queryset(self):
        projects = accessible_projects_for_user(self.request.user)
        return AiTestingTask.objects.filter(project__in=projects).select_related(
            'project',
            'created_by',
        ).annotate(
            run_count=Count('runs', distinct=True),
        )

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user)
        record_unified_audit(
            domain='ai_testing',
            action=UnifiedAuditLog.ACTION_CREATE,
            object_type='ai_testing_task',
            object_id=task.id,
            object_name=task.name,
            project_id=task.project_id,
            project_name=task.project.name,
            actor=self.request.user,
            summary='Created AI testing task.',
            metadata={
                'operation': 'create_task',
                'execution_mode': task.execution_mode,
                'target_url': task.target_url,
            },
        )

    def perform_update(self, serializer):
        if not _can_manage_task(self.request.user, self.get_object()):
            raise PermissionDenied('No permission to manage this AI testing task.')
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_manage_task(self.request.user, instance):
            raise PermissionDenied('No permission to manage this AI testing task.')
        instance.delete()

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        task = self.get_object()
        if not _can_manage_task(request.user, task):
            raise PermissionDenied('No permission to run this AI testing task.')
        run = create_ai_testing_run(
            task,
            request.user,
            start_immediately=str(request.data.get('start_immediately', '')).lower() in {'1', 'true', 'yes'},
        )
        record_unified_audit(
            domain='ai_testing',
            action=UnifiedAuditLog.ACTION_RUN,
            object_type='ai_testing_run',
            object_id=run.id,
            object_name=task.name,
            project_id=task.project_id,
            project_name=task.project.name,
            actor=request.user,
            summary='Created AI testing run.',
            metadata={
                'operation': 'create_run',
                'task_id': task.id,
                'run_id': run.id,
                'status': run.status,
                'start_immediately': str(request.data.get('start_immediately', '')).lower() in {'1', 'true', 'yes'},
            },
        )
        return Response(AiTestingRunSerializer(run, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AiTestingRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AiTestingRunSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'task', 'status', 'execution_mode']
    search_fields = ['instruction_snapshot', 'logs', 'error_message']
    ordering_fields = ['created_at', 'started_at', 'finished_at']
    ordering = ['-created_at']

    def get_queryset(self):
        projects = accessible_projects_for_user(self.request.user)
        return AiTestingRun.objects.filter(project__in=projects).select_related(
            'project',
            'task',
            'created_by',
        )

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        run = self.get_object()
        if not (
            run.created_by_id == request.user.id
            or user_can_manage_project(request.user, run.project)
        ):
            raise PermissionDenied('No permission to start this AI testing run.')
        run = start_ai_testing_run(run)
        record_unified_audit(
            domain='ai_testing',
            action=UnifiedAuditLog.ACTION_RUN,
            object_type='ai_testing_run',
            object_id=run.id,
            object_name=run.task.name,
            project_id=run.project_id,
            project_name=run.project.name,
            actor=request.user,
            summary='Started AI testing run.',
            metadata={
                'operation': 'start_run',
                'task_id': run.task_id,
                'run_id': run.id,
                'status': run.status,
            },
        )
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        run = self.get_object()
        if not (
            run.created_by_id == request.user.id
            or user_can_manage_project(request.user, run.project)
        ):
            raise PermissionDenied('No permission to cancel this AI testing run.')
        run = cancel_ai_testing_run(run)
        record_unified_audit(
            domain='ai_testing',
            action=UnifiedAuditLog.ACTION_UPDATE,
            object_type='ai_testing_run',
            object_id=run.id,
            object_name=run.task.name,
            project_id=run.project_id,
            project_name=run.project.name,
            actor=request.user,
            summary='Cancelled AI testing run.',
            metadata={
                'operation': 'cancel_run',
                'task_id': run.task_id,
                'run_id': run.id,
                'status': run.status,
            },
        )
        return Response(self.get_serializer(run).data)

    @action(detail=False, methods=['post'])
    def run_pending(self, request):
        limit = request.data.get('limit') or request.query_params.get('limit')
        try:
            limit = int(limit) if limit else None
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid limit.'}, status=status.HTTP_400_BAD_REQUEST)
        result = run_pending_ai_testing_runs(
            limit=limit,
            queryset=self.get_queryset(),
            manage_connections=False,
        )
        record_unified_audit(
            domain='ai_testing',
            action=UnifiedAuditLog.ACTION_RUN,
            object_type='ai_testing_queue',
            actor=request.user,
            summary='Ran pending AI testing queue.',
            metadata={
                'operation': 'run_pending',
                'limit': limit,
                **result,
            },
        )
        return Response(result)


class AiTestingSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_ai_testing_summary_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        projects = accessible_projects_for_user(request.user)
        tasks = AiTestingTask.objects.filter(project__in=projects)
        runs = AiTestingRun.objects.filter(project__in=projects)
        return Response({
            'projects': projects.count(),
            'tasks': tasks.count(),
            'active_tasks': tasks.filter(status=AiTestingTask.STATUS_ACTIVE).count(),
            'runs': runs.count(),
            'pending_runs': runs.filter(status=AiTestingRun.STATUS_PENDING).count(),
            'running_runs': runs.filter(status=AiTestingRun.STATUS_RUNNING).count(),
            'succeeded_runs': runs.filter(status=AiTestingRun.STATUS_SUCCEEDED).count(),
            'failed_runs': runs.filter(status=AiTestingRun.STATUS_FAILED).count(),
            'by_mode': {
                item['execution_mode']: item['count']
                for item in tasks.values('execution_mode').annotate(count=Count('id'))
            },
        })
