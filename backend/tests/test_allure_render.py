"""Allure 报告 HTML 渲染回归测试。

模板从 ``apps/api_testing/_allure_html.py`` 内联字符串迁到 Django 模板后，
需要保证 context 注入字段完整、特殊字符正确转义。
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

# 这些测试只渲染模板；不需要 DB。


def _mock_execution(status='COMPLETED'):
    project = SimpleNamespace(name='Demo Project')
    test_suite = SimpleNamespace(name='Suite A', project=project)
    return SimpleNamespace(
        id=42,
        test_suite=test_suite,
        status=status,
        total_requests=3,
        passed_requests=2,
        failed_requests=1,
        created_at=datetime(2026, 5, 1, 9, 30),
        get_status_display=lambda: '已完成',
    )


class TestSummaryReport:
    def test_renders_with_passing_status(self):
        from apps.api_testing._allure_html import render_summary_report

        html = render_summary_report(_mock_execution('COMPLETED'), [])
        assert 'Demo Project' in html
        assert 'status-passed' in html
        assert 'Suite A' in html

    def test_renders_with_failing_status(self):
        from apps.api_testing._allure_html import render_summary_report

        html = render_summary_report(_mock_execution('FAILED'), [])
        assert 'status-failed' in html

    def test_includes_result_items(self):
        from apps.api_testing._allure_html import render_summary_report

        results = [
            {'name': 'login', 'method': 'POST', 'url': '/api/login/', 'passed': True},
            {
                'name': 'fetch user',
                'method': 'GET',
                'url': '/api/users/me/',
                'passed': False,
                'error': '500 Internal Server Error',
            },
        ]
        html = render_summary_report(_mock_execution(), results)
        assert 'method-post' in html
        assert 'method-get' in html
        assert '500 Internal Server Error' in html

    def test_no_project_handled(self):
        from apps.api_testing._allure_html import render_summary_report

        execution = _mock_execution()
        execution.test_suite.project = None
        html = render_summary_report(execution, [])
        assert 'N/A' in html


class TestFallbackReport:
    def test_renders_fallback(self):
        from apps.api_testing._allure_html import render_fallback_report

        html = render_fallback_report(_mock_execution())
        assert 'Suite A' in html
        assert '总请求数: 3' in html


# --------------------------------------------------------------------------- #
# 测试用例解析
# --------------------------------------------------------------------------- #

class TestCaseParsing:
    def test_parse_table_format(self):
        from apps.requirement_analysis.views._test_case_parsing import (
            parse_test_cases_content,
        )
        content = (
            '| 用例ID | 测试目标 | 前置条件 | 预期结果 | 优先级 |\n'
            '|---|---|---|---|---|\n'
            '| TC001 | 登录 | 已注册 | 成功 | P1 |\n'
        )
        cases = parse_test_cases_content(content)
        assert len(cases) == 1
        assert cases[0]['caseId'] == 'TC001'
        assert cases[0]['priority'] == 'P1'

    def test_round_trip(self):
        from apps.requirement_analysis.views._test_case_parsing import (
            parse_test_cases_content,
            reconstruct_test_cases_content,
        )
        cases = [{'caseId': 'TC001', 'scenario': '登录', 'precondition': '已注册', 'expected': '成功', 'priority': 'P1'}]
        rebuilt = reconstruct_test_cases_content(cases)
        cases2 = parse_test_cases_content(rebuilt)
        assert cases2[0]['caseId'] == 'TC001'
        assert cases2[0]['scenario'] == '登录'

    def test_priority_mapping(self):
        from apps.requirement_analysis.views._test_case_parsing import map_priority
        assert map_priority('P0') == 'critical'
        assert map_priority('P1') == 'high'
        assert map_priority('P2') == 'medium'
        assert map_priority('P3') == 'low'
        assert map_priority('未知') == 'medium'  # 兜底
