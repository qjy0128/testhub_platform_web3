from django.db import models
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.audit import record_unified_audit
from apps.core.models import UnifiedAuditLog
from apps.projects.unified import accessible_projects_for_user, user_can_manage_project

from .models import OcrBatch, OcrEngineConfig, OcrPage, OcrTask
from .serializers import OcrBatchSerializer, OcrEngineConfigSerializer, OcrPageSerializer, OcrTaskSerializer
from .services import (
    check_ocr_engine,
    infer_source_type,
    refresh_ocr_batch_status,
    run_ocr_task,
    run_pending_ocr_tasks,
    validate_upload_file,
)


def _can_manage_ocr_task(user, task):
    if getattr(task, 'created_by_id', None) == getattr(user, 'id', None):
        return True
    if task.project_id and user_can_manage_project(user, task.project):
        return True
    return False


def _get_engine_for_request(user, engine_id=None):
    queryset = OcrEngineConfig.objects.filter(is_active=True)
    if not user.is_staff:
        queryset = queryset.filter(created_by=user)
    if engine_id:
        return queryset.filter(pk=engine_id).first()
    return queryset.filter(is_default=True).first()


class OcrEngineConfigViewSet(viewsets.ModelViewSet):
    serializer_class = OcrEngineConfigSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['engine_type', 'is_default', 'is_active']
    search_fields = ['name', 'model_name']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-is_default', '-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return OcrEngineConfig.objects.none()
        queryset = OcrEngineConfig.objects.select_related('created_by').annotate(
            task_count=Count('tasks', distinct=True),
        )
        if user.is_staff:
            return queryset
        return queryset.filter(created_by=user)

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        if instance.is_default:
            self._clear_other_defaults(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.is_default:
            self._clear_other_defaults(instance)

    def _clear_other_defaults(self, instance):
        OcrEngineConfig.objects.filter(
            created_by=instance.created_by,
            is_default=True,
        ).exclude(pk=instance.pk).update(is_default=False)

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        instance = self.get_object()
        instance.is_default = True
        instance.is_active = True
        instance.save(update_fields=['is_default', 'is_active', 'updated_at'])
        self._clear_other_defaults(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'])
    def preflight(self, request, pk=None):
        instance = self.get_object()
        return Response(check_ocr_engine(instance))


class OcrTaskViewSet(viewsets.ModelViewSet):
    serializer_class = OcrTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'batch', 'engine', 'status', 'source_type']
    search_fields = ['name', 'original_filename', 'input_url', 'extracted_text']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return OcrTask.objects.none()
        queryset = OcrTask.objects.select_related('project', 'batch', 'engine', 'created_by').annotate(
            page_count=Count('pages', distinct=True),
        )
        if user.is_staff:
            return queryset
        accessible_projects = accessible_projects_for_user(user)
        return queryset.filter(
            models.Q(project__in=accessible_projects) | models.Q(project__isnull=True, created_by=user)
        ).distinct()

    def perform_create(self, serializer):
        engine = serializer.validated_data.get('engine')
        if engine is None:
            engine = OcrEngineConfig.objects.filter(
                created_by=self.request.user,
                is_default=True,
                is_active=True,
            ).first()
        task = serializer.save(created_by=self.request.user, engine=engine)
        self._record_task_audit(task, 'Created OCR task.', operation='create')

    def perform_update(self, serializer):
        if not _can_manage_ocr_task(self.request.user, self.get_object()):
            raise PermissionDenied('No permission to manage this OCR task.')
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_manage_ocr_task(self.request.user, instance):
            raise PermissionDenied('No permission to manage this OCR task.')
        instance.delete()

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        task = self.get_object()
        if not _can_manage_ocr_task(request.user, task):
            raise PermissionDenied('No permission to manage this OCR task.')
        task.status = OcrTask.STATUS_PENDING
        task.error_message = ''
        task.save(update_fields=['status', 'error_message', 'updated_at'])
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        task = self.get_object()
        if not _can_manage_ocr_task(request.user, task):
            raise PermissionDenied('No permission to manage this OCR task.')
        if task.status == OcrTask.STATUS_CANCELLED:
            return Response({'detail': 'Cancelled tasks cannot be run.'}, status=status.HTTP_400_BAD_REQUEST)
        run_ocr_task(task)
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        task = self.get_object()
        if not _can_manage_ocr_task(request.user, task):
            raise PermissionDenied('No permission to manage this OCR task.')
        if task.status in {OcrTask.STATUS_SUCCEEDED, OcrTask.STATUS_FAILED, OcrTask.STATUS_CANCELLED}:
            return Response({'detail': 'Task is already finished.'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = OcrTask.STATUS_CANCELLED
        task.save(update_fields=['status', 'updated_at'])
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def pages(self, request, pk=None):
        task = self.get_object()
        pages = task.pages.order_by('page_number')
        serializer = OcrPageSerializer(pages, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='revise-page')
    def revise_page(self, request, pk=None):
        task = self.get_object()
        if not _can_manage_ocr_task(request.user, task):
            raise PermissionDenied('No permission to manage this OCR task.')

        text = request.data.get('text')
        if not isinstance(text, str):
            return Response({'detail': 'text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        page_id = request.data.get('page_id')
        page_number = request.data.get('page_number')
        pages = task.pages.all()
        if page_id:
            page = pages.filter(pk=page_id).first()
        elif page_number:
            page = pages.filter(page_number=page_number).first()
        else:
            page = None
        if page is None:
            return Response({'detail': 'OCR page not found.'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        metadata = dict(page.metadata or {})
        if 'original_text' not in metadata:
            metadata['original_text'] = page.text or ''
        revisions = metadata.get('revisions')
        if not isinstance(revisions, list):
            revisions = []
        revisions.append({
            'previous_text': page.text or '',
            'text': text,
            'created_by': request.user.id,
            'created_by_name': getattr(request.user, 'username', '') or '',
            'created_at': now.isoformat(),
        })
        metadata['revisions'] = revisions
        metadata['review_state'] = 'revised'
        metadata['revised_at'] = now.isoformat()
        metadata['revised_by'] = request.user.id

        page.text = text
        page.metadata = metadata
        page.save(update_fields=['text', 'metadata'])

        result_json = dict(task.result_json or {})
        if 'original_extracted_text' not in result_json:
            result_json['original_extracted_text'] = task.extracted_text or ''
        history = result_json.get('revision_history')
        if not isinstance(history, list):
            history = []
        history.append({
            'page_id': page.id,
            'page_number': page.page_number,
            'created_by': request.user.id,
            'created_by_name': getattr(request.user, 'username', '') or '',
            'created_at': now.isoformat(),
        })
        result_json['revision_history'] = history
        result_json['review_state'] = 'revised'

        ordered_pages = task.pages.order_by('page_number')
        task.extracted_text = '\n\n'.join(page_item.text or '' for page_item in ordered_pages).strip()
        task.result_json = result_json
        task.save(update_fields=['extracted_text', 'result_json', 'updated_at'])

        record_unified_audit(
            domain='ocr_service',
            action=UnifiedAuditLog.ACTION_UPDATE,
            object_type='ocr_page',
            object_id=page.id,
            object_name=f'{task.name} / page {page.page_number}',
            project_id=task.project_id,
            project_name=task.project.name if task.project_id else '',
            actor=request.user,
            summary='Revised OCR page text.',
            metadata={
                'operation': 'revise_page',
                'ocr_task_id': task.id,
                'page_number': page.page_number,
            },
        )

        task_serializer = self.get_serializer(task)
        page_serializer = OcrPageSerializer(page, context={'request': request})
        return Response({'task': task_serializer.data, 'page': page_serializer.data})

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        uploaded_file = request.FILES.get('file')
        if uploaded_file is None:
            return Response({'detail': 'No file was uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        uploaded_file.name = uploaded_file.name.split('\\')[-1].split('/')[-1]

        try:
            validate_upload_file(uploaded_file)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        project = None
        project_id = request.data.get('project')
        if project_id:
            project = accessible_projects_for_user(request.user).filter(pk=project_id).first()
            if project is None:
                return Response({'detail': 'Project is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        engine = _get_engine_for_request(request.user, request.data.get('engine'))
        if request.data.get('engine') and engine is None:
            return Response({'detail': 'OCR engine is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        task = OcrTask.objects.create(
            project=project,
            batch=None,
            engine=engine,
            name=request.data.get('name') or uploaded_file.name,
            source_type=infer_source_type(uploaded_file.name, getattr(uploaded_file, 'content_type', '') or ''),
            input_file=uploaded_file,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            mime_type=getattr(uploaded_file, 'content_type', '') or '',
            priority=int(request.data.get('priority') or 100),
            max_attempts=max(1, min(int(request.data.get('max_attempts') or 1), 5)),
            created_by=request.user,
        )
        serializer = self.get_serializer(task)
        self._record_task_audit(task, 'Uploaded OCR task file.', operation='upload')
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def batch(self, request):
        items = request.data.get('items')
        if not isinstance(items, list) or not items:
            return Response({'detail': 'items must be a non-empty list.'}, status=status.HTTP_400_BAD_REQUEST)

        project = None
        project_id = request.data.get('project')
        if project_id:
            project = accessible_projects_for_user(request.user).filter(pk=project_id).first()
            if project is None:
                return Response({'detail': 'Project is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        engine = _get_engine_for_request(request.user, request.data.get('engine'))
        if request.data.get('engine') and engine is None:
            return Response({'detail': 'OCR engine is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        batch = OcrBatch.objects.create(
            project=project,
            engine=engine,
            name=request.data.get('name') or 'OCR batch',
            metadata=request.data.get('metadata') if isinstance(request.data.get('metadata'), dict) else {},
            created_by=request.user,
        )

        created_tasks = []
        max_attempts = max(1, min(int(request.data.get('max_attempts') or 1), 5))
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            source_type = item.get('source_type') or OcrTask.SOURCE_TEXT
            task = OcrTask.objects.create(
                project=project,
                batch=batch,
                engine=engine,
                name=item.get('name') or f'{batch.name} #{index}',
                source_type=source_type,
                input_url=item.get('input_url', ''),
                input_text=item.get('input_text', ''),
                priority=int(item.get('priority') or request.data.get('priority') or 100),
                max_attempts=max(1, min(int(item.get('max_attempts') or max_attempts), 5)),
                created_by=request.user,
            )
            created_tasks.append(task)

        refresh_ocr_batch_status(batch)
        if str(request.data.get('run_immediately', '')).lower() in {'1', 'true', 'yes'}:
            for task in created_tasks:
                run_ocr_task(task)
            batch.refresh_from_db()

        self._record_batch_audit(batch, 'Created OCR text batch.', created_tasks, operation='batch_text')
        return Response(
            {
                'batch': OcrBatchSerializer(batch, context={'request': request}).data,
                'task_ids': [task.id for task in created_tasks],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def batch_upload(self, request):
        uploaded_files = request.FILES.getlist('files') or request.FILES.getlist('file')
        if not uploaded_files:
            return Response({'detail': 'No files were uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        project = None
        project_id = request.data.get('project')
        if project_id:
            project = accessible_projects_for_user(request.user).filter(pk=project_id).first()
            if project is None:
                return Response({'detail': 'Project is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        engine = _get_engine_for_request(request.user, request.data.get('engine'))
        if request.data.get('engine') and engine is None:
            return Response({'detail': 'OCR engine is not accessible.'}, status=status.HTTP_400_BAD_REQUEST)

        max_attempts = max(1, min(int(request.data.get('max_attempts') or 1), 5))
        batch = OcrBatch.objects.create(
            project=project,
            engine=engine,
            name=request.data.get('name') or 'OCR file batch',
            metadata={'source': 'file_upload', 'file_count': len(uploaded_files)},
            created_by=request.user,
        )

        created_tasks = []
        for index, uploaded_file in enumerate(uploaded_files, start=1):
            uploaded_file.name = uploaded_file.name.split('\\')[-1].split('/')[-1]
            try:
                validate_upload_file(uploaded_file)
            except ValueError as exc:
                batch.delete()
                return Response(
                    {'detail': f'{uploaded_file.name}: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            task = OcrTask.objects.create(
                project=project,
                batch=batch,
                engine=engine,
                name=request.data.get(f'name_{index}') or uploaded_file.name,
                source_type=infer_source_type(uploaded_file.name, getattr(uploaded_file, 'content_type', '') or ''),
                input_file=uploaded_file,
                original_filename=uploaded_file.name,
                file_size=uploaded_file.size,
                mime_type=getattr(uploaded_file, 'content_type', '') or '',
                priority=int(request.data.get('priority') or 100),
                max_attempts=max_attempts,
                created_by=request.user,
            )
            created_tasks.append(task)

        refresh_ocr_batch_status(batch)
        if str(request.data.get('run_immediately', '')).lower() in {'1', 'true', 'yes'}:
            for task in created_tasks:
                run_ocr_task(task)
            batch.refresh_from_db()

        self._record_batch_audit(batch, 'Uploaded OCR file batch.', created_tasks, operation='batch_upload')
        return Response(
            {
                'batch': OcrBatchSerializer(batch, context={'request': request}).data,
                'task_ids': [task.id for task in created_tasks],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'])
    def run_pending(self, request):
        limit = request.data.get('limit') or request.query_params.get('limit')
        try:
            limit = int(limit) if limit else None
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid limit.'}, status=status.HTTP_400_BAD_REQUEST)
        result = run_pending_ocr_tasks(limit=limit, queryset=self.get_queryset())
        record_unified_audit(
            domain='ocr_service',
            action=UnifiedAuditLog.ACTION_RUN,
            object_type='ocr_queue',
            actor=request.user,
            summary='Ran pending OCR task queue.',
            metadata={
                'operation': 'run_pending',
                'limit': limit,
                **result,
            },
        )
        return Response(result)

    def _record_task_audit(self, task, summary, *, operation):
        record_unified_audit(
            domain='ocr_service',
            action=UnifiedAuditLog.ACTION_CREATE,
            object_type='ocr_task',
            object_id=task.id,
            object_name=task.name,
            project_id=task.project_id,
            project_name=task.project.name if task.project_id else '',
            actor=self.request.user,
            summary=summary,
            metadata={
                'operation': operation,
                'source_type': task.source_type,
                'engine_id': task.engine_id,
                'batch_id': task.batch_id,
                'file_name': task.original_filename,
                'file_size': task.file_size,
            },
        )

    def _record_batch_audit(self, batch, summary, tasks, *, operation):
        record_unified_audit(
            domain='ocr_service',
            action=UnifiedAuditLog.ACTION_CREATE,
            object_type='ocr_batch',
            object_id=batch.id,
            object_name=batch.name,
            project_id=batch.project_id,
            project_name=batch.project.name if batch.project_id else '',
            actor=self.request.user,
            summary=summary or 'Created OCR batch.',
            metadata={
                'operation': operation,
                'engine_id': batch.engine_id,
                'task_count': len(tasks),
                'task_ids': [task.id for task in tasks],
                'run_immediately': any(task.status != OcrTask.STATUS_PENDING for task in tasks),
            },
        )


class OcrServiceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_ocr_service_summary_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        user = request.user
        tasks = OcrTask.objects.all()
        batches = OcrBatch.objects.all()
        engines = OcrEngineConfig.objects.all()
        if not user.is_staff:
            accessible_projects = accessible_projects_for_user(user)
            tasks = tasks.filter(
                models.Q(project__in=accessible_projects) | models.Q(project__isnull=True, created_by=user)
            ).distinct()
            batches = batches.filter(
                models.Q(project__in=accessible_projects) | models.Q(project__isnull=True, created_by=user)
            ).distinct()
            engines = engines.filter(created_by=user)

        return Response({
            'engines': engines.count(),
            'active_engines': engines.filter(is_active=True).count(),
            'batches': batches.count(),
            'running_batches': batches.filter(status=OcrBatch.STATUS_RUNNING).count(),
            'tasks': tasks.count(),
            'pages': OcrPage.objects.filter(task__in=tasks).count(),
            'pending_tasks': tasks.filter(status=OcrTask.STATUS_PENDING).count(),
            'running_tasks': tasks.filter(status=OcrTask.STATUS_RUNNING).count(),
            'succeeded_tasks': tasks.filter(status=OcrTask.STATUS_SUCCEEDED).count(),
            'failed_tasks': tasks.filter(status=OcrTask.STATUS_FAILED).count(),
        })


class OcrPageViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = OcrPageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['task', 'page_number']
    search_fields = ['text']
    ordering_fields = ['page_number', 'created_at']
    ordering = ['task_id', 'page_number']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return OcrPage.objects.none()
        tasks = OcrTask.objects.all()
        if not user.is_staff:
            accessible_projects = accessible_projects_for_user(user)
            tasks = tasks.filter(
                models.Q(project__in=accessible_projects) | models.Q(project__isnull=True, created_by=user)
            ).distinct()
        return OcrPage.objects.filter(task__in=tasks).select_related('task')


class OcrBatchViewSet(viewsets.ModelViewSet):
    serializer_class = OcrBatchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'engine', 'status']
    search_fields = ['name']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not getattr(user, 'is_authenticated', False):
            return OcrBatch.objects.none()
        queryset = OcrBatch.objects.select_related('project', 'engine', 'created_by')
        if user.is_staff:
            return queryset
        accessible_projects = accessible_projects_for_user(user)
        return queryset.filter(
            models.Q(project__in=accessible_projects) | models.Q(project__isnull=True, created_by=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _can_manage_batch(self, batch):
        if batch.created_by_id == self.request.user.id:
            return True
        if batch.project_id and user_can_manage_project(self.request.user, batch.project):
            return True
        return False

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        batch = self.get_object()
        if not self._can_manage_batch(batch):
            raise PermissionDenied('No permission to manage this OCR batch.')
        for task in batch.tasks.filter(status=OcrTask.STATUS_PENDING).order_by('priority', 'created_at'):
            run_ocr_task(task)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        batch = self.get_object()
        if not self._can_manage_batch(batch):
            raise PermissionDenied('No permission to manage this OCR batch.')
        batch.tasks.filter(status=OcrTask.STATUS_PENDING).update(status=OcrTask.STATUS_CANCELLED)
        refresh_ocr_batch_status(batch)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data)
