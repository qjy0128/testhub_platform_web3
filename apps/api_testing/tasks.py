"""api_testing 的 Celery 任务。

迁移自 ``views.py``：原 ``ApiExecutionViewSet.generate_allure_report`` 在 HTTP
请求线程内同步调用 ``subprocess.run``，最坏阻塞 90 秒。这里把整个流程搬到
异步任务，view 只负责落库 + dispatch + 返回 202，前端通过
``GET .../allure-report-status/`` 轮询。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import _allure_html
from .models import TestExecution

logger = logging.getLogger(__name__)


def _check_java_environment() -> bool:
    """检测 java 命令是否可用。"""
    try:
        result = subprocess.run(
            ['java', '-version'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version = result.stderr.split('\n')[0] if result.stderr else 'Unknown'
            logger.info('Java 环境可用: %s', version)
            return True
        logger.warning('Java 命令执行失败: %s', result.stderr)
        return False
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning('Java 环境检查失败: %s', e)
        return False


def _resolve_allure_command() -> Path | None:
    base_dir = Path(__file__).resolve().parent.parent.parent
    name = 'allure.bat' if os.name == 'nt' else 'allure'
    candidate = base_dir / 'allure' / 'bin' / name
    if candidate.exists():
        return candidate
    for fallback in (Path('/usr/local/bin/allure'), Path('/usr/bin/allure')):
        if fallback.exists():
            return fallback
    return None


def _force_clean(directory: str) -> None:
    if not os.path.exists(directory):
        return
    try:
        shutil.rmtree(directory)
    except PermissionError:
        logger.warning('无法删除目录（权限不足）：%s，尝试清理内容', directory)
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            except OSError:
                pass


def _generate_test_result_files(execution: TestExecution, report_dir: str) -> None:
    """落地 Allure 兼容的 *.json 文件供 ``allure generate`` 渲染。"""
    if not execution.results:
        logger.warning('执行记录 %s 没有结果数据', execution.id)
        return

    container = {
        'uuid': str(execution.id),
        'name': execution.test_suite.name,
        'children': [f'{execution.id}-{i}' for i in range(len(execution.results))],
    }
    container_path = os.path.join(report_dir, f'{execution.id}-container.json')
    with open(container_path, 'w', encoding='utf-8') as f:
        json.dump(container, f, ensure_ascii=False, indent=2)

    project_name = execution.test_suite.project.name if execution.test_suite.project else 'unknown'
    for i, result in enumerate(execution.results):
        request_result = {
            'uuid': f'{execution.id}-{i}',
            'name': result.get('name', f'测试请求 {i + 1}'),
            'status': 'passed' if result.get('passed', False) else 'failed',
            'stage': 'finished',
            'start': int(time.time() * 1000) - 1000,
            'stop': int(time.time() * 1000),
            'description': f"Method: {result.get('method', 'GET')}\nURL: {result.get('url', '')}",
            'historyId': f'{execution.test_suite.id}-{i}',
            'fullName': f"{execution.test_suite.name} / {result.get('name', f'请求 {i + 1}')}",
            'links': [],
            'labels': [
                {'name': 'suite', 'value': execution.test_suite.name},
                {'name': 'testClass', 'value': execution.test_suite.name},
                {'name': 'package', 'value': 'api_testing'},
                {'name': 'project', 'value': project_name},
            ],
            'parameters': [
                {'name': 'method', 'value': result.get('method', 'GET')},
                {'name': 'url', 'value': result.get('url', '')},
            ],
            'steps': [
                {
                    'name': '发送请求',
                    'status': 'passed',
                    'stage': 'finished',
                    'start': int(time.time() * 1000) - 1000,
                    'stop': int(time.time() * 1000) - 500,
                    'steps': [],
                },
                {
                    'name': '验证响应',
                    'status': 'passed' if result.get('passed', False) else 'failed',
                    'stage': 'finished',
                    'start': int(time.time() * 1000) - 500,
                    'stop': int(time.time() * 1000),
                    'steps': [],
                },
            ],
        }
        if result.get('error'):
            request_result['statusDetails'] = {'message': result.get('error'), 'trace': ''}
        path = os.path.join(report_dir, f'{execution.id}-{i}-result.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(request_result, f, ensure_ascii=False, indent=2)


def _run_allure(allure_cmd: Path, results_dir: str, report_output_dir: str) -> None:
    if os.name == 'nt':
        cmd = ['cmd', '/c', str(allure_cmd), 'generate', results_dir, '--clean', '--output', report_output_dir]
    else:
        cmd = [str(allure_cmd), 'generate', results_dir, '--clean', '--output', report_output_dir]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    logger.info('Allure 报告生成成功: %s', result.stdout)


@shared_task(bind=True, name='api_testing.generate_allure_report', ignore_result=True)
def generate_allure_report_task(self, execution_id: int) -> None:
    """异步生成 Allure 报告并把状态回写到 TestExecution。"""
    try:
        execution = TestExecution.objects.select_related('test_suite__project').get(pk=execution_id)
    except TestExecution.DoesNotExist:
        logger.warning('execution=%s 不存在，跳过报告生成', execution_id)
        return

    TestExecution.objects.filter(pk=execution_id).update(
        report_status='GENERATING',
        report_error='',
    )

    try:
        results_dir = os.path.join(
            settings.MEDIA_ROOT, 'api-testing', 'allure-results', f'execution_{execution.id}'
        )
        os.makedirs(results_dir, exist_ok=True)
        _generate_test_result_files(execution, results_dir)

        report_output_dir = os.path.join(
            settings.MEDIA_ROOT, 'api-testing', 'allure-reports', f'execution_{execution.id}'
        )
        os.makedirs(report_output_dir, exist_ok=True)

        java_available = _check_java_environment()
        allure_cmd = _resolve_allure_command()

        if allure_cmd and java_available:
            try:
                _force_clean(report_output_dir)
                _run_allure(allure_cmd, results_dir, report_output_dir)
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                detail = str(e)
                if hasattr(e, 'stderr') and e.stderr:
                    detail = f'{detail}\nStderr: {e.stderr}'
                logger.error('Allure 命令执行失败: %s', detail)
                TestExecution.objects.filter(pk=execution_id).update(
                    report_status='FAILED',
                    report_error=detail,
                )
                return
        else:
            logger.warning('Allure 工具或 Java 环境不可用，生成简单报告')
            os.makedirs(report_output_dir, exist_ok=True)
            with open(os.path.join(report_output_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(_allure_html.render_fallback_report(execution))

        # 写概览页
        summary_path = os.path.join(report_output_dir, 'summary.html')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(_allure_html.render_summary_report(execution, execution.results or []))

        TestExecution.objects.filter(pk=execution_id).update(
            report_status='READY',
            report_error='',
            report_generated_at=timezone.now(),
        )
        logger.info('execution=%s 报告生成完成', execution_id)

    except Exception as e:
        logger.error('生成 Allure 报告失败: %s\n%s', e, traceback.format_exc())
        TestExecution.objects.filter(pk=execution_id).update(
            report_status='FAILED',
            report_error=f'{e}',
        )
