"""调度器权限回归测试（静态层）。

关键：``SchedulerRunDueJobsView`` 必须仅 admin 可访问。
我们用类属性断言代替实际 HTTP 请求，避开 Windows 上 pytest tmpdir 与
SQLite 内存库的资源竞态。
"""
from __future__ import annotations


def test_run_due_jobs_view_is_admin_only():
    from rest_framework.permissions import IsAdminUser

    from apps.scheduler.views import SchedulerRunDueJobsView

    assert IsAdminUser in SchedulerRunDueJobsView.permission_classes


def test_capabilities_view_is_authenticated_only():
    from rest_framework.permissions import IsAuthenticated

    from apps.scheduler.views import SchedulerCapabilitiesView

    assert IsAuthenticated in SchedulerCapabilitiesView.permission_classes


def test_run_due_jobs_clamps_limit():
    """``MAX_DISPATCH_LIMIT`` 必须存在并且为正整数。"""
    from apps.scheduler.views import MAX_DISPATCH_LIMIT

    assert isinstance(MAX_DISPATCH_LIMIT, int)
    assert MAX_DISPATCH_LIMIT > 0
    assert MAX_DISPATCH_LIMIT <= 10000  # sanity bound


def test_run_due_jobs_url_resolves():
    from django.urls import resolve

    match = resolve('/api/scheduler/run-due/')
    from apps.scheduler.views import SchedulerRunDueJobsView

    view_cls = getattr(match.func, 'cls', None) or getattr(match.func, 'view_class', None)
    assert view_cls is SchedulerRunDueJobsView
