import logging
from csv import writer as csv_writer
from datetime import datetime, time, timedelta
from io import StringIO

from django.db.models import Avg, Count, Max, Min, Q
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.unified import accessible_projects_for_user, user_has_project_action_permission
from .audit import record_unified_audit
from .models import (
    RequestPerformanceMetric,
    UnifiedAuditLog,
    UnifiedNotificationConfig,
    UnifiedNotificationSendLog,
    UnifiedNotificationTemplate,
    UnifiedSchedulerAlert,
    UnifiedScheduledJobDependency,
    UnifiedScheduledJobRun,
)
from .scheduler_alerts import notify_scheduler_alerts, sync_scheduler_alerts
from .notifications import render_notification_template, send_unified_notification
from .scheduled_jobs import (
    get_accessible_unified_project,
    get_scheduled_job,
    get_scheduled_job_context,
    list_scheduled_jobs,
    normalize_scheduled_job,
    summarize_scheduled_jobs,
    user_can_manage_task,
    validate_module_name,
)
from .scheduler_engine import dependency_blocks, run_scheduled_job
from .serializers import (
    RequestPerformanceMetricSerializer,
    UnifiedAuditLogSerializer,
    UnifiedNotificationConfigSerializer,
    UnifiedNotificationSendLogSerializer,
    UnifiedNotificationTemplateSerializer,
    UnifiedSchedulerAlertSerializer,
    UnifiedScheduledJobDependencySerializer,
    UnifiedScheduledJobRunSerializer,
    UnifiedScheduledJobSerializer,
)

logger = logging.getLogger(__name__)


def _audit_project_fields(source_project=None, binding=None):
    if binding is not None:
        return binding.project_id, binding.project.name
    if source_project is not None:
        return source_project.id, source_project.name
    return None, ''


def _record_scheduled_job_audit(action, request, module, task, source_project=None, binding=None, summary='', metadata=None):
    project_id, project_name = _audit_project_fields(source_project=source_project, binding=binding)
    return record_unified_audit(
        domain='scheduler',
        action=action,
        object_type='scheduled_job',
        object_id=task.id,
        object_name=getattr(task, 'name', ''),
        module=module,
        source_id=task.id,
        project_id=project_id,
        project_name=project_name,
        actor=request.user,
        summary=summary,
        metadata={
            'job_key': f'{module}:{task.id}',
            **(metadata or {}),
        },
    )


def _can_manage_scheduled_action(user, action_key, module, task, source_project=None, binding=None):
    if user_can_manage_task(
        user,
        module,
        task,
        source_project=source_project,
        binding=binding,
    ):
        return True
    if binding is None:
        return False
    return user_has_project_action_permission(
        user,
        binding.project,
        module,
        action_key,
        default_roles=['owner', 'admin'],
    )


def _pause_scheduled_task(task):
    task.status = 'PAUSED'
    if hasattr(task, 'next_run_time'):
        task.next_run_time = None
        task.save(update_fields=['status', 'next_run_time'])
        return
    task.save(update_fields=['status'])


def _resume_scheduled_task(task):
    task.status = 'ACTIVE'
    if hasattr(task, 'calculate_next_run'):
        task.next_run_time = task.calculate_next_run()
        task.save(update_fields=['status', 'next_run_time'])
        return
    task.save(update_fields=['status'])


class UnifiedNotificationConfigViewSet(viewsets.ModelViewSet):
    queryset = UnifiedNotificationConfig.objects.all()
    serializer_class = UnifiedNotificationConfigSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['config_type', 'is_default', 'is_active']
    search_fields = ['name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        logger.info('Created unified notification config: %s', instance.name)

    def perform_update(self, serializer):
        instance = serializer.save()
        logger.info('Updated unified notification config: %s', instance.name)

    def perform_destroy(self, instance):
        logger.info('Deleted unified notification config: %s', instance.name)
        instance.delete()

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        config = self.get_object()
        UnifiedNotificationConfig.objects.filter(is_default=True).update(is_default=False)
        config.is_default = True
        config.save(update_fields=['is_default', 'updated_at'])
        return Response({'message': 'Default notification config updated.'})

    @action(detail=False, methods=['get'])
    def active_configs(self, request):
        configs = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_test(self, request, pk=None):
        config = self.get_object()
        template_id = request.data.get('template_id')
        if template_id:
            template = UnifiedNotificationTemplate.objects.filter(
                id=template_id,
                is_active=True,
            ).first()
            if template is None:
                return Response({'detail': 'Notification template not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            template = UnifiedNotificationTemplate.objects.create(
                name='Test notification',
                event_type=UnifiedNotificationTemplate.EVENT_MANUAL,
                channel=request.data.get('channel') or UnifiedNotificationTemplate.CHANNEL_ALL,
                subject_template='TestHub notification test',
                body_template='Hello {{ username }}, this is a TestHub notification test.',
                content_type=UnifiedNotificationTemplate.CONTENT_TEXT,
                created_by=request.user,
            )
        logs = send_unified_notification(
            config=config,
            template=template,
            variables=request.data.get('variables') or {'username': request.user.username},
            channel=request.data.get('channel'),
            recipients=request.data.get('recipients'),
            attachments=request.data.get('attachments') or [],
            created_by=request.user,
        )
        serializer = UnifiedNotificationSendLogSerializer(logs, many=True)
        status_code = status.HTTP_200_OK if all(log.status == 'success' for log in logs) else status.HTTP_207_MULTI_STATUS
        return Response({'logs': serializer.data}, status=status_code)


class UnifiedNotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = UnifiedNotificationTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event_type', 'channel', 'content_type', 'is_default', 'is_active']
    search_fields = ['name', 'subject_template', 'body_template']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['event_type', '-is_default', '-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not getattr(self.request.user, 'is_authenticated', False):
            return UnifiedNotificationTemplate.objects.none()
        queryset = UnifiedNotificationTemplate.objects.select_related('created_by')
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(Q(created_by=self.request.user) | Q(created_by__isnull=True))

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def render(self, request, pk=None):
        template = self.get_object()
        rendered = render_notification_template(template, request.data.get('variables') or {})
        return Response({
            'subject': rendered.subject,
            'body': rendered.body,
            'content_type': rendered.content_type,
        })


class UnifiedNotificationSendLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UnifiedNotificationSendLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['channel', 'status', 'config', 'template']
    search_fields = ['target', 'subject', 'content', 'error_message']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not getattr(self.request.user, 'is_authenticated', False):
            return UnifiedNotificationSendLog.objects.none()
        queryset = UnifiedNotificationSendLog.objects.select_related('config', 'template', 'created_by')
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(Q(created_by=self.request.user) | Q(config__created_by=self.request.user))


class UnifiedScheduledJobRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UnifiedScheduledJobRunSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['module', 'source_id', 'status', 'trigger_source']
    search_fields = ['job_name', 'error_message']
    ordering_fields = ['created_at', 'started_at', 'finished_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UnifiedScheduledJobRun.objects.select_related('triggered_by', 'retry_of')

    def _filter_accessible(self, queryset):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return list(queryset)
        return [
            run for run in queryset
            if run.triggered_by_id == user.id
            or get_scheduled_job(user, run.module, run.source_id) is not None
        ]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        runs = self._filter_accessible(queryset)
        page = self.paginate_queryset(runs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(runs, many=True)
        return Response(serializer.data)

    def get_object(self):
        instance = super().get_object()
        if not self._filter_accessible([instance]):
            raise Http404
        return instance


class UnifiedAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UnifiedAuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['domain', 'action', 'object_type', 'module', 'source_id', 'project_id']
    search_fields = ['object_name', 'summary', 'project_name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UnifiedAuditLog.objects.select_related('actor')

    def _filter_accessible(self, queryset):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return list(queryset)
        project_ids = set(accessible_projects_for_user(user).values_list('id', flat=True))
        return [log for log in queryset if self._can_read_log(user, log, project_ids)]

    def _can_read_log(self, user, log, project_ids=None):
        project_ids = project_ids or set()
        if log.actor_id == user.id:
            return True
        if log.project_id and log.project_id in project_ids:
            return True
        if log.module and log.source_id and get_scheduled_job(user, log.module, log.source_id) is not None:
            return True
        metadata = log.metadata or {}
        for key in ('upstream_key', 'downstream_key', 'job_key'):
            job_key = metadata.get(key)
            if not job_key or ':' not in str(job_key):
                continue
            module, source_id = str(job_key).split(':', 1)
            if source_id.isdigit() and get_scheduled_job(user, module, int(source_id)) is not None:
                return True
        return False

    def list(self, request, *args, **kwargs):
        queryset = self._get_filtered_queryset()
        logs = self._filter_accessible(queryset)
        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)

    def get_object(self):
        instance = super().get_object()
        if not self._filter_accessible([instance]):
            raise Http404
        return instance

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self._get_filtered_queryset()
        logs = self._filter_accessible(queryset)
        domain_counts = {}
        action_counts = {}
        module_counts = {}
        actor_counts = {}

        for log in logs:
            domain_counts[log.domain] = domain_counts.get(log.domain, 0) + 1
            action_counts[log.action] = action_counts.get(log.action, 0) + 1
            module_key = log.module or '-'
            module_counts[module_key] = module_counts.get(module_key, 0) + 1
            actor_key = log.actor.username if log.actor_id else '-'
            actor_counts[actor_key] = actor_counts.get(actor_key, 0) + 1

        return Response({
            'total': len(logs),
            'domains': domain_counts,
            'actions': action_counts,
            'modules': module_counts,
            'actors': actor_counts,
        })

    @action(detail=False, methods=['get'])
    def export(self, request):
        queryset = self._get_filtered_queryset()
        logs = self._filter_accessible(queryset)

        output = StringIO()
        csv = csv_writer(output)
        csv.writerow([
            'id',
            'created_at',
            'domain',
            'action',
            'object_type',
            'object_id',
            'object_name',
            'module',
            'source_id',
            'project_id',
            'project_name',
            'actor',
            'summary',
        ])
        for log in logs:
            csv.writerow([
                log.id,
                log.created_at.isoformat() if log.created_at else '',
                log.domain,
                log.action,
                log.object_type,
                log.object_id,
                log.object_name,
                log.module,
                log.source_id or '',
                log.project_id or '',
                log.project_name,
                log.actor.username if log.actor_id else '',
                log.summary,
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="unified_audit_logs.csv"'
        return response

    def _get_filtered_queryset(self):
        queryset = self.filter_queryset(self.get_queryset())
        return self._apply_extra_filters(queryset)

    def _apply_extra_filters(self, queryset):
        created_after = self.request.query_params.get('created_at_after')
        created_before = self.request.query_params.get('created_at_before')
        if created_after:
            parsed_after = parse_datetime(created_after)
            if parsed_after is None:
                date_after = parse_date(created_after)
                if date_after:
                    parsed_after = timezone.make_aware(datetime.combine(date_after, time.min))
            if parsed_after:
                queryset = queryset.filter(created_at__gte=parsed_after)
        if created_before:
            parsed_before = parse_datetime(created_before)
            if parsed_before is None:
                date_before = parse_date(created_before)
                if date_before:
                    parsed_before = timezone.make_aware(datetime.combine(date_before, time.max))
            if parsed_before:
                queryset = queryset.filter(created_at__lte=parsed_before)
        return queryset


class RequestPerformanceMetricViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RequestPerformanceMetricSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['method', 'status_code', 'is_slow', 'is_error', 'path', 'route_name']
    search_fields = ['path', 'route_name', 'user_agent']
    ordering_fields = ['created_at', 'response_time_ms', 'status_code']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not getattr(self.request.user, 'is_authenticated', False):
            return RequestPerformanceMetric.objects.none()
        queryset = RequestPerformanceMetric.objects.select_related('user')
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(user=user)

        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            start_value = parse_datetime(start)
            if start_value is None:
                start_date = parse_date(start)
                if start_date:
                    start_value = timezone.make_aware(datetime.combine(start_date, time.min))
            if start_value:
                queryset = queryset.filter(created_at__gte=start_value)
        if end:
            end_value = parse_datetime(end)
            if end_value is None:
                end_date = parse_date(end)
                if end_date:
                    end_value = timezone.make_aware(datetime.combine(end_date, time.max))
            if end_value:
                queryset = queryset.filter(created_at__lte=end_value)
        return queryset

    def _summary_payload(self, queryset):
        aggregate = queryset.aggregate(
            total=Count('id'),
            avg_response_time=Avg('response_time_ms'),
            max_response_time=Max('response_time_ms'),
            min_response_time=Min('response_time_ms'),
            slow_count=Count('id', filter=Q(is_slow=True)),
            error_count=Count('id', filter=Q(is_error=True)),
        )
        total = aggregate['total'] or 0
        slow_count = aggregate['slow_count'] or 0
        error_count = aggregate['error_count'] or 0
        status_groups = {}
        for row in queryset.values('status_code').annotate(count=Count('id')).order_by('status_code'):
            group = f"{int((row['status_code'] or 0) / 100)}xx"
            status_groups[group] = status_groups.get(group, 0) + row['count']
        top_paths = list(queryset.values('path').annotate(
            count=Count('id'),
            avg_response_time=Avg('response_time_ms'),
            max_response_time=Max('response_time_ms'),
            error_count=Count('id', filter=Q(is_error=True)),
        ).order_by('-count')[:10])
        return {
            **aggregate,
            'slow_rate': (slow_count / total) if total else 0,
            'error_rate': (error_count / total) if total else 0,
            'status_groups': status_groups,
            'top_paths': top_paths,
        }

    @action(detail=False, methods=['get'])
    def summary(self, request):
        return Response(self._summary_payload(self.filter_queryset(self.get_queryset())))

    @action(detail=False, methods=['get'])
    def trends(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        rows = queryset.annotate(day=TruncDate('created_at')).values('day').annotate(
            count=Count('id'),
            avg_response_time=Avg('response_time_ms'),
            max_response_time=Max('response_time_ms'),
            slow_count=Count('id', filter=Q(is_slow=True)),
            error_count=Count('id', filter=Q(is_error=True)),
        ).order_by('day')
        return Response([
            {
                **row,
                'day': row['day'].isoformat() if row['day'] else None,
            }
            for row in rows
        ])

    @action(detail=False, methods=['get'], url_path='slow-requests')
    def slow_requests(self, request):
        queryset = self.filter_queryset(self.get_queryset().filter(is_slow=True)).order_by('-response_time_ms', '-created_at')[:50]
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=False, methods=['get'], url_path='error-requests')
    def error_requests(self, request):
        queryset = self.filter_queryset(self.get_queryset().filter(is_error=True)).order_by('-created_at')[:50]
        return Response(self.get_serializer(queryset, many=True).data)


class UnifiedSchedulerAlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UnifiedSchedulerAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'severity', 'alert_type', 'module', 'project_id']
    search_fields = ['job_key', 'job_name', 'message', 'project_name']
    ordering_fields = ['last_seen_at', 'first_seen_at', 'occurrences']
    ordering = ['-last_seen_at']

    def get_queryset(self):
        return UnifiedSchedulerAlert.objects.select_related('acknowledged_by')

    def _can_read_alert(self, user, alert, project_ids=None):
        if user.is_staff or user.is_superuser:
            return True
        project_ids = project_ids or set()
        if alert.project_id and alert.project_id in project_ids:
            return True
        if alert.module and alert.source_id and get_scheduled_job(user, alert.module, alert.source_id) is not None:
            return True
        return False

    def _filter_accessible(self, queryset):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return list(queryset)
        project_ids = set(accessible_projects_for_user(user).values_list('id', flat=True))
        return [alert for alert in queryset if self._can_read_alert(user, alert, project_ids)]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        alerts = self._filter_accessible(queryset)
        page = self.paginate_queryset(alerts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)

    def get_object(self):
        instance = super().get_object()
        if not self._filter_accessible([instance]):
            raise Http404
        return instance

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if alert.status == UnifiedSchedulerAlert.STATUS_RESOLVED:
            return Response({'detail': 'Resolved alert cannot be acknowledged.'}, status=status.HTTP_400_BAD_REQUEST)
        alert.status = UnifiedSchedulerAlert.STATUS_ACKNOWLEDGED
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at'])
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.status = UnifiedSchedulerAlert.STATUS_RESOLVED
        alert.resolved_at = timezone.now()
        alert.acknowledged_by = None
        alert.acknowledged_at = None
        alert.save(update_fields=['status', 'resolved_at', 'acknowledged_by', 'acknowledged_at'])
        return Response(self.get_serializer(alert).data)

    @action(detail=False, methods=['post'])
    def notify(self, request):
        status_filter = request.data.get('status') or request.query_params.get('status') or UnifiedSchedulerAlert.STATUS_OPEN
        queryset = self.filter_queryset(self.get_queryset()).filter(status=status_filter)
        alerts = self._filter_accessible(queryset)
        result = notify_scheduler_alerts(alerts, actor=request.user)
        return Response({
            'status': status_filter,
            'count': len(alerts),
            **result,
        })


class UnifiedScheduledJobDependencyViewSet(viewsets.ModelViewSet):
    serializer_class = UnifiedScheduledJobDependencySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = [
        'upstream_module',
        'upstream_source_id',
        'downstream_module',
        'downstream_source_id',
        'is_active',
    ]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['downstream_module', 'downstream_source_id']

    def get_queryset(self):
        return UnifiedScheduledJobDependency.objects.select_related('created_by')

    def _filter_accessible(self, queryset):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return list(queryset)
        return [
            dependency for dependency in queryset
            if get_scheduled_job(user, dependency.upstream_module, dependency.upstream_source_id)
            and get_scheduled_job(user, dependency.downstream_module, dependency.downstream_source_id)
        ]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(self._filter_accessible(queryset), many=True)
        return Response(serializer.data)

    def get_object(self):
        instance = super().get_object()
        if not self._filter_accessible([instance]):
            raise Http404
        return instance

    def perform_create(self, serializer):
        data = serializer.validated_data
        upstream_module = data['upstream_module']
        downstream_module = data['downstream_module']
        upstream_source_id = data['upstream_source_id']
        downstream_source_id = data['downstream_source_id']

        validate_module_name(upstream_module)
        validate_module_name(downstream_module)
        if upstream_module == downstream_module and upstream_source_id == downstream_source_id:
            raise PermissionDenied('A scheduled job cannot depend on itself.')

        upstream_context = get_scheduled_job_context(self.request.user, upstream_module, upstream_source_id)
        downstream_context = get_scheduled_job_context(self.request.user, downstream_module, downstream_source_id)
        if upstream_context is None or downstream_context is None:
            raise PermissionDenied('No permission to access one of these scheduled jobs.')
        if not _can_manage_scheduled_action(
            self.request.user,
            'scheduler.manage_dependency',
            downstream_module,
            downstream_context['task'],
            source_project=downstream_context['source_project'],
            binding=downstream_context['binding'],
        ):
            raise PermissionDenied('No permission to manage the downstream scheduled job.')

        instance = serializer.save(created_by=self.request.user)
        self._record_dependency_audit(
            UnifiedAuditLog.ACTION_CREATE,
            instance,
            'Created scheduled job dependency.',
            downstream_context=downstream_context,
        )

    def perform_update(self, serializer):
        self._assert_can_manage_dependency(serializer.instance)
        instance = serializer.save()
        downstream_context = self._assert_can_manage_dependency(instance)
        self._record_dependency_audit(
            UnifiedAuditLog.ACTION_UPDATE,
            instance,
            'Updated scheduled job dependency.',
            downstream_context=downstream_context,
        )

    def perform_destroy(self, instance):
        downstream_context = self._assert_can_manage_dependency(instance)
        self._record_dependency_audit(
            UnifiedAuditLog.ACTION_DELETE,
            instance,
            'Deleted scheduled job dependency.',
            downstream_context=downstream_context,
        )
        instance.delete()

    def _assert_can_manage_dependency(self, dependency):
        downstream_context = get_scheduled_job_context(
            self.request.user,
            dependency.downstream_module,
            dependency.downstream_source_id,
        )
        if downstream_context is None:
            raise PermissionDenied('No permission to access the downstream scheduled job.')
        if not _can_manage_scheduled_action(
            self.request.user,
            'scheduler.manage_dependency',
            dependency.downstream_module,
            downstream_context['task'],
            source_project=downstream_context['source_project'],
            binding=downstream_context['binding'],
        ):
            raise PermissionDenied('No permission to manage the downstream scheduled job.')
        return downstream_context

    def _record_dependency_audit(self, action_name, dependency, summary, downstream_context=None):
        downstream_context = downstream_context or {}
        source_project = downstream_context.get('source_project')
        binding = downstream_context.get('binding')
        project_id, project_name = _audit_project_fields(source_project=source_project, binding=binding)
        record_unified_audit(
            domain='scheduler',
            action=action_name,
            object_type='scheduled_job_dependency',
            object_id=dependency.id,
            object_name=f'{dependency.upstream_key} -> {dependency.downstream_key}',
            module=dependency.downstream_module,
            source_id=dependency.downstream_source_id,
            project_id=project_id,
            project_name=project_name,
            actor=self.request.user,
            summary=summary,
            metadata={
                'upstream_key': dependency.upstream_key,
                'downstream_key': dependency.downstream_key,
                'is_active': dependency.is_active,
            },
        )


class UnifiedScheduledJobSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_core_scheduled_jobs_summary_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        jobs = list_scheduled_jobs(request.user)
        run_queryset = UnifiedScheduledJobRun.objects.all()
        if not (request.user.is_staff or request.user.is_superuser):
            run_queryset = [
                run for run in run_queryset
                if run.triggered_by_id == request.user.id
                or get_scheduled_job(request.user, run.module, run.source_id) is not None
            ]
        run_counts = {
            item['status']: item['count']
            for item in run_queryset.values('status').annotate(count=Count('id'))
        } if hasattr(run_queryset, 'values') else {}
        if not hasattr(run_queryset, 'values'):
            for run in run_queryset:
                run_counts[run.status] = run_counts.get(run.status, 0) + 1
        payload = summarize_scheduled_jobs(jobs)
        payload['blocked'] = sum(1 for job in jobs if dependency_blocks(job['module'], job['source_id']))
        payload['runs'] = {
            'pending': run_counts.get(UnifiedScheduledJobRun.STATUS_PENDING, 0),
            'running': run_counts.get(UnifiedScheduledJobRun.STATUS_RUNNING, 0),
            'succeeded': run_counts.get(UnifiedScheduledJobRun.STATUS_SUCCEEDED, 0),
            'failed': run_counts.get(UnifiedScheduledJobRun.STATUS_FAILED, 0),
            'skipped': run_counts.get(UnifiedScheduledJobRun.STATUS_SKIPPED, 0),
        }
        return Response(payload)


class UnifiedScheduledJobListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_core_scheduled_jobs_list_retrieve',
        responses=UnifiedScheduledJobSerializer(many=True),
    )
    def get(self, request):
        project_id = request.query_params.get('project')
        module = request.query_params.get('module')
        status_filter = request.query_params.get('status')
        trigger_type = request.query_params.get('trigger_type')

        unified_project = None
        if project_id:
            unified_project = get_accessible_unified_project(request.user, project_id)
            if unified_project is None:
                raise Http404

        try:
            jobs = list_scheduled_jobs(
                request.user,
                unified_project=unified_project,
                module=module,
                status=status_filter,
                trigger_type=trigger_type,
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UnifiedScheduledJobSerializer(jobs, many=True)
        return Response(serializer.data)


class UnifiedScheduledJobGraphView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_core_scheduled_jobs_graph_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        project_id = request.query_params.get('project')
        module = request.query_params.get('module')
        status_filter = request.query_params.get('status')
        trigger_type = request.query_params.get('trigger_type')

        unified_project = None
        if project_id:
            unified_project = get_accessible_unified_project(request.user, project_id)
            if unified_project is None:
                raise Http404

        try:
            jobs = list_scheduled_jobs(
                request.user,
                unified_project=unified_project,
                module=module,
                status=status_filter,
                trigger_type=trigger_type,
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        job_map = {job['job_key']: job for job in jobs}
        dependencies = UnifiedScheduledJobDependency.objects.filter(is_active=True)
        if not (request.user.is_staff or request.user.is_superuser):
            dependencies = [
                dependency for dependency in dependencies
                if get_scheduled_job(request.user, dependency.upstream_module, dependency.upstream_source_id)
                and get_scheduled_job(request.user, dependency.downstream_module, dependency.downstream_source_id)
            ]

        edges = []
        for dependency in dependencies:
            if dependency.upstream_key not in job_map or dependency.downstream_key not in job_map:
                continue
            edges.append({
                'id': dependency.id,
                'upstream_key': dependency.upstream_key,
                'downstream_key': dependency.downstream_key,
            })

        blocked_keys = {
            job['job_key']
            for job in jobs
            if dependency_blocks(job['module'], job['source_id'])
        }
        nodes = [
            {
                'id': job['job_key'],
                'name': job['name'],
                'module': job['module'],
                'module_display': job['module_display'],
                'status': job['status'],
                'last_run_status': job['last_unified_run_status'],
                'is_running': job['is_running'],
                'blocked': job['job_key'] in blocked_keys,
            }
            for job in jobs
        ]
        return Response({'nodes': nodes, 'edges': edges})


class UnifiedScheduledJobHealthView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_core_scheduled_jobs_health_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        project_id = request.query_params.get('project')
        module = request.query_params.get('module')
        status_filter = request.query_params.get('status')
        trigger_type = request.query_params.get('trigger_type')
        sla_minutes = self._int_param(request, 'sla_minutes', default=30, minimum=1, maximum=1440)
        stale_minutes = self._int_param(request, 'stale_minutes', default=30, minimum=1, maximum=1440)
        lookback_hours = self._int_param(request, 'lookback_hours', default=24, minimum=1, maximum=168)

        unified_project = None
        if project_id:
            unified_project = get_accessible_unified_project(request.user, project_id)
            if unified_project is None:
                raise Http404

        try:
            jobs = list_scheduled_jobs(
                request.user,
                unified_project=unified_project,
                module=module,
                status=status_filter,
                trigger_type=trigger_type,
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        job_map = {job['job_key']: job for job in jobs}
        due_soon_at = now + timedelta(minutes=sla_minutes)
        stale_before = now - timedelta(minutes=stale_minutes)
        lookback_at = now - timedelta(hours=lookback_hours)

        due_now = []
        due_soon = []
        overdue = []
        blocked = []
        running = []

        for job in jobs:
            next_run_time = job.get('next_run_time')
            normalized_status = str(job.get('status') or '').lower()
            is_active = normalized_status == 'active'
            if job.get('is_running'):
                running.append(job)
            if is_active and next_run_time:
                if next_run_time <= now:
                    due_now.append(job)
                    overdue.append(job)
                elif next_run_time <= due_soon_at:
                    due_soon.append(job)

            blockers = dependency_blocks(job['module'], job['source_id'])
            if blockers:
                blocked.append((job, blockers))

        running_runs = self._filter_runs_for_jobs(
            UnifiedScheduledJobRun.objects.filter(
                status=UnifiedScheduledJobRun.STATUS_RUNNING,
                finished_at__isnull=True,
            ),
            job_map,
        )
        stale_running = [
            run for run in running_runs
            if (run.locked_until and run.locked_until < now)
            or (run.started_at and run.started_at < stale_before)
        ]
        recent_failed = self._filter_runs_for_jobs(
            UnifiedScheduledJobRun.objects.filter(
                status=UnifiedScheduledJobRun.STATUS_FAILED,
                created_at__gte=lookback_at,
            ).order_by('-created_at')[:100],
            job_map,
        )

        alerts = []
        for run in stale_running[:20]:
            job = job_map.get(run.job_key, {})
            alerts.append({
                'type': 'stale_running',
                'severity': 'critical',
                'job_key': run.job_key,
                'job_name': run.job_name or job.get('name', ''),
                'module': run.module,
                'module_display': job.get('module_display', run.module),
                'run_id': run.id,
                'started_at': run.started_at,
                'locked_until': run.locked_until,
                'message': 'Running job lock is stale.',
            })
        for job in overdue[:20]:
            alerts.append({
                'type': 'overdue',
                'severity': 'warning',
                'job_key': job['job_key'],
                'job_name': job['name'],
                'module': job['module'],
                'module_display': job['module_display'],
                'next_run_time': job.get('next_run_time'),
                'message': 'Scheduled job is overdue.',
            })
        for job, blockers in blocked[:20]:
            alerts.append({
                'type': 'blocked',
                'severity': 'warning',
                'job_key': job['job_key'],
                'job_name': job['name'],
                'module': job['module'],
                'module_display': job['module_display'],
                'blocked_by': blockers,
                'message': 'Scheduled job is blocked by dependencies.',
            })
        for run in recent_failed[:20]:
            job = job_map.get(run.job_key, {})
            alerts.append({
                'type': 'recent_failure',
                'severity': 'danger',
                'job_key': run.job_key,
                'job_name': run.job_name or job.get('name', ''),
                'module': run.module,
                'module_display': job.get('module_display', run.module),
                'run_id': run.id,
                'finished_at': run.finished_at,
                'message': run.error_message or 'Scheduled job failed recently.',
            })

        for alert in alerts:
            job = job_map.get(alert.get('job_key') or '', {})
            alert['source_id'] = alert.get('source_id') or job.get('source_id')
            alert['project_id'] = job.get('unified_project_id') or job.get('source_project_id')
            alert['project_name'] = job.get('unified_project_name') or job.get('source_project_name') or ''

        persistence = sync_scheduler_alerts(
            alerts,
            resolve_absent=not any([project_id, module, status_filter, trigger_type]),
        )

        payload = {
            'status': 'unhealthy' if alerts else 'healthy',
            'checked_at': now,
            'thresholds': {
                'sla_minutes': sla_minutes,
                'stale_minutes': stale_minutes,
                'lookback_hours': lookback_hours,
            },
            'counts': {
                'total': len(jobs),
                'active': sum(1 for job in jobs if str(job.get('status') or '').lower() == 'active'),
                'paused': sum(1 for job in jobs if str(job.get('status') or '').lower() == 'paused'),
                'due_now': len(due_now),
                'due_soon': len(due_soon),
                'overdue': len(overdue),
                'blocked': len(blocked),
                'running': len(running),
                'stale_running': len(stale_running),
                'recent_failed': len(recent_failed),
            },
            'due_soon': self._job_rows(due_soon[:20]),
            'overdue': self._job_rows(overdue[:20]),
            'stale_running': UnifiedScheduledJobRunSerializer(stale_running[:20], many=True).data,
            'recent_failed': UnifiedScheduledJobRunSerializer(recent_failed[:20], many=True).data,
            'alerts': alerts[:50],
            'persistence': persistence,
        }
        return Response(payload)

    def _int_param(self, request, name, *, default, minimum, maximum):
        try:
            value = int(request.query_params.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    def _filter_runs_for_jobs(self, queryset, job_map):
        return [run for run in queryset if run.job_key in job_map]

    def _job_rows(self, jobs):
        return [
            {
                'job_key': job['job_key'],
                'name': job['name'],
                'module': job['module'],
                'module_display': job['module_display'],
                'status': job['status'],
                'next_run_time': job.get('next_run_time'),
                'unified_project_id': job.get('unified_project_id'),
                'unified_project_name': job.get('unified_project_name'),
            }
            for job in jobs
        ]


class UnifiedScheduledJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_core_scheduled_jobs_detail_retrieve',
        responses=UnifiedScheduledJobSerializer,
    )
    def get(self, request, module, source_id):
        try:
            job = get_scheduled_job(request.user, module, source_id)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if job is None:
            raise Http404

        serializer = UnifiedScheduledJobSerializer(job)
        return Response(serializer.data)


class UnifiedScheduledJobActionView(APIView):
    permission_classes = [IsAuthenticated]
    action_name = None

    @extend_schema(
        request=inline_serializer(
            name='UnifiedScheduledJobActionRequest',
            fields={
                'force': serializers.BooleanField(required=False),
                'max_attempts': serializers.IntegerField(required=False, min_value=1),
            },
        ),
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request, module, source_id):
        try:
            context = get_scheduled_job_context(request.user, module, source_id)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if context is None:
            raise Http404

        task = context['task']
        source_project = context['source_project']
        binding = context['binding']

        action_key_map = {
            'pause': 'scheduler.pause',
            'resume': 'scheduler.resume',
            'run-now': 'scheduler.run_now',
        }
        if not _can_manage_scheduled_action(
            request.user,
            action_key_map.get(self.action_name, 'scheduler.manage'),
            module,
            task,
            source_project=source_project,
            binding=binding,
        ):
            raise PermissionDenied('No permission to manage this scheduled job.')

        if self.action_name == 'pause':
            _pause_scheduled_task(task)
            task.refresh_from_db()
            _record_scheduled_job_audit(
                UnifiedAuditLog.ACTION_PAUSE,
                request,
                module,
                task,
                source_project=source_project,
                binding=binding,
                summary='Paused scheduled job.',
                metadata={'status': task.status},
            )
            return Response({
                'message': 'Scheduled job paused.',
                'job': normalize_scheduled_job(module, task, source_project=source_project, binding=binding),
            })

        if self.action_name == 'resume':
            _resume_scheduled_task(task)
            task.refresh_from_db()
            _record_scheduled_job_audit(
                UnifiedAuditLog.ACTION_RESUME,
                request,
                module,
                task,
                source_project=source_project,
                binding=binding,
                summary='Resumed scheduled job.',
                metadata={'status': task.status},
            )
            return Response({
                'message': 'Scheduled job resumed.',
                'job': normalize_scheduled_job(module, task, source_project=source_project, binding=binding),
            })

        if self.action_name != 'run-now':
            return Response({'detail': 'Unsupported action.'}, status=status.HTTP_400_BAD_REQUEST)

        force = str(request.data.get('force', '')).lower() in {'1', 'true', 'yes'}
        result = run_scheduled_job(
            module,
            task,
            triggered_by=request.user,
            trigger_source=UnifiedScheduledJobRun.TRIGGER_MANUAL,
            max_attempts=request.data.get('max_attempts', 1),
            force_dependencies=force,
        )

        if result.blocked_by:
            _record_scheduled_job_audit(
                UnifiedAuditLog.ACTION_RUN,
                request,
                module,
                task,
                source_project=source_project,
                binding=binding,
                summary='Scheduled job run was blocked by dependencies.',
                metadata={
                    'outcome': 'blocked',
                    'run_id': getattr(result.run, 'id', None),
                    'blocked_by': result.blocked_by,
                },
            )
            return Response(
                {
                    'detail': 'Scheduled job dependencies are not satisfied.',
                    'blocked_by': result.blocked_by,
                    'run': UnifiedScheduledJobRunSerializer(result.run).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if result.locked_by:
            _record_scheduled_job_audit(
                UnifiedAuditLog.ACTION_RUN,
                request,
                module,
                task,
                source_project=source_project,
                binding=binding,
                summary='Scheduled job run was skipped because another run is active.',
                metadata={
                    'outcome': 'locked',
                    'run_id': getattr(result.run, 'id', None),
                    'locked_by': result.locked_by,
                },
            )
            return Response(
                {
                    'detail': 'Scheduled job is already running.',
                    'locked_by': result.locked_by,
                    'run': UnifiedScheduledJobRunSerializer(result.run).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if result.failed:
            _record_scheduled_job_audit(
                UnifiedAuditLog.ACTION_RUN,
                request,
                module,
                task,
                source_project=source_project,
                binding=binding,
                summary='Scheduled job run failed.',
                metadata={
                    'outcome': 'failed',
                    'run_id': getattr(result.run, 'id', None),
                    'attempts': result.attempts,
                },
            )
            return Response(
                {
                    'detail': result.payload.get('detail', 'Scheduled job failed.'),
                    'attempts': result.attempts,
                    'run': UnifiedScheduledJobRunSerializer(result.run).data if result.run else None,
                },
                status=result.status_code,
            )

        task.refresh_from_db()
        _record_scheduled_job_audit(
            UnifiedAuditLog.ACTION_RUN,
            request,
            module,
            task,
            source_project=source_project,
            binding=binding,
            summary='Scheduled job run dispatched.',
            metadata={
                'outcome': 'succeeded',
                'run_id': getattr(result.run, 'id', None),
                'attempts': result.attempts,
            },
        )
        payload = dict(result.payload)
        payload['attempts'] = result.attempts
        payload['run'] = UnifiedScheduledJobRunSerializer(result.run).data
        payload['job'] = normalize_scheduled_job(
            module,
            task,
            source_project=source_project,
            binding=binding,
        )
        return Response(payload)


class UnifiedScheduledJobPauseView(UnifiedScheduledJobActionView):
    action_name = 'pause'


class UnifiedScheduledJobResumeView(UnifiedScheduledJobActionView):
    action_name = 'resume'


class UnifiedScheduledJobRunNowView(UnifiedScheduledJobActionView):
    action_name = 'run-now'
