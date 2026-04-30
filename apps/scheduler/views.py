from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from .services import dispatch_due_scheduled_jobs, get_scheduler_capabilities


class SchedulerCapabilitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(get_scheduler_capabilities())


class SchedulerRunDueJobsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        modules = request.data.get('modules')
        if isinstance(modules, str):
            modules = [module.strip() for module in modules.split(',') if module.strip()]
        elif modules is not None and not isinstance(modules, list):
            return Response({'detail': 'modules must be a list or comma separated string.'}, status=status.HTTP_400_BAD_REQUEST)

        result = dispatch_due_scheduled_jobs(
            modules=modules,
            limit=request.data.get('limit'),
            max_attempts=request.data.get('max_attempts', 3),
            dry_run=bool(request.data.get('dry_run', False)),
            async_queue=bool(request.data.get('async_queue', True)),
        )
        return Response(result)
