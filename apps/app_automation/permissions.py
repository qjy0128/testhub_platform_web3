# -*- coding: utf-8 -*-


from django.db import models


def _user_id(user):
    return getattr(user, 'id', None) or getattr(user, 'pk', None)


def _is_authenticated(user):
    return bool(getattr(user, 'is_authenticated', False))


def _same_user(left, right):
    left_id = _user_id(left)
    right_id = _user_id(right)
    return left_id is not None and right_id is not None and left_id == right_id


def _is_staff_user(user):
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _member_exists(project, user):
    members = getattr(project, 'members', None)
    if members is None:
        return False

    try:
        return members.filter(id=_user_id(user)).exists()
    except Exception:
        return False


def user_can_access_app_project(user, project):
    if not _is_authenticated(user) or project is None:
        return False

    if _is_staff_user(user):
        return True

    if _same_user(user, getattr(project, 'owner', None)):
        return True

    return _member_exists(project, user)


def accessible_app_projects_for_user(user):
    from .models import AppProject

    if not _is_authenticated(user):
        return AppProject.objects.none()

    if _is_staff_user(user):
        return AppProject.objects.all()

    return AppProject.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()


def app_project_access_filter(user, project_field='project', ownerless_user_field='created_by'):
    if not _is_authenticated(user):
        return models.Q(pk__in=[])

    if _is_staff_user(user):
        return models.Q()

    accessible_project_ids = accessible_app_projects_for_user(user).values('id')
    return (
        models.Q(**{f'{project_field}__in': accessible_project_ids}) |
        models.Q(**{project_field: None, ownerless_user_field: user})
    )


def user_can_access_app_case(user, test_case):
    if test_case is None or not _is_authenticated(user):
        return False

    if _is_staff_user(user):
        return True

    if user_can_access_app_project(user, getattr(test_case, 'project', None)):
        return True

    return _same_user(user, getattr(test_case, 'created_by', None))


def user_can_access_app_suite(user, test_suite):
    if test_suite is None or not _is_authenticated(user):
        return False

    if _is_staff_user(user):
        return True

    if user_can_access_app_project(user, getattr(test_suite, 'project', None)):
        return True

    return _same_user(user, getattr(test_suite, 'created_by', None))


def user_can_access_app_package(user, app_package):
    if app_package is None or not _is_authenticated(user):
        return False

    if _is_staff_user(user):
        return True

    return _same_user(user, getattr(app_package, 'created_by', None))


def user_can_access_app_execution(user, execution):
    if not _is_authenticated(user) or execution is None:
        return False

    if _is_staff_user(user):
        return True

    if _same_user(user, getattr(execution, 'user', None)):
        return True

    test_case = getattr(execution, 'test_case', None)
    if user_can_access_app_project(user, getattr(test_case, 'project', None)):
        return True

    test_suite = getattr(execution, 'test_suite', None)
    if user_can_access_app_project(user, getattr(test_suite, 'project', None)):
        return True

    return False
