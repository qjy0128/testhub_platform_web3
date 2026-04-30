import copy
import os
import socket
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .models import UnifiedScheduledJobDependency, UnifiedScheduledJobRun
from .scheduled_jobs import get_scheduled_job_queryset, get_scheduled_module_keys, normalize_scheduled_job


DEFAULT_LOCK_SECONDS = 30 * 60
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_DEFER_SECONDS = 60
MAX_ATTEMPTS_LIMIT = 5


class SchedulerExecutionError(Exception):
    def __init__(self, payload, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(str(payload))
        self.payload = payload
        self.status_code = status_code


@dataclass
class ScheduledJobExecutionResult:
    run: UnifiedScheduledJobRun | None
    payload: dict = field(default_factory=dict)
    status_code: int = status.HTTP_200_OK
    blocked_by: list = field(default_factory=list)
    locked_by: dict | None = None
    attempts: list = field(default_factory=list)

    @property
    def succeeded(self):
        return bool(self.run and self.run.status == UnifiedScheduledJobRun.STATUS_SUCCEEDED)

    @property
    def skipped(self):
        return bool(self.run and self.run.status == UnifiedScheduledJobRun.STATUS_SKIPPED)

    @property
    def failed(self):
        return bool(self.run and self.run.status == UnifiedScheduledJobRun.STATUS_FAILED)


class SchedulerRequest:
    def __init__(self, user, data=None):
        self.user = user
        self.data = data or {}
        self.query_params = {}
        self.method = 'POST'
        self.META = {}


def clamp_max_attempts(value, default=1):
    try:
        return max(1, min(int(value), MAX_ATTEMPTS_LIMIT))
    except (TypeError, ValueError):
        return default


def build_worker_id():
    host = socket.gethostname() or 'localhost'
    return f'{host}:{os.getpid()}'


def dependency_blocks(module, source_id):
    blocks = []
    dependencies = UnifiedScheduledJobDependency.objects.filter(
        downstream_module=module,
        downstream_source_id=source_id,
        is_active=True,
    )
    for dependency in dependencies:
        last_run = UnifiedScheduledJobRun.objects.filter(
            module=dependency.upstream_module,
            source_id=dependency.upstream_source_id,
        ).order_by('-created_at').first()
        if last_run is None or last_run.status != UnifiedScheduledJobRun.STATUS_SUCCEEDED:
            blocks.append({
                'dependency_id': dependency.id,
                'upstream_key': dependency.upstream_key,
                'last_status': getattr(last_run, 'status', 'never_run'),
            })
    return blocks


def dependency_would_create_cycle(
    upstream_module,
    upstream_source_id,
    downstream_module,
    downstream_source_id,
    *,
    exclude_dependency_id=None,
):
    target = (str(upstream_module), int(upstream_source_id))
    stack = [(str(downstream_module), int(downstream_source_id))]
    visited = set()

    while stack:
        module, source_id = stack.pop()
        key = (module, source_id)
        if key == target:
            return True
        if key in visited:
            continue
        visited.add(key)

        queryset = UnifiedScheduledJobDependency.objects.filter(
            upstream_module=module,
            upstream_source_id=source_id,
            is_active=True,
        )
        if exclude_dependency_id:
            queryset = queryset.exclude(pk=exclude_dependency_id)

        for dependency in queryset:
            stack.append((dependency.downstream_module, dependency.downstream_source_id))

    return False


def get_active_running_run(module, source_id, now=None, lock_seconds=DEFAULT_LOCK_SECONDS):
    now = now or timezone.now()
    recent_cutoff = now - timedelta(seconds=lock_seconds)
    return UnifiedScheduledJobRun.objects.filter(
        module=module,
        source_id=source_id,
        status=UnifiedScheduledJobRun.STATUS_RUNNING,
        finished_at__isnull=True,
    ).filter(
        Q(locked_until__gt=now) |
        Q(locked_until__isnull=True, started_at__gte=recent_cutoff)
    ).order_by('-created_at').first()


def create_job_run(
    module,
    task,
    *,
    attempt=1,
    max_attempts=1,
    trigger_source=UnifiedScheduledJobRun.TRIGGER_MANUAL,
    triggered_by=None,
    scheduled_for=None,
    worker_id='',
    lock_seconds=DEFAULT_LOCK_SECONDS,
    retry_of=None,
    result=None,
    status_value=UnifiedScheduledJobRun.STATUS_RUNNING,
    error_message='',
):
    now = timezone.now()
    finished_at = now if status_value != UnifiedScheduledJobRun.STATUS_RUNNING else None
    locked_until = None
    if status_value == UnifiedScheduledJobRun.STATUS_RUNNING:
        locked_until = now + timedelta(seconds=lock_seconds)
    return UnifiedScheduledJobRun.objects.create(
        module=module,
        source_id=task.id,
        job_name=getattr(task, 'name', ''),
        status=status_value,
        attempt=attempt,
        max_attempts=max_attempts,
        trigger_source=trigger_source,
        scheduled_for=scheduled_for,
        locked_until=locked_until,
        worker_id=worker_id,
        retry_of=retry_of,
        result=copy.deepcopy(result) if result else {},
        error_message=error_message,
        triggered_by=triggered_by,
        started_at=now,
        finished_at=finished_at,
    )


def finish_job_run(job_run, status_value, result=None, error_message=''):
    job_run.status = status_value
    job_run.result = copy.deepcopy(result) if result else {}
    job_run.error_message = error_message or ''
    job_run.locked_until = None
    job_run.finished_at = timezone.now()
    job_run.save(update_fields=[
        'status',
        'result',
        'error_message',
        'locked_until',
        'finished_at',
        'updated_at',
    ])
    return job_run


def defer_task_check(task, seconds=DEFAULT_DEFER_SECONDS):
    if not hasattr(task, 'next_run_time'):
        return None
    task.next_run_time = timezone.now() + timedelta(seconds=seconds)
    task.save(update_fields=['next_run_time'])
    return task.next_run_time


def _response_payload(response):
    data = getattr(response, 'data', None)
    if isinstance(data, dict):
        return dict(data)
    return {'data': data}


def run_module_task(module, task, user):
    request = SchedulerRequest(user, data={'scheduled': True})
    if module == 'api_testing':
        from apps.api_testing.models import TaskExecutionLog
        from apps.api_testing.views import ScheduledTaskViewSet

        execution_log = TaskExecutionLog.objects.create(
            task=task,
            status='PENDING',
            executed_by=user,
        )
        ScheduledTaskViewSet()._execute_task_async(task, execution_log)
        return {
            'message': 'Task execution started.',
            'execution_id': execution_log.id,
        }

    if module == 'ui_automation':
        from apps.ui_automation.views import UiScheduledTaskViewSet

        viewset = UiScheduledTaskViewSet()
        viewset.request = request
        viewset.kwargs = {'pk': task.pk}
        viewset.get_object = lambda: task
        response = viewset.run_now(request, pk=task.pk)
        payload = _response_payload(response)
        if response.status_code >= 400:
            raise SchedulerExecutionError(payload, status_code=response.status_code)
        return payload

    if module == 'app_automation':
        from apps.app_automation.views import AppScheduledTaskViewSet

        viewset = AppScheduledTaskViewSet()
        viewset.request = request
        viewset.kwargs = {'pk': task.pk}
        viewset.get_object = lambda: task
        response = viewset.run_now(request, pk=task.pk)
        payload = _response_payload(response)
        if response.status_code >= 400:
            raise SchedulerExecutionError(payload, status_code=response.status_code)
        return payload

    raise SchedulerExecutionError({'detail': 'Unsupported module.'}, status_code=status.HTTP_400_BAD_REQUEST)


def run_scheduled_job(
    module,
    task,
    *,
    triggered_by=None,
    trigger_source=UnifiedScheduledJobRun.TRIGGER_MANUAL,
    max_attempts=1,
    force_dependencies=False,
    lock_seconds=DEFAULT_LOCK_SECONDS,
    defer_blocked_seconds=DEFAULT_DEFER_SECONDS,
    worker_id='',
):
    max_attempts = clamp_max_attempts(max_attempts, default=1)
    worker_id = worker_id or build_worker_id()
    triggered_by = triggered_by or getattr(task, 'created_by', None)
    scheduled_for = getattr(task, 'next_run_time', None)
    now = timezone.now()

    active_run = get_active_running_run(module, task.id, now=now, lock_seconds=lock_seconds)
    if active_run is not None:
        run = create_job_run(
            module,
            task,
            max_attempts=max_attempts,
            trigger_source=trigger_source,
            triggered_by=triggered_by,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            result={'locked_by_run_id': active_run.id},
            status_value=UnifiedScheduledJobRun.STATUS_SKIPPED,
            error_message='A previous run is still active.',
        )
        if trigger_source == UnifiedScheduledJobRun.TRIGGER_SCHEDULER:
            next_check_at = defer_task_check(task, seconds=defer_blocked_seconds)
            run.result = {**run.result, 'next_check_at': next_check_at.isoformat() if next_check_at else None}
            run.save(update_fields=['result', 'updated_at'])
        return ScheduledJobExecutionResult(
            run=run,
            status_code=status.HTTP_409_CONFLICT,
            locked_by={'run_id': active_run.id, 'locked_until': active_run.locked_until},
        )

    blocks = dependency_blocks(module, task.id)
    if blocks and not force_dependencies:
        run = create_job_run(
            module,
            task,
            max_attempts=max_attempts,
            trigger_source=trigger_source,
            triggered_by=triggered_by,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            result={'blocked_by': blocks},
            status_value=UnifiedScheduledJobRun.STATUS_SKIPPED,
            error_message='Dependency check failed.',
        )
        if trigger_source == UnifiedScheduledJobRun.TRIGGER_SCHEDULER:
            next_check_at = defer_task_check(task, seconds=defer_blocked_seconds)
            run.result = {**run.result, 'next_check_at': next_check_at.isoformat() if next_check_at else None}
            run.save(update_fields=['result', 'updated_at'])
        return ScheduledJobExecutionResult(
            run=run,
            status_code=status.HTTP_409_CONFLICT,
            blocked_by=blocks,
        )

    attempts = []
    retry_of = None
    last_error = None
    last_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    for attempt in range(1, max_attempts + 1):
        source = trigger_source if attempt == 1 else UnifiedScheduledJobRun.TRIGGER_RETRY
        job_run = create_job_run(
            module,
            task,
            attempt=attempt,
            max_attempts=max_attempts,
            trigger_source=source,
            triggered_by=triggered_by,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            lock_seconds=lock_seconds,
            retry_of=retry_of,
        )
        try:
            payload = run_module_task(module, task, triggered_by)
        except SchedulerExecutionError as exc:
            last_error = str(exc.payload)
            last_status_code = exc.status_code
            finish_job_run(job_run, UnifiedScheduledJobRun.STATUS_FAILED, result=exc.payload, error_message=last_error)
            attempts.append(job_run.id)
            retry_of = retry_of or job_run
            continue
        except Exception as exc:
            last_error = str(exc)
            finish_job_run(job_run, UnifiedScheduledJobRun.STATUS_FAILED, error_message=last_error)
            attempts.append(job_run.id)
            retry_of = retry_of or job_run
            continue

        finish_job_run(job_run, UnifiedScheduledJobRun.STATUS_SUCCEEDED, result=payload)
        attempts.append(job_run.id)
        return ScheduledJobExecutionResult(
            run=job_run,
            payload=payload,
            attempts=attempts,
        )

    return ScheduledJobExecutionResult(
        run=UnifiedScheduledJobRun.objects.get(pk=attempts[-1]) if attempts else None,
        payload={'detail': last_error or 'Scheduled job failed.'},
        status_code=last_status_code,
        attempts=attempts,
    )


def iter_due_scheduled_tasks(modules=None, now=None):
    now = now or timezone.now()
    selected_modules = modules or get_scheduled_module_keys()
    for module in selected_modules:
        queryset = get_scheduled_job_queryset(module).filter(
            status='ACTIVE',
            next_run_time__isnull=False,
            next_run_time__lte=now,
        ).order_by('next_run_time', 'id')
        for task in queryset:
            if hasattr(task, 'should_run_now') and not task.should_run_now():
                continue
            yield module, task


def run_due_scheduled_jobs(
    *,
    modules=None,
    limit=None,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    lock_seconds=DEFAULT_LOCK_SECONDS,
    defer_blocked_seconds=DEFAULT_DEFER_SECONDS,
    worker_id='',
    dry_run=False,
):
    worker_id = worker_id or build_worker_id()
    summary = {
        'worker_id': worker_id,
        'due': 0,
        'started': 0,
        'succeeded': 0,
        'failed': 0,
        'skipped': 0,
        'runs': [],
        'jobs': [],
    }

    for module, task in iter_due_scheduled_tasks(modules=modules):
        if limit is not None and summary['due'] >= limit:
            break
        summary['due'] += 1
        summary['jobs'].append(normalize_scheduled_job(module, task))
        if dry_run:
            continue

        result = run_scheduled_job(
            module,
            task,
            triggered_by=getattr(task, 'created_by', None),
            trigger_source=UnifiedScheduledJobRun.TRIGGER_SCHEDULER,
            max_attempts=max_attempts,
            lock_seconds=lock_seconds,
            defer_blocked_seconds=defer_blocked_seconds,
            worker_id=worker_id,
        )
        if result.run:
            summary['runs'].append(result.run.id)
        if result.succeeded:
            summary['started'] += 1
            summary['succeeded'] += 1
        elif result.skipped:
            summary['skipped'] += 1
        else:
            summary['failed'] += 1

    return summary
