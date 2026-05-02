"""``TestCaseGenerationTaskViewSet.generate`` 的方法体。

从 ``generation_tasks.py`` 抽出，签名调整为 ``handle_generate(view, request)``，
``view`` 是 ViewSet 实例，复用其权限过滤后的 queryset / get_object 等接口。
"""
from __future__ import annotations

import asyncio
import logging
import threading

from asgiref.sync import sync_to_async
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.projects.unified import user_can_access_project
from ..models import (
    AIModelConfig,
    AIModelService,
    PromptConfig,
    TestCaseGenerationTask,
)
from ..serializers import (
    TestCaseGenerationRequestSerializer,
    TestCaseGenerationTaskSerializer,
)

logger = logging.getLogger(__name__)


def handle_generate(view, request):
    """实现 ``POST /api/requirement-analysis/testcase-generation/generate/``。"""
    """创建新的测试用例生成任务"""
    try:
        serializer = TestCaseGenerationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        project = validated_data.get('project')
        if project and not user_can_access_project(request.user, project):
            return Response(
                {'error': '无权访问该项目'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 获取活跃的配置
        writer_config = None
        reviewer_config = None
        writer_prompt = None
        reviewer_prompt = None

        if validated_data.get('use_writer_model', True):
            # 优先查找任意启用的编写模型配置
            writer_config = AIModelConfig.objects.filter(role='writer', is_active=True).first()

            if not writer_config:
                return Response(
                    {'error': '未找到可用的测试用例编写模型配置'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            writer_prompt = PromptConfig.get_active_config('writer')
            if not writer_prompt:
                return Response(
                    {'error': '未找到可用的测试用例编写提示词配置'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if validated_data.get('use_reviewer_model', True):
            # 优先查找任意启用的评审模型配置
            reviewer_config = AIModelConfig.objects.filter(role='reviewer', is_active=True).first()

            if not reviewer_config:
                return Response(
                    {'error': '未找到可用的测试用例评审模型配置'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            reviewer_prompt = PromptConfig.get_active_config('reviewer')
            if not reviewer_prompt:
                return Response(
                    {'error': '未找到可用的测试用例评审提示词配置'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 创建任务
        task_data = {
            'title': validated_data['title'],
            'requirement_text': validated_data['requirement_text'],
            'writer_model_config': writer_config.id if writer_config else None,
            'reviewer_model_config': reviewer_config.id if reviewer_config else None,
            'writer_prompt_config': writer_prompt.id if writer_prompt else None,
            'reviewer_prompt_config': reviewer_prompt.id if reviewer_prompt else None,
        }

        # 如果请求中包含项目ID，添加到任务数据中
        if project:
            task_data['project'] = project.id

        # 处理输出模式：优先使用用户指定的，否则使用生成行为配置的默认值
        output_mode = request.data.get('output_mode')
        if output_mode and output_mode in ['stream', 'complete']:
            task_data['output_mode'] = output_mode
        else:
            # 从生成行为配置中读取默认值
            from ..models import GenerationConfig
            gen_config = GenerationConfig.get_active_config()
            if gen_config:
                task_data['output_mode'] = gen_config.default_output_mode
            else:
                # 如果没有配置，默认使用流式输出
                task_data['output_mode'] = 'stream'

        task_serializer = TestCaseGenerationTaskSerializer(
            data=task_data,
            context={'request': request}
        )

        if task_serializer.is_valid():
            task = task_serializer.save()

            # 派发到 Celery；失败时回退到旧的"线程内 asyncio loop"模式，
            # 这样 broker 不可达时仍能完成生成（行为与历史一致）。
            from ..tasks import execute_generation_task
            try:
                execute_generation_task.delay(task.task_id)
            except Exception as exc:
                logger.warning('Celery 派发失败，回退到本地线程: %s', exc)
                _run_generation_in_thread_fallback(task)

            return Response({
                'message': '测试用例生成任务已创建',
                'task_id': task.task_id,
                'task': task_serializer.data,
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(task_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f"创建生成任务时出错: {e}")
        return Response(
            {'error': f'创建任务失败: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )



def _run_generation_in_thread_fallback(task) -> None:
    """Celery broker 不可达时的最终回退：直接在子线程里执行 Celery task 的同步函数体。

    任务状态字段仍由 ``execute_generation_task`` 内部更新，行为完全一致。
    """
    import threading

    from ..tasks import execute_generation_task

    def _runner():
        try:
            # 直接调用 task 函数（绕过 .delay）。第一个参数是 self（celery.Task），
            # 在 fallback 路径下没有意义，传 None 即可，因为函数体不读它。
            execute_generation_task.run(task.task_id)
        except Exception as exc:
            logger.error('线程回退执行生成任务失败: %s', exc)
            try:
                task.status = 'failed'
                task.error_message = str(exc)
                task.save(update_fields=['status', 'error_message'])
            except Exception:
                logger.warning('回退路径写入失败状态也失败了，跳过')

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
