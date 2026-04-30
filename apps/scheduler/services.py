from importlib.util import find_spec

from django.conf import settings

from apps.core.scheduler_engine import DEFAULT_MAX_ATTEMPTS, run_due_scheduled_jobs


BACKEND_LOCAL = 'local'
BACKEND_DJANGO_Q2 = 'django_q2'


def django_q2_available():
    return find_spec('django_q') is not None


def get_scheduler_backend():
    configured_backend = str(getattr(settings, 'SCHEDULER_BACKEND', BACKEND_LOCAL) or BACKEND_LOCAL).lower()
    if configured_backend == BACKEND_DJANGO_Q2 and django_q2_available():
        return BACKEND_DJANGO_Q2
    return BACKEND_LOCAL


def get_scheduler_capabilities():
    backend = get_scheduler_backend()
    return {
        'independent_app': True,
        'backend': backend,
        'configured_backend': getattr(settings, 'SCHEDULER_BACKEND', BACKEND_LOCAL),
        'django_q2_available': django_q2_available(),
        'supports_dependencies': True,
        'supports_retries': True,
        'supports_persistent_runs': True,
        'supports_alerts': True,
        'supports_async_queue': backend == BACKEND_DJANGO_Q2,
    }


def dispatch_due_scheduled_jobs(
    *,
    modules=None,
    limit=None,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    dry_run=False,
    async_queue=True,
):
    backend = get_scheduler_backend()
    if backend == BACKEND_DJANGO_Q2 and async_queue and not dry_run:
        from django_q.tasks import async_task

        task_id = async_task(
            'apps.core.scheduler_engine.run_due_scheduled_jobs',
            modules=modules,
            limit=limit,
            max_attempts=max_attempts,
            dry_run=False,
        )
        return {
            'queued': True,
            'backend': backend,
            'task_id': task_id,
        }

    summary = run_due_scheduled_jobs(
        modules=modules,
        limit=limit,
        max_attempts=max_attempts,
        dry_run=dry_run,
    )
    return {
        'queued': False,
        'backend': backend,
        'summary': summary,
    }
