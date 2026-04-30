import logging
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime

from django.conf import settings
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.ui_automation.planned_task_state import (
    ACTIVE_TASK_STATUSES,
    sync_planned_task_status,
)

from .models import AiTestingRun, AiTestingTask

logger = logging.getLogger(__name__)

AI_TESTING_STOP_SIGNALS = {}


@contextmanager
def temporary_async_unsafe_env():
    previous = os.environ.get('DJANGO_ALLOW_ASYNC_UNSAFE')
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)
        else:
            os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = previous


def build_initial_plan(instruction):
    lines = [
        line.strip(' -\t')
        for line in (instruction or '').replace('\r\n', '\n').split('\n')
        if line.strip()
    ]
    if not lines:
        return []
    if len(lines) == 1:
        return [normalize_planned_step({'id': 1, 'description': lines[0], 'status': 'pending'}, 1)]
    return [
        normalize_planned_step({'id': index, 'description': line, 'status': 'pending'}, index)
        for index, line in enumerate(lines, start=1)
    ]


def normalize_planned_step(step, fallback_index):
    step_id = step.get('id') or step.get('index') or fallback_index
    description = step.get('description') or step.get('title') or step.get('name') or ''
    status = str(step.get('status') or 'pending').strip().lower()
    return {
        'id': step_id,
        'index': fallback_index,
        'description': str(description),
        'title': str(description),
        'status': status,
    }


def normalize_planned_steps(planned_steps):
    return [
        normalize_planned_step(step, index)
        for index, step in enumerate(planned_steps or [], start=1)
        if isinstance(step, dict)
    ]


def create_ai_testing_run(task, user, *, start_immediately=False):
    planned_steps = build_initial_plan(task.instruction)
    run = AiTestingRun.objects.create(
        task=task,
        project=task.project,
        status=AiTestingRun.STATUS_PENDING,
        instruction_snapshot=task.instruction,
        target_url_snapshot=task.target_url,
        execution_mode=task.execution_mode,
        planned_steps=planned_steps,
        artifacts={
            'screenshots': [],
            'recordings': [],
            'reports': [],
        },
        created_by=user,
    )
    if start_immediately:
        run = start_ai_testing_run(run)
    return run


def cancel_ai_testing_run(run):
    if run.status in {AiTestingRun.STATUS_SUCCEEDED, AiTestingRun.STATUS_FAILED, AiTestingRun.STATUS_CANCELLED}:
        return run
    AI_TESTING_STOP_SIGNALS[run.id] = True
    run.status = AiTestingRun.STATUS_CANCELLED
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'finished_at', 'updated_at'])
    return run


def start_ai_testing_run(run, *, dispatch=True):
    with transaction.atomic():
        locked_run = AiTestingRun.objects.select_for_update().get(pk=run.pk)
        if locked_run.status == AiTestingRun.STATUS_CANCELLED:
            return locked_run
        if locked_run.status == AiTestingRun.STATUS_RUNNING:
            return locked_run
        if locked_run.status not in {AiTestingRun.STATUS_PENDING, AiTestingRun.STATUS_FAILED}:
            return locked_run

        locked_run.status = AiTestingRun.STATUS_RUNNING
        locked_run.started_at = locked_run.started_at or timezone.now()
        locked_run.finished_at = None
        locked_run.error_message = ''
        locked_run.logs = append_log(locked_run.logs, '[System] AI testing run started.')
        locked_run.save(update_fields=['status', 'started_at', 'finished_at', 'error_message', 'logs', 'updated_at'])

    AI_TESTING_STOP_SIGNALS[locked_run.id] = False
    if dispatch:
        dispatch_ai_testing_run(locked_run.id)
    return locked_run


def dispatch_ai_testing_run(run_id):
    thread = threading.Thread(
        target=execute_ai_testing_run,
        args=(run_id,),
        name=f'ai-testing-run-{run_id}',
        daemon=True,
    )
    thread.start()
    return thread


def run_pending_ai_testing_runs(*, limit=None, runner=None, manage_connections=True, queryset=None):
    queryset = queryset or AiTestingRun.objects.all()
    queryset = queryset.filter(
        status=AiTestingRun.STATUS_PENDING,
    ).select_related('task').order_by('created_at')
    if limit is not None:
        queryset = queryset[:limit]

    total = 0
    succeeded = 0
    failed = 0
    cancelled = 0
    run_ids = []

    for pending_run in queryset:
        total += 1
        run_ids.append(pending_run.id)
        running_run = start_ai_testing_run(pending_run, dispatch=False)
        execute_ai_testing_run(running_run.id, runner=runner, manage_connections=manage_connections)
        running_run.refresh_from_db()
        if running_run.status == AiTestingRun.STATUS_SUCCEEDED:
            succeeded += 1
        elif running_run.status == AiTestingRun.STATUS_CANCELLED:
            cancelled += 1
        else:
            failed += 1

    return {
        'total': total,
        'succeeded': succeeded,
        'failed': failed,
        'cancelled': cancelled,
        'run_ids': run_ids,
    }


def execute_ai_testing_run(run_id, *, runner=None, manage_connections=True):
    if manage_connections:
        close_old_connections()
        try:
            connection.close()
        except Exception:
            pass

    run = AiTestingRun.objects.select_related('task', 'project').get(pk=run_id)
    if run.status != AiTestingRun.STATUS_RUNNING:
        return run

    browser_config = run.task.browser_config if run.task_id else {}
    browser_config = browser_config if isinstance(browser_config, dict) else {}
    enable_gif = parse_bool(browser_config.get('enable_gif', True), default=True)
    runner = runner or load_browser_runner()

    def safe_save(update_fields=None):
        for attempt in range(3):
            try:
                with temporary_async_unsafe_env():
                    run.save(update_fields=update_fields)
                return
            except (DatabaseError, Exception) as exc:
                if attempt == 2:
                    raise
                logger.warning('Retrying AI testing run save after error: %s', exc)
                try:
                    connection.close()
                except Exception:
                    pass

    def should_stop():
        if AI_TESTING_STOP_SIGNALS.get(run.id, False):
            return True
        with temporary_async_unsafe_env():
            run.refresh_from_db(fields=['status'])
        return run.status == AiTestingRun.STATUS_CANCELLED

    def on_analysis_complete(planned_steps):
        normalized_steps = normalize_planned_steps(planned_steps)
        if normalized_steps:
            run.planned_steps = normalized_steps
        run.logs = append_log(run.logs, '[System] Task analysis finished; execution started.')
        safe_save(update_fields=['planned_steps', 'logs', 'updated_at'])

    def on_step_update(step_info):
        if not isinstance(step_info, dict):
            return
        if step_info.get('type') == 'log':
            content = step_info.get('content')
            if content:
                run.logs = f'{run.logs}{content}'
                safe_save(update_fields=['logs', 'updated_at'])
            return

        task_id = step_info.get('task_id')
        task_status = step_info.get('status')
        if task_id and task_status:
            result = sync_planned_task_status(run.planned_steps, task_id, task_status)
            event = {
                'task_id': task_id,
                'status': str(task_status).strip().lower(),
                'updated': result['updated'],
                'backfilled_task_ids': result['backfilled_task_ids'],
                'created_at': timezone.now().isoformat(),
            }
            run.executed_steps = [*run.executed_steps, event]
            safe_save(update_fields=['planned_steps', 'executed_steps', 'updated_at'])

    try:
        task_description = build_agent_task_description(run)
        history = runner(
            task_description,
            analysis_callback=on_analysis_complete,
            step_callback=on_step_update,
            should_stop=should_stop,
            execution_mode=map_execution_mode(run.execution_mode),
            enable_gif=enable_gif,
            case_name=run.task.name[:50] if run.task_id else 'AI Testing Task',
            wallet_context={},
        )

        run.artifacts = {
            **(run.artifacts or {}),
            'history_steps': extract_history_steps(history),
        }
        gif_path = collect_gif_artifact(run) if enable_gif else None
        if gif_path:
            run.artifacts = {
                **run.artifacts,
                'recordings': [*run.artifacts.get('recordings', []), gif_path],
            }

        if should_stop():
            run.status = AiTestingRun.STATUS_CANCELLED
            run.logs = append_log(run.logs, '[System] Run cancelled.')
        else:
            run.status = resolve_run_status(run.planned_steps)
            run.logs = append_log(run.logs, format_run_summary(run.planned_steps))
        run.finished_at = timezone.now()
        safe_save(update_fields=['status', 'artifacts', 'logs', 'finished_at', 'updated_at'])
    except Exception as exc:
        logger.exception('AI testing run failed: %s', exc)
        with temporary_async_unsafe_env():
            run.refresh_from_db()
        if run.status == AiTestingRun.STATUS_CANCELLED:
            run.logs = append_log(run.logs, '[System] Run cancelled.')
        else:
            mark_first_active_step(run.planned_steps, 'failed')
            run.status = AiTestingRun.STATUS_FAILED
            run.error_message = str(exc)
            run.logs = append_log(run.logs, f'[System] Run failed: {exc}')
            run.logs = append_log(run.logs, format_run_summary(run.planned_steps))
        run.finished_at = timezone.now()
        safe_save(update_fields=['status', 'planned_steps', 'logs', 'error_message', 'finished_at', 'updated_at'])
    finally:
        AI_TESTING_STOP_SIGNALS.pop(run_id, None)
        if manage_connections:
            close_old_connections()
    return run


def load_browser_runner():
    from apps.ui_automation.ai_agent import run_full_process_sync

    return run_full_process_sync


def map_execution_mode(execution_mode):
    if execution_mode in {AiTestingTask.MODE_BROWSER_TEXT, 'text', 'browser_use_text'}:
        return 'text'
    if execution_mode in {AiTestingTask.MODE_BROWSER_VISION, 'vision', 'browser_use_vision'}:
        return 'vision'
    return 'text'


def build_agent_task_description(run):
    parts = []
    if run.target_url_snapshot:
        parts.append(f'Target URL: {run.target_url_snapshot}')
    parts.append(run.instruction_snapshot or '')
    return '\n\n'.join(part for part in parts if part).strip()


def resolve_run_status(planned_steps):
    if not planned_steps:
        return AiTestingRun.STATUS_SUCCEEDED
    statuses = {step.get('status', 'pending') for step in planned_steps}
    if 'failed' in statuses:
        return AiTestingRun.STATUS_FAILED
    if statuses.intersection(ACTIVE_TASK_STATUSES):
        return AiTestingRun.STATUS_FAILED
    return AiTestingRun.STATUS_SUCCEEDED


def mark_first_active_step(planned_steps, status_value):
    for step in planned_steps or []:
        if step.get('status', 'pending') in ACTIVE_TASK_STATUSES:
            step['status'] = status_value
            return step.get('id')
    return None


def format_run_summary(planned_steps):
    summary = {
        'total': len(planned_steps or []),
        'completed': 0,
        'failed': 0,
        'skipped': 0,
        'pending': 0,
        'in_progress': 0,
    }
    for step in planned_steps or []:
        status_value = step.get('status', 'pending')
        summary[status_value] = summary.get(status_value, 0) + 1
    if summary['total'] == 0:
        return '[System] Run finished without planned sub-tasks.'
    return (
        '[System] Sub-task summary: '
        f"total {summary['total']}, completed {summary['completed']}, "
        f"failed {summary['failed']}, skipped {summary['skipped']}, "
        f"remaining {summary['pending'] + summary['in_progress']}."
    )


def extract_history_steps(history):
    steps = []
    for index, step in enumerate(getattr(history, 'steps', []) or [], start=1):
        steps.append({
            'index': index,
            'action': serialize_step_value(
                getattr(step, 'action', None)
                or getattr(step, 'model_output', None)
                or step
            ),
        })
    return steps


def serialize_step_value(value):
    if value is None:
        return ''
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return value
    if hasattr(value, '__dict__'):
        return {
            key: serialize_step_value(item)
            for key, item in value.__dict__.items()
            if not key.startswith('_')
        }
    return str(value)


def collect_gif_artifact(run):
    source_path = os.path.join(os.getcwd(), 'agent_history.gif')
    if not os.path.exists(source_path):
        return None

    target_dir = os.path.join(settings.MEDIA_ROOT, 'ai_testing_recording')
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    safe_name = ''.join(ch if ch.isalnum() or ch in (' ', '_', '-') else '_' for ch in run.task.name)[:60]
    filename = f'{safe_name or "ai_testing"}_{run.id}_{timestamp}.gif'
    target_path = os.path.join(target_dir, filename)
    shutil.move(source_path, target_path)
    return f'media/ai_testing_recording/{filename}'


def append_log(logs, message):
    prefix = logs or ''
    separator = '' if not prefix or prefix.endswith('\n') else '\n'
    return f'{prefix}{separator}{message}\n'


def parse_bool(value, *, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}
