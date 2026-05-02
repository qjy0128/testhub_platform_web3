"""共享辅助：访问控制 helpers 和 SSE 透传 renderer。"""
from django.db import models
from rest_framework.renderers import BaseRenderer

from apps.projects.models import Project
from apps.projects.unified import accessible_projects_for_user, user_can_access_project

from ..models import RequirementDocument


class PassThroughRenderer(BaseRenderer):
    """直接透传 StreamingHttpResponse，不做任何渲染处理。"""
    media_type = 'text/event-stream'
    format = 'event-stream'
    render_level = 0

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def is_staff_user(user) -> bool:
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def accessible_requirement_documents_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return RequirementDocument.objects.none()
    if is_staff_user(user):
        return RequirementDocument.objects.all()
    return RequirementDocument.objects.filter(
        models.Q(uploaded_by=user)
        | models.Q(project__in=accessible_projects_for_user(user))
    ).distinct()


def resolve_accessible_project(user, project_id):
    if not project_id:
        return None
    try:
        project = Project.objects.get(id=project_id)
    except (Project.DoesNotExist, TypeError, ValueError):
        return None
    if not user_can_access_project(user, project):
        return None
    return project


# 兼容旧调用签名（views.py 内部使用 _ 前缀私有名）：
_is_staff_user = is_staff_user
_accessible_requirement_documents_for_user = accessible_requirement_documents_for_user
_resolve_accessible_project = resolve_accessible_project
