"""Allure 报告 HTML 渲染。

实际模板见 ``templates/api_testing/allure_summary.html`` 和
``allure_fallback.html``，本模块只负责构建 context 并交给 Django 模板引擎。
保留原有公开函数名（``render_summary_report`` / ``render_fallback_report``）以
兼容老调用点。
"""
from __future__ import annotations

from typing import Iterable

from django.template.loader import render_to_string


def render_fallback_report(execution) -> str:
    return render_to_string(
        'api_testing/allure_fallback.html',
        {
            'execution': execution,
            'execution_status_display': execution.get_status_display(),
        },
    )


def _build_items(results: Iterable[dict]) -> list[dict]:
    items: list[dict] = []
    for i, r in enumerate(results or []):
        passed = r.get('passed', False)
        method = r.get('method', 'GET')
        items.append({
            'result_class': 'passed' if passed else 'failed',
            'method': method,
            'method_class': f'method-{method.lower()}',
            'name': r.get('name', f'测试请求 {i + 1}'),
            'url': r.get('url', ''),
            'status_text': '通过' if passed else '失败',
            'error': r.get('error') or '',
        })
    return items


def render_summary_report(execution, results: Iterable[dict]) -> str:
    return render_to_string(
        'api_testing/allure_summary.html',
        {
            'execution': execution,
            'execution_status_display': execution.get_status_display(),
            'project_name': (
                execution.test_suite.project.name if execution.test_suite.project else 'N/A'
            ),
            'created_at': (
                execution.created_at.strftime('%Y-%m-%d %H:%M:%S') if execution.created_at else 'N/A'
            ),
            'status_class': 'status-passed' if execution.status == 'COMPLETED' else 'status-failed',
            'items': _build_items(results),
        },
    )
