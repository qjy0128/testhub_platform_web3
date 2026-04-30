from django.apps import apps
from django.db import models

from .models import MetaProject, Project, ProjectMember, ProjectModuleBinding, ProjectPermissionPolicy
from .module_registry import get_module_project_model_path


def is_authenticated_user(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def is_staff_user(user):
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def get_module_project_model(module):
    model_path = get_module_project_model_path(module)
    if not model_path:
        return None
    app_label, model_name = model_path.split('.')
    return apps.get_model(app_label, model_name)


def get_module_project(module, object_id):
    model = get_module_project_model(module)
    if model is None:
        return None
    try:
        return model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return None


def get_module_project_name(module, object_id):
    module_project = get_module_project(module, object_id)
    if module_project is None:
        return ''
    return getattr(module_project, 'name', str(module_project))


def accessible_projects_for_user(user):
    if not is_authenticated_user(user):
        return Project.objects.none()
    if is_staff_user(user):
        return Project.objects.all()
    return Project.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()


def accessible_meta_projects_for_user(user):
    if not is_authenticated_user(user):
        return MetaProject.objects.none()
    if is_staff_user(user):
        return MetaProject.objects.all()
    accessible_project_ids = accessible_projects_for_user(user).values('id')
    return MetaProject.objects.filter(
        models.Q(owner=user) | models.Q(project_id__in=accessible_project_ids)
    ).distinct()


def user_can_access_project(user, project):
    if not is_authenticated_user(user):
        return False
    if is_staff_user(user):
        return True
    if getattr(project, 'owner_id', None) == getattr(user, 'id', None):
        return True
    return ProjectMember.objects.filter(project=project, user=user).exists()


def user_can_manage_project(user, project):
    if not is_authenticated_user(user):
        return False
    if is_staff_user(user):
        return True
    if getattr(project, 'owner_id', None) == getattr(user, 'id', None):
        return True
    return ProjectMember.objects.filter(
        project=project,
        user=user,
        role__in=['owner', 'admin'],
    ).exists()


def get_project_member_role(user, project):
    if not is_authenticated_user(user):
        return ''
    if is_staff_user(user):
        return 'owner'
    if getattr(project, 'owner_id', None) == getattr(user, 'id', None):
        return 'owner'
    membership = ProjectMember.objects.filter(project=project, user=user).values('role').first()
    return membership['role'] if membership else ''


def ensure_meta_project_tree(project, owner=None):
    owner = owner or getattr(project, 'owner', None)
    if owner is None:
        return None

    root = MetaProject.objects.filter(
        project=project,
        parent__isnull=True,
        node_type=MetaProject.NODE_META_PROJECT,
    ).first()
    if root is None:
        root = MetaProject.objects.create(
            project=project,
            node_type=MetaProject.NODE_META_PROJECT,
            name=project.name,
            description=project.description or '',
            status=project.status,
            owner=owner,
            sort_order=0,
        )
    else:
        changed_fields = []
        if root.name != project.name:
            root.name = project.name
            changed_fields.append('name')
        if root.description != (project.description or ''):
            root.description = project.description or ''
            changed_fields.append('description')
        if root.status != project.status:
            root.status = project.status
            changed_fields.append('status')
        if root.owner_id != owner.id:
            root.owner = owner
            changed_fields.append('owner')
        if changed_fields:
            changed_fields.append('updated_at')
            root.save(update_fields=changed_fields)

    for index, binding in enumerate(project.module_bindings.all().order_by('module', 'id'), start=1):
        ensure_module_meta_node_for_binding(binding, root=root, sort_order=index)

    return root


def ensure_module_meta_node_for_binding(binding, root=None, sort_order=None):
    root = root or ensure_meta_project_tree(binding.project)
    if root is None:
        return None

    node = MetaProject.objects.filter(
        project=binding.project,
        module=binding.module,
        object_id=binding.object_id,
    ).first()
    module_name = binding.display_name or get_module_project_name(binding.module, binding.object_id)
    if not module_name:
        module_name = f'{binding.module} #{binding.object_id}'

    defaults = {
        'parent': root,
        'node_type': MetaProject.NODE_MODULE_PROJECT,
        'name': module_name,
        'description': '',
        'status': binding.project.status,
        'owner': binding.project.owner,
        'sort_order': sort_order or 0,
    }
    if node is None:
        node = MetaProject.objects.create(
            project=binding.project,
            module=binding.module,
            object_id=binding.object_id,
            **defaults,
        )
    else:
        changed_fields = []
        for field, value in defaults.items():
            current_value = getattr(node, field)
            current_id = getattr(node, f'{field}_id', None) if field in {'parent', 'owner'} else current_value
            expected_id = getattr(value, 'id', None) if field in {'parent', 'owner'} else value
            if current_id != expected_id:
                setattr(node, field, value)
                changed_fields.append(field)
        if changed_fields:
            changed_fields.append('updated_at')
            node.save(update_fields=changed_fields)
    return node


def user_has_project_action_permission(user, project, module, action, default_roles=None):
    if not is_authenticated_user(user):
        return False
    if is_staff_user(user):
        return True

    role = get_project_member_role(user, project)
    if not role:
        return False

    policies = list(ProjectPermissionPolicy.objects.filter(
        project=project,
        action=action,
        is_active=True,
        module__in=[module, ProjectPermissionPolicy.MODULE_ANY],
    ).order_by('module'))
    if policies:
        exact_policy = next((item for item in policies if item.module == module), None)
        active_policy = exact_policy or policies[0]
        allowed_roles = [str(item).lower() for item in (active_policy.allowed_roles or [])]
        return role in allowed_roles

    default_roles = default_roles or ['owner', 'admin']
    return role in [str(item).lower() for item in default_roles]


def user_can_access_module_project(user, module, object_id):
    module_project = get_module_project(module, object_id)
    if module_project is None or not is_authenticated_user(user):
        return False
    if is_staff_user(user):
        return True
    if getattr(module_project, 'owner_id', None) == getattr(user, 'id', None):
        return True
    members = getattr(module_project, 'members', None)
    if members is None:
        return False
    return members.filter(id=getattr(user, 'id', None)).exists()
