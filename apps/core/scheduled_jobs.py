from django.apps import apps
from django.core.exceptions import ValidationError

from apps.projects.models import ProjectModuleBinding
from apps.projects.module_registry import (
    build_module_count_summary,
    get_module_definition,
    get_scheduled_module_keys,
    get_scheduled_task_model_path,
)
from apps.projects.unified import (
    accessible_projects_for_user,
    get_module_project_name,
    is_staff_user,
    user_can_access_project,
    user_can_manage_project,
    user_can_access_module_project,
)


def validate_module_name(module):
    if module and not get_scheduled_task_model_path(module):
        raise ValidationError('Unsupported module.')


def get_scheduled_job_model(module):
    validate_module_name(module)
    app_label, model_name = get_scheduled_task_model_path(module).split('.')
    return apps.get_model(app_label, model_name)


def get_scheduled_job_queryset(module):
    model = get_scheduled_job_model(module)
    if module == ProjectModuleBinding.MODULE_API_TESTING:
        return model.objects.select_related(
            'test_suite__project',
            'api_request__collection__project',
            'environment__project',
            'created_by',
        )
    if module == ProjectModuleBinding.MODULE_UI_AUTOMATION:
        return model.objects.select_related(
            'project',
            'test_suite',
            'created_by',
        )
    if module == ProjectModuleBinding.MODULE_APP_AUTOMATION:
        return model.objects.select_related(
            'project',
            'test_suite',
            'test_case',
            'created_by',
        )
    return model.objects.none()


def resolve_task_source_project(module, task):
    if module == ProjectModuleBinding.MODULE_API_TESTING:
        if getattr(task, 'test_suite_id', None) and getattr(task.test_suite, 'project_id', None):
            return task.test_suite.project
        api_request = getattr(task, 'api_request', None)
        if api_request and getattr(api_request, 'collection', None) and getattr(api_request.collection, 'project_id', None):
            return api_request.collection.project
        environment = getattr(task, 'environment', None)
        if environment and getattr(environment, 'project_id', None):
            return environment.project
        return None
    if module == ProjectModuleBinding.MODULE_UI_AUTOMATION:
        return getattr(task, 'project', None)
    if module == ProjectModuleBinding.MODULE_APP_AUTOMATION:
        return getattr(task, 'project', None)
    return None


def resolve_task_target_name(module, task):
    if module == ProjectModuleBinding.MODULE_API_TESTING:
        if getattr(task, 'test_suite_id', None):
            return task.test_suite.name
        if getattr(task, 'api_request_id', None):
            return task.api_request.name
    elif module == ProjectModuleBinding.MODULE_UI_AUTOMATION:
        if getattr(task, 'test_suite_id', None):
            return task.test_suite.name
        test_cases = getattr(task, 'test_cases', None) or []
        if test_cases:
            return f'{len(test_cases)} cases'
    elif module == ProjectModuleBinding.MODULE_APP_AUTOMATION:
        if getattr(task, 'test_suite_id', None):
            return task.test_suite.name
        if getattr(task, 'test_case_id', None):
            return task.test_case.name
    return ''


def get_binding_for_source_project(module, source_project):
    if source_project is None:
        return None
    return ProjectModuleBinding.objects.select_related('project').filter(
        module=module,
        object_id=source_project.id,
    ).first()


def normalize_scheduled_job(module, task, source_project=None, binding=None):
    source_project = source_project or resolve_task_source_project(module, task)
    binding = binding or get_binding_for_source_project(module, source_project)
    source_project_id = getattr(source_project, 'id', None)
    module_definition = get_module_definition(module)
    from .models import UnifiedScheduledJobDependency, UnifiedScheduledJobRun

    last_unified_run = UnifiedScheduledJobRun.objects.filter(
        module=module,
        source_id=task.id,
    ).order_by('-created_at').first()
    running_run = UnifiedScheduledJobRun.objects.filter(
        module=module,
        source_id=task.id,
        status=UnifiedScheduledJobRun.STATUS_RUNNING,
        finished_at__isnull=True,
    ).order_by('-created_at').first()
    dependency_count = UnifiedScheduledJobDependency.objects.filter(
        downstream_module=module,
        downstream_source_id=task.id,
        is_active=True,
    ).count()

    return {
        'job_key': f'{module}:{task.id}',
        'module': module,
        'module_display': module_definition.display_name if module_definition else module,
        'module_description': module_definition.description if module_definition else '',
        'module_frontend_path': module_definition.frontend_path if module_definition else '',
        'module_tag_type': module_definition.tag_type if module_definition else 'info',
        'source_id': task.id,
        'name': task.name,
        'description': getattr(task, 'description', '') or '',
        'task_type': task.task_type,
        'trigger_type': task.trigger_type,
        'status': task.status,
        'target_name': resolve_task_target_name(module, task),
        'source_project_id': source_project_id,
        'source_project_name': get_module_project_name(module, source_project_id) if source_project_id else '',
        'unified_project_id': getattr(binding, 'project_id', None),
        'unified_project_name': binding.project.name if binding else '',
        'last_run_time': getattr(task, 'last_run_time', None),
        'next_run_time': getattr(task, 'next_run_time', None),
        'total_runs': getattr(task, 'total_runs', 0),
        'successful_runs': getattr(task, 'successful_runs', 0),
        'failed_runs': getattr(task, 'failed_runs', 0),
        'created_by_id': getattr(task, 'created_by_id', None),
        'created_at': getattr(task, 'created_at', None),
        'updated_at': getattr(task, 'updated_at', None),
        'last_unified_run_id': getattr(last_unified_run, 'id', None),
        'last_unified_run_status': getattr(last_unified_run, 'status', '') or '',
        'last_unified_run_at': getattr(last_unified_run, 'created_at', None),
        'running_run_id': getattr(running_run, 'id', None),
        'is_running': running_run is not None,
        'dependency_count': dependency_count,
    }


def user_can_access_task(user, module, task, source_project=None, binding=None):
    if is_staff_user(user):
        return True
    source_project = source_project or resolve_task_source_project(module, task)
    binding = binding or get_binding_for_source_project(module, source_project)
    if binding is not None and user_can_access_project(user, binding.project):
        return True
    if source_project is not None:
        return user_can_access_module_project(user, module, source_project.id)
    return getattr(task, 'created_by_id', None) == getattr(user, 'id', None)


def user_can_manage_task(user, module, task, source_project=None, binding=None):
    if is_staff_user(user):
        return True
    source_project = source_project or resolve_task_source_project(module, task)
    binding = binding or get_binding_for_source_project(module, source_project)
    if binding is not None and user_can_manage_project(user, binding.project):
        return True
    if source_project is not None and getattr(source_project, 'owner_id', None) == getattr(user, 'id', None):
        return True
    return getattr(task, 'created_by_id', None) == getattr(user, 'id', None)


def get_scheduled_job_context(user, module, source_id):
    validate_module_name(module)
    try:
        task = get_scheduled_job_queryset(module).get(pk=source_id)
    except get_scheduled_job_model(module).DoesNotExist:
        return None

    source_project = resolve_task_source_project(module, task)
    binding = get_binding_for_source_project(module, source_project)
    if not user_can_access_task(user, module, task, source_project=source_project, binding=binding):
        return None

    return {
        'task': task,
        'source_project': source_project,
        'binding': binding,
        'job': normalize_scheduled_job(
            module,
            task,
            source_project=source_project,
            binding=binding,
        ),
    }


def summarize_scheduled_jobs(jobs):
    summary = {
        'total': 0,
        'active': 0,
        'paused': 0,
        'completed': 0,
        'failed': 0,
        'by_module': {
            **build_module_count_summary(scheduled_only=True),
        },
    }

    for job in jobs:
        summary['total'] += 1
        module = job.get('module')
        if module in summary['by_module']:
            summary['by_module'][module] += 1

        normalized_status = str(job.get('status') or '').strip().lower()
        if normalized_status == 'active':
            summary['active'] += 1
        elif normalized_status == 'paused':
            summary['paused'] += 1
        elif normalized_status == 'completed':
            summary['completed'] += 1
        elif normalized_status == 'failed':
            summary['failed'] += 1

    return summary


def get_scheduled_job_summary(user, unified_project):
    return summarize_scheduled_jobs(
        list_scheduled_jobs(user, unified_project=unified_project)
    )


def list_scheduled_jobs(user, unified_project=None, module=None, status=None, trigger_type=None):
    validate_module_name(module)
    bindings = ProjectModuleBinding.objects.select_related('project')
    if unified_project is not None:
        bindings = bindings.filter(project=unified_project)
    binding_map = {(binding.module, binding.object_id): binding for binding in bindings}

    jobs = []
    modules = [module] if module else get_scheduled_module_keys()

    for module_name in modules:
        queryset = get_scheduled_job_queryset(module_name)
        if status:
            queryset = queryset.filter(status=status)
        if trigger_type:
            queryset = queryset.filter(trigger_type=trigger_type)

        for task in queryset:
            source_project = resolve_task_source_project(module_name, task)
            binding = None
            if source_project is not None:
                binding = binding_map.get((module_name, source_project.id))
            if not user_can_access_task(
                user,
                module_name,
                task,
                source_project=source_project,
                binding=binding,
            ):
                continue
            if source_project is not None:
                if unified_project is not None and binding is None:
                    continue
            elif unified_project is not None:
                continue

            jobs.append(
                normalize_scheduled_job(
                    module_name,
                    task,
                    source_project=source_project,
                    binding=binding,
                )
            )

    jobs.sort(
        key=lambda item: (
            item['next_run_time'] is None,
            item['next_run_time'] or item['created_at'],
            item['job_key'],
        )
    )
    return jobs


def get_scheduled_job(user, module, source_id):
    context = get_scheduled_job_context(user, module, source_id)
    if context is None:
        return None
    return context['job']


def get_accessible_unified_project(user, project_id):
    return accessible_projects_for_user(user).filter(pk=project_id).first()
