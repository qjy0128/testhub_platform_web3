from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import dispatch_due_scheduled_jobs, get_scheduler_capabilities

# 单次手动 dispatch 一次最多触发的任务数。避免被打满 worker。
MAX_DISPATCH_LIMIT = 1000


class SchedulerCapabilitiesView(APIView):
    """读取调度后端能力。普通用户即可访问，仅返回静态描述。"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(get_scheduler_capabilities())


class SchedulerRunDueJobsView(APIView):
    """手动派发到期定时任务。

    全局影响：会跨所有用户的定时任务集合执行，因此仅管理员可调用。
    """

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        modules = request.data.get('modules')
        if isinstance(modules, str):
            modules = [module.strip() for module in modules.split(',') if module.strip()]
        elif modules is not None and not isinstance(modules, list):
            return Response(
                {'detail': 'modules must be a list or comma separated string.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 把 limit 强制限制在 [1, MAX_DISPATCH_LIMIT]，None 透传表示"使用底层默认"。
        raw_limit = request.data.get('limit')
        limit = None
        if raw_limit is not None:
            try:
                limit = max(1, min(int(raw_limit), MAX_DISPATCH_LIMIT))
            except (TypeError, ValueError):
                return Response(
                    {'detail': 'limit must be an integer.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            max_attempts = max(1, min(int(request.data.get('max_attempts', 3)), 10))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'max_attempts must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = dispatch_due_scheduled_jobs(
            modules=modules,
            limit=limit,
            max_attempts=max_attempts,
            dry_run=bool(request.data.get('dry_run', False)),
            async_queue=bool(request.data.get('async_queue', True)),
        )
        return Response(result)
