"""自 ``views/_main.py`` 拆出。

当前阶段保留与 ``_main.py`` 相同的整段 import 块以避免迁移过程中遗漏；
pre-commit 的 ruff/isort 会在每次提交时自动收敛 unused import。
"""
import asyncio
import logging
import re
import os  # Added import
import json
import time
from rest_framework import serializers, viewsets, status
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django.conf import settings  # Added import
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from asgiref.sync import sync_to_async
from django.db import models

from apps.projects.unified import accessible_projects_for_user, user_can_access_project
from apps.projects.models import Project
from ..models import (
    RequirementDocument, RequirementAnalysis, BusinessRequirement,
    GeneratedTestCase, AnalysisTask, AIModelConfig, PromptConfig, TestCaseGenerationTask,
    GenerationConfig, AIModelService
)
from ..serializers import (
    RequirementDocumentSerializer, RequirementAnalysisSerializer,
    BusinessRequirementSerializer, GeneratedTestCaseSerializer,
    AnalysisTaskSerializer, DocumentUploadSerializer,
    TestCaseGenerationRequestSerializer, TestCaseReviewRequestSerializer,
    AIModelConfigSerializer, PromptConfigSerializer, TestCaseGenerationTaskSerializer,
    GenerationConfigSerializer
)
from ..services import RequirementAnalysisService, DocumentProcessor
from ._common import (
    PassThroughRenderer,
    is_staff_user as _is_staff_user,
    accessible_requirement_documents_for_user as _accessible_requirement_documents_for_user,
    resolve_accessible_project as _resolve_accessible_project,
)

logger = logging.getLogger(__name__)

class AIModelConfigViewSet(viewsets.ModelViewSet):
    """AI模型配置视图集"""
    queryset = AIModelConfig.objects.all()
    serializer_class = AIModelConfigSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = super().get_queryset()

        # 按模型类型过滤
        model_type = self.request.query_params.get('model_type')
        if model_type:
            queryset = queryset.filter(model_type=model_type)

        # 按角色过滤
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        else:
            # 如果没有指定角色，默认排除 AI智能模式专用模型
            queryset = queryset.exclude(role__in=['browser_use_text', 'browser_use_vision'])

        # 按是否启用过滤
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试模型连接"""
        try:
            config = self.get_object()

            logger.info(f"=== 开始测试模型连接 ===")
            logger.info(f"模型类型: {config.model_type}")
            logger.info(f"模型名称: {config.model_name}")
            logger.info(f"API URL: {config.base_url}")
            logger.info("API Key configured: %s", bool(config.api_key))

            # 准备测试消息
            test_messages = [
                {"role": "system", "content": "你是一个AI助手"},
                {"role": "user", "content": "请回复'连接成功'"}
            ]

            # 异步测试连接 - 统一使用OpenAI兼容API
            def test_api_connection():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:
                        logger.info("开始调用API...")
                        # 设置60秒超时，统一使用OpenAI兼容API
                        result = loop.run_until_complete(
                            asyncio.wait_for(
                                AIModelService.call_openai_compatible_api(config, test_messages),
                                timeout=60.0
                            )
                        )

                        logger.info(f"API调用成功: {result}")
                        return {
                            'success': True,
                            'message': '连接测试成功',
                            'response': result.get('choices', [{}])[0].get('message', {}).get('content', '')
                        }
                    except asyncio.TimeoutError:
                        logger.error(f"API连接测试超时 (60秒), URL: {config.base_url}, Model: {config.model_name}")
                        return {
                            'success': False,
                            'message': '连接测试超时: 请检查网络连接或API地址是否正确'
                        }
                    finally:
                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except Exception:
                            pass
                        finally:
                            loop.close()

                except Exception as e:
                    logger.error(f"API连接测试异常: {repr(e)}, URL: {config.base_url}, Model: {config.model_name}")
                    import traceback
                    logger.error(f"详细错误堆栈:\n{traceback.format_exc()}")
                    return {
                        'success': False,
                        'message': f'连接测试失败: {str(e)}'
                    }

            result = test_api_connection()

            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"测试连接时出错: {e}")
            return Response(
                {'success': False, 'message': f'测试失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        """启用配置"""
        try:
            config = self.get_object()
            config.is_active = True
            config.save()
            return Response({
                'message': 'AI模型配置已启用',
                'id': config.id,
                'is_active': True
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"启用AI模型配置失败: {e}")
            return Response({
                'error': f'启用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        """禁用配置"""
        try:
            config = self.get_object()
            config.is_active = False
            config.save()
            return Response({
                'message': 'AI模型配置已禁用',
                'id': config.id,
                'is_active': False
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"禁用AI模型配置失败: {e}")
            return Response({
                'error': f'禁用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PromptConfigViewSet(viewsets.ModelViewSet):
    """提示词配置视图集"""
    queryset = PromptConfig.objects.all()
    serializer_class = PromptConfigSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = super().get_queryset()

        # 按提示词类型过滤
        prompt_type = self.request.query_params.get('prompt_type')
        if prompt_type:
            queryset = queryset.filter(prompt_type=prompt_type)

        # 按是否启用过滤
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'])
    def load_defaults(self, request):
        """加载默认提示词"""
        try:
            # 读取用例编写提示词
            writer_prompt_path = os.path.join(settings.BASE_DIR, 'docs/tester.md')
            # 读取用例评审提示词
            reviewer_prompt_path = os.path.join(settings.BASE_DIR, 'docs/tester_pro.md')

            defaults = {}

            try:
                with open(writer_prompt_path, 'r', encoding='utf-8') as f:
                    defaults['writer'] = f.read()
            except FileNotFoundError:
                defaults['writer'] = """你是一位拥有10年经验的资深测试用例编写专家，能够根据需求精确生成高质量的测试用例。

# 核心目标
生成高覆盖率、颗粒度细致的测试用例，确保不遗漏任何功能逻辑、异常场景和边界条件。

# 角色设定
1. 身份：精通全栈测试（Web/App/API）的高级QA专家
2. 测试风格：破坏性测试思维，善于发现潜在Bug
3. 输出原则：详细、独立、可执行

# 用例设计规范
1. **独立性**：每条用例只验证一个具体的测试点，严禁合并多个场景。
2. **完整性**：
   - 包含用例ID（[模块]_[序号]）
   - 清晰的测试目标
   - 准确的前置条件
   - 步骤化操作描述
   - 具体的预期结果
3. **覆盖维度**：
   - ✅ 功能正向流程（Happy Path）
   - ⚠️ 异常流程（输入错误、权限不足、网络异常）
   - 🔄 边界值（最大/最小值、空值、特殊字符）
   - 🔒 业务约束（状态机流转、数据依赖）

# 输出格式
请严格按照以下Markdown表格格式输出，不要包含任何开场白或结束语：

## ⚠️ 重要：输出顺序要求
1. **必须按用例编号从小到大的顺序输出**（如：001, 002, 003...）
2. **绝对不能跳号、重复或乱序输出**
3. 编号必须连续，中间不能有遗漏
4. 所有用例必须一次性完整输出，不能中断

```markdown
| 用例ID | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 | 测试类型 | 关联需求 |
|--------|--------|--------|--------|--------|--------|--------|--------|
| LOGIN_001 | 验证手机号格式校验 | 在登录页 | 1. 输入10位手机号<br>2. 点击获取验证码 | 提示"手机号格式不正确"，发送按钮不可点 | P1 | 功能验证 | 登录模块 |
```"""

            try:
                with open(reviewer_prompt_path, 'r', encoding='utf-8') as f:
                    defaults['reviewer'] = f.read()
            except FileNotFoundError:
                defaults['reviewer'] = """你是一名资深测试专家（Test Architect），拥有极高的质量标准。你的任务是对生成的测试用例进行严格的评审。

# 核心职责
不只是简单通过，而是要作为“质量守门员”，敏锐地发现遗漏的场景、逻辑漏洞和描述不清的问题。

# 评审维度
1. **覆盖率检查**：
   - 是否遗漏了需求文档中的关键功能点？
   - 是否包含了必要的异常场景（如断网、服务超时、数据错误）？
   - 是否覆盖了边界条件（如最大长度、空值、特殊字符）？
2. **逻辑性检查**：
   - 前置条件是否充分？（例如测试“支付功能”前是否检查了“余额充足”）
   - 预期结果是否具体？（拒绝模糊的“显示正确”，必须说明具体提示文案或状态变化）
3. **规范性检查**：
   - 用例标题是否清晰表达了测试意图？
   - 步骤是否可执行？

# 输出要求
请输出一份结构化的评审报告：
1. **总体评价**：给出一个质量评分（0-100分）和总体结论（通过/需修改）。
2. **发现的问题**：列出具体的问题点，精确到具体的用例ID。
3. **补充建议**：直接给出建议补充的测试场景或用例。
4. **修正后的用例**（可选）：如果发现严重问题，请直接提供修正后的用例版本。"""

            return Response({
                'message': '默认提示词加载成功',
                'defaults': defaults
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"加载默认提示词失败: {e}")
            return Response(
                {'error': f'加载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        """启用配置"""
        try:
            config = self.get_object()
            config.is_active = True
            config.save()
            return Response({
                'message': '提示词配置已启用',
                'id': config.id,
                'is_active': True
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"启用提示词配置失败: {e}")
            return Response({
                'error': f'启用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        """禁用配置"""
        try:
            config = self.get_object()
            config.is_active = False
            config.save()
            return Response({
                'message': '提示词配置已禁用',
                'id': config.id,
                'is_active': False
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"禁用提示词配置失败: {e}")
            return Response({
                'error': f'禁用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GenerationConfigViewSet(viewsets.ModelViewSet):
    """生成行为配置视图集"""
    queryset = GenerationConfig.objects.all()
    serializer_class = GenerationConfigSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'])
    def active(self, request):
        """获取活跃的生成配置"""
        try:
            config = GenerationConfig.get_active_config()
            if not config:
                return Response({
                    'error': '未找到活跃的生成配置，请先创建并启用一个配置'
                }, status=status.HTTP_404_NOT_FOUND)

            serializer = self.get_serializer(config)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"获取活跃生成配置失败: {e}")
            return Response({
                'error': f'获取失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        """启用配置"""
        try:
            # 禁用其他所有配置
            GenerationConfig.objects.all().update(is_active=False)

            # 启用当前配置
            config = self.get_object()
            config.is_active = True
            config.save()

            return Response({
                'message': '生成配置已启用',
                'id': config.id,
                'is_active': True
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"启用生成配置失败: {e}")
            return Response({
                'error': f'启用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        """禁用配置"""
        try:
            config = self.get_object()
            config.is_active = False
            config.save()

            return Response({
                'message': '生成配置已禁用',
                'id': config.id,
                'is_active': False
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"禁用生成配置失败: {e}")
            return Response({
                'error': f'禁用失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

