"""测试用例文本解析与重建工具。

从 ``generation_tasks.py.TestCaseGenerationTaskViewSet`` 中抽出的纯函数，
全部不依赖类状态，便于单元测试与复用。

公开函数：
    parse_test_cases_content(content) -> list[dict]
    reconstruct_test_cases_content(test_cases) -> str
    map_priority(priority_str) -> str
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #

def parse_test_cases_content(content: str) -> list[dict[str, Any]]:
    """解析测试用例内容，自动识别表格 / 文本两种格式。"""
    if not content:
        return []

    # 去掉 markdown 加粗，保留纯文本
    clean_content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
    logger.info('开始解析测试用例内容，内容长度: %d', len(clean_content))
    logger.debug('内容前 200 字符: %s', clean_content[:200])

    if '|' in clean_content:
        return _parse_table_format(clean_content)
    return _parse_text_format(clean_content)


def _parse_table_format(content: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    table_data: list[list[str]] = []

    for line in lines:
        if '|' not in line or line.startswith('|-'):
            continue

        # 处理 \\| 转义：先替换为占位符，分隔后再还原
        placeholder = '___PIPE___'
        processed = line.replace(r'\|', placeholder)
        if processed.startswith('|'):
            processed = processed[1:]
        if processed.endswith('|'):
            processed = processed[:-1]

        cells = [
            cell.replace(placeholder, '|').replace('&#124;', '|').strip()
            for cell in processed.split('|')
        ]
        if len(cells) > 1:
            table_data.append(cells)

    if len(table_data) < 2:
        return []

    headers = [h.lower() for h in table_data[0]]
    test_cases: list[dict[str, Any]] = []

    for row in table_data[1:]:
        if len(row) < len(headers):
            continue

        case: dict[str, Any] = {}
        for i, header in enumerate(headers):
            value = row[i] if i < len(row) else ''
            if any(k in header for k in ['编号', 'id', '序号', '用例id']):
                case['caseId'] = value
            elif any(k in header for k in ['场景', '标题', '名称', 'title', 'scenario', '测试目标']):
                case['scenario'] = value
            elif any(k in header for k in ['前置', '前提', 'precondition']):
                case['precondition'] = value
            elif any(k in header for k in ['步骤', 'step', '测试步骤', '操作步骤']):
                case['steps'] = value
            elif any(k in header for k in ['预期', '结果', 'expected', 'result']):
                case['expected'] = value
            elif any(k in header for k in ['优先级', 'priority']):
                case['priority'] = value

        if case.get('scenario') or case.get('steps'):
            test_cases.append(case)

    return test_cases


def _parse_text_format(content: str) -> list[dict[str, Any]]:
    test_cases: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for raw in content.split('\n'):
        line = raw.strip()
        if not line:
            continue

        is_case_start = (
            '测试用例' in line
            or 'Test Case' in line
            or line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.'))
            or line.startswith(('一、', '二、', '三、', '四、', '五、'))
            or bool(re.match(r'^\d+[\.\)、]', line))
        )

        if is_case_start:
            if current:
                test_cases.append(current)
            scenario = line
            scenario = scenario.replace('测试用例', '').replace('Test Case', '')
            scenario = scenario.replace(':', '').replace('：', '')
            scenario = re.sub(r'^\d+[\.\)、]\s*', '', scenario)
            current = {'scenario': scenario.strip()}
        elif current:
            if any(k in line for k in ['前置条件', '前提条件', '前置', '前提']):
                current['precondition'] = _extract_field_value(line)
            elif any(k in line for k in ['测试步骤', '操作步骤', '执行步骤', '步骤']):
                current['steps'] = _extract_field_value(line)
            elif any(k in line for k in ['预期结果', '期望结果', '预期']):
                current['expected'] = _extract_field_value(line)
            elif '优先级' in line:
                current['priority'] = _extract_field_value(line)

    if current:
        test_cases.append(current)
    logger.info('解析完成，共解析出 %d 个测试用例', len(test_cases))
    return test_cases


def _extract_field_value(line: str) -> str:
    for sep in [':', '：', '】', '】:', '】：']:
        if sep in line:
            return line.split(sep, 1)[-1].strip()
    for prefix in ['前置条件', '测试步骤', '操作步骤', '预期结果', '优先级']:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return line.strip()


# --------------------------------------------------------------------------- #
# 重建
# --------------------------------------------------------------------------- #

def reconstruct_test_cases_content(test_cases: list[dict[str, Any]]) -> str:
    if not test_cases:
        return ''
    has_case_ids = any(c.get('caseId') for c in test_cases)
    if has_case_ids:
        return _reconstruct_table_format(test_cases)
    return _reconstruct_text_format(test_cases)


def _reconstruct_table_format(test_cases: list[dict[str, Any]]) -> str:
    out: list[str] = ['```markdown']

    has_steps = any(
        c.get('steps') and c.get('steps') != '参考测试目标执行相应操作' for c in test_cases
    )

    if has_steps:
        out.append('| 用例ID | 测试目标 | 前置条件 | 测试步骤 | 预期结果 | 优先级 | 测试类型 | 关联需求 |')
        out.append('|--------|--------|--------|--------|--------|--------|--------|--------|')
        for c in test_cases:
            precondition = (c.get('precondition') or '').replace('\n', '<br>')
            steps = (c.get('steps') or '参考测试目标执行相应操作').replace('\n', '<br>')
            expected = (c.get('expected') or '').replace('\n', '<br>')
            out.append(
                f"| {c.get('caseId', '')} | {c.get('scenario', '')} | {precondition} | "
                f"{steps} | {expected} | {c.get('priority', 'P2')} | 功能验证 | 需求1 |"
            )
    else:
        out.append('| 用例ID | 测试目标 | 前置条件 | 预期结果 | 优先级 | 测试类型 | 关联需求 |')
        out.append('|--------|--------|--------|--------|--------|--------|--------|')
        for c in test_cases:
            precondition = (c.get('precondition') or '').replace('\n', '<br>')
            expected = (c.get('expected') or '').replace('\n', '<br>')
            out.append(
                f"| {c.get('caseId', '')} | {c.get('scenario', '')} | {precondition} | "
                f"{expected} | {c.get('priority', 'P2')} | 功能验证 | 需求1 |"
            )

    out.append('```')
    return '\n'.join(out)


def _reconstruct_text_format(test_cases: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for c in test_cases:
        scenario = c.get('scenario', '未命名测试用例')
        already_marked = (
            bool(re.match(r'^\d+[\.\)、]', scenario))
            or '测试用例' in scenario
            or 'Test Case' in scenario
        )
        if not already_marked:
            out.append(f'\n测试用例: {scenario}')
        else:
            out.append(f'\n{scenario}')
        if c.get('precondition'):
            out.append(f'前置条件: {c["precondition"]}')
        if c.get('steps'):
            out.append(f'测试步骤: {c["steps"]}')
        if c.get('expected'):
            out.append(f'预期结果: {c["expected"]}')
        if c.get('priority'):
            out.append(f'优先级: {c["priority"]}')
        out.append('')
    return '\n'.join(out)


# --------------------------------------------------------------------------- #
# 优先级映射
# --------------------------------------------------------------------------- #

_PRIORITY_MAP = {
    '最高': 'critical',
    '高': 'high',
    '中': 'medium',
    '低': 'low',
    'P0': 'critical',
    'P1': 'high',
    'P2': 'medium',
    'P3': 'low',
}


def map_priority(priority_str: str) -> str:
    return _PRIORITY_MAP.get(priority_str, 'medium')
