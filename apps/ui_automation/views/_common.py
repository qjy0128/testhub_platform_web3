"""Shared utility functions and classes used across multiple view modules."""

import logging
import os
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import models
from rest_framework.pagination import PageNumberPagination

from ..models import UiProject, TestScript, TestCase

logger = logging.getLogger(__name__)
User = get_user_model()


def is_ui_automation_admin(user):
    return getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)


def accessible_ui_projects_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return UiProject.objects.none()
    if is_ui_automation_admin(user):
        return UiProject.objects.all()
    return UiProject.objects.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()


def accessible_test_scripts_for_user(user):
    return TestScript.objects.filter(project__in=accessible_ui_projects_for_user(user))


def accessible_test_cases_for_user(user):
    return TestCase.objects.filter(project__in=accessible_ui_projects_for_user(user))


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


def is_retryable_mysql_error(error):
    error_str = str(error)
    retryable_markers = (
        '2006',
        '2003',
        'MySQL server has gone away',
        "Can't connect to MySQL server",
        'Lost connection to MySQL server',
        'WinError 10048',
        'WinError 10022',
    )
    return error_str == '0' or any(marker in error_str for marker in retryable_markers)


def extract_step_info(s, step_index):
    """提取步骤信息的辅助函数，确保返回可读的步骤描述"""
    step_info = {'step': step_index}

    # 尝试多种方式提取可读信息
    if hasattr(s, 'action'):
        # 如果有action属性
        action_data = s.action
        if isinstance(action_data, str):
            step_info['action'] = action_data
        elif hasattr(action_data, '__dict__'):
            # 如果是对象，提取关键属性
            attrs = {}
            for key in ['type', 'description', 'goal', 'coordinate', 'text', 'output', 'result']:
                if hasattr(action_data, key):
                    value = getattr(action_data, key)
                    if isinstance(value, str):
                        attrs[key] = value
                    elif callable(value):
                        attrs[key] = getattr(value, '__name__', str(value))
                    else:
                        attrs[key] = str(value)
            if attrs:
                step_info['action'] = attrs
        else:
            step_info['action'] = str(action_data)
    elif hasattr(s, 'model_output'):
        # 如果有model_output属性
        output_data = s.model_output
        if isinstance(output_data, str):
            step_info['action'] = output_data
        elif hasattr(output_data, '__dict__'):
            # 提取model_output的关键信息
            attrs = {'type': 'model_output'}
            for key in ['action', 'description', 'goal', 'coordinate', 'text']:
                if hasattr(output_data, key):
                    value = getattr(output_data, key)
                    attrs[key] = str(value) if value else None
            step_info['action'] = attrs
        else:
            step_info['action'] = str(output_data)
    elif hasattr(s, '__dict__'):
        # 通用的对象提取
        attrs = {}
        for key in dir(s):
            if not key.startswith('_'):
                try:
                    value = getattr(s, key)
                    if not callable(value):
                        attrs[key] = str(value)
                except Exception:
                    pass
        if attrs:
            step_info['action'] = attrs
    else:
        # 最后回退，但检查是否是函数对象
        if callable(s):
            step_info['action'] = f"<Action: {getattr(s, '__name__', 'unknown action')}>"
        else:
            step_info['action'] = str(s)

    return step_info


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000
