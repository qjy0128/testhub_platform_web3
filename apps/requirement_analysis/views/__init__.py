"""``requirement_analysis.views`` 包入口。

历史 ``views.py`` 共 3245 行，已按职责拆分：

- ``_common``           — 访问控制 helpers + ``PassThroughRenderer``
- ``text_analysis``     — ``upload_and_analyze`` + ``analyze_text``（已去重 / 修复不可达分支）
- ``documents``         — 文档 / 分析 / 业务需求 ViewSet
- ``generation``        — 测试用例 / 分析任务 ViewSet + 分页类
- ``ai_models``         — AI 模型 / Prompt / 生成配置 ViewSet
- ``generation_tasks``  — 测试用例生成任务 ViewSet（待进一步内部拆分）
- ``configs_status``    — 配置状态 schema + ViewSet

入口透出 ``urls.py`` 依赖的所有符号，保持向后兼容。
"""
from ._common import PassThroughRenderer  # noqa: F401

# 兼容历史 mock.patch 路径：原来这些符号 import 自 views.py 顶层。
from apps.projects.unified import (  # noqa: F401
    accessible_projects_for_user,
    user_can_access_project,
)
from apps.projects.models import Project  # noqa: F401
from .ai_models import AIModelConfigViewSet, GenerationConfigViewSet, PromptConfigViewSet  # noqa: F401
from .configs_status import ConfigStatusSchemaSerializer, ConfigStatusViewSet  # noqa: F401
from .documents import (  # noqa: F401
    BusinessRequirementViewSet,
    RequirementAnalysisViewSet,
    RequirementDocumentViewSet,
)
from .generation import (  # noqa: F401
    AnalysisTaskViewSet,
    GeneratedTestCasePagination,
    GeneratedTestCaseViewSet,
    TestCaseGenerationTaskPagination,
)
from .generation_tasks import TestCaseGenerationTaskViewSet  # noqa: F401
from .text_analysis import analyze_text, upload_and_analyze  # noqa: F401

__all__ = [
    'AIModelConfigViewSet',
    'AnalysisTaskViewSet',
    'BusinessRequirementViewSet',
    'ConfigStatusSchemaSerializer',
    'ConfigStatusViewSet',
    'GeneratedTestCasePagination',
    'GeneratedTestCaseViewSet',
    'GenerationConfigViewSet',
    'PassThroughRenderer',
    'PromptConfigViewSet',
    'RequirementAnalysisViewSet',
    'RequirementDocumentViewSet',
    'TestCaseGenerationTaskPagination',
    'TestCaseGenerationTaskViewSet',
    'analyze_text',
    'upload_and_analyze',
]
