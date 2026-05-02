"""单点 endpoints：上传文档/直接分析文本。

历史 ``views.py`` 同时存在两个 ``analyze_text`` 定义（后者覆盖前者），
本模块保留真正在用的"先进分析 + fallback"实现，删除不可达的 except 分支。
"""
import asyncio
import logging

from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.throttles import AIRateThrottle
from ..models import (
    BusinessRequirement,
    RequirementAnalysis,
    RequirementDocument,
)
from ..serializers import DocumentUploadSerializer
from ..services import AIService, DocumentProcessor
from ._common import resolve_accessible_project

logger = logging.getLogger(__name__)


def _build_fallback_analysis(title: str, description: str) -> dict:
    return {
        'analysis_report': (
            f'对需求"{title}"的分析已完成。\n\n'
            f'需求描述：{description[:200]}...\n\n'
            '基于描述内容识别到若干功能性需求。'
        ),
        'requirements_count': 2,
        'requirements': [
            {
                'requirement_id': 'REQ001',
                'requirement_name': f'{title} - 核心功能',
                'requirement_type': 'functional',
                'module': '核心模块',
                'requirement_level': 'high',
                'estimated_hours': 8,
                'description': description[:100] + '...',
                'acceptance_criteria': '功能正常运行，满足用户需求',
            },
            {
                'requirement_id': 'REQ002',
                'requirement_name': f'{title} - 交互功能',
                'requirement_type': 'usability',
                'module': '前端模块',
                'requirement_level': 'medium',
                'estimated_hours': 6,
                'description': '用户界面和交互相关需求',
                'acceptance_criteria': '界面友好，操作简单',
            },
        ],
    }


def _persist_analysis(document: RequirementDocument, result: dict, analysis_time: float):
    analysis = RequirementAnalysis.objects.create(
        document=document,
        analysis_report=result['analysis_report'],
        requirements_count=result['requirements_count'],
        analysis_time=analysis_time,
    )
    for req_data in result['requirements']:
        BusinessRequirement.objects.create(analysis=analysis, **req_data)
    document.status = 'analyzed'
    document.save()
    return analysis


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def upload_and_analyze(request):
    """上传文档并立即开始分析"""
    try:
        serializer = DocumentUploadSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        document: RequirementDocument = serializer.save()
        document.status = 'analyzing'
        document.save()

        try:
            if not document.extracted_text:
                document.extracted_text = DocumentProcessor.extract_text(document)
                document.save()

            # 旧版：使用一个本地构造的"模拟"结果保持行为不变。
            # 长期目标是直接走 AIService，与 ``analyze_text`` 同源。
            analysis_result = _build_fallback_analysis(document.title, document.extracted_text or '')
            analysis = _persist_analysis(document, analysis_result, analysis_time=2.5)
        except Exception as e:
            logger.error(f"分析失败: {e}")
            document.status = 'failed'
            document.save()
            raise

        return Response({
            'message': '上传并分析完成',
            'document_id': document.id,
            'analysis_id': analysis.id,
            'requirements_count': analysis.requirements_count,
        })
    except Exception as e:
        logger.error(f"上传并分析失败: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def analyze_text(request):
    """分析手动输入的需求文本。优先调用 AIService，失败时回退到本地模板。"""
    try:
        title = request.data.get('title')
        description = request.data.get('description')
        project_id = request.data.get('project')

        if not title or not description:
            return Response(
                {'error': '需求标题和描述不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = resolve_accessible_project(request.user, project_id)
        if project_id and project is None:
            return Response(
                {'error': 'Project is not accessible.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        document = RequirementDocument.objects.create(
            title=title,
            file=None,
            document_type='txt',
            status='analyzing',
            uploaded_by=request.user,
            project=project,
            extracted_text=description,
        )

        try:
            logger.info(f"开始使用先进分析器分析需求: {title}")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                analysis_result = loop.run_until_complete(
                    AIService.analyze_requirements(description, title)
                )
            finally:
                loop.close()
            logger.info(f"先进分析完成，识别需求: {analysis_result.get('requirements_count', 0)}个")
            analysis = _persist_analysis(
                document,
                analysis_result,
                analysis_time=analysis_result.get('analysis_time', 2.0),
            )
        except Exception as e:
            logger.error(f"先进分析失败: {e}，使用备用分析")
            try:
                fallback = _build_fallback_analysis(title, description)
                analysis = _persist_analysis(document, fallback, analysis_time=1.5)
            except Exception as inner:
                logger.error(f"备用分析也失败: {inner}")
                document.status = 'failed'
                document.save()
                raise

        return Response({
            'message': '文本分析完成',
            'document_id': document.id,
            'analysis_id': analysis.id,
            'requirements_count': analysis.requirements_count,
        })

    except Exception as e:
        logger.error(f"文本分析失败: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
