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

from .models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeQuery
from .serializers import (
    KnowledgeBaseSerializer,
    KnowledgeChunkSerializer,
    KnowledgeDocumentSerializer,
    KnowledgeQuerySerializer,
    accessible_knowledge_bases_for_user,
)
from .services import (
    answer_query,
    extract_text_from_document_file,
    get_answer_model_config,
    index_document,
    index_pending_documents,
    search_knowledge_base,
    validate_upload_file,
)


def _can_manage_knowledge_base(user, knowledge_base):
    return (
        getattr(knowledge_base, 'created_by_id', None) == getattr(user, 'id', None)
        or user_can_manage_project(user, knowledge_base.project)
    )


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'status', 'embedding_provider']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        return accessible_knowledge_bases_for_user(self.request.user).select_related(
            'project',
            'created_by',
        ).annotate(
            document_count=Count('documents', distinct=True),
            query_count=Count('queries', distinct=True),
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if not _can_manage_knowledge_base(self.request.user, self.get_object()):
            raise PermissionDenied('No permission to manage this knowledge base.')
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_manage_knowledge_base(self.request.user, instance):
            raise PermissionDenied('No permission to manage this knowledge base.')
        instance.delete()

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        knowledge_base = self.get_object()
        documents = knowledge_base.documents.select_related('created_by').order_by('-created_at')
        page = self.paginate_queryset(documents)
        if page is not None:
            serializer = KnowledgeDocumentSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = KnowledgeDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reindex(self, request, pk=None):
        knowledge_base = self.get_object()
        if not _can_manage_knowledge_base(request.user, knowledge_base):
            raise PermissionDenied('No permission to manage this knowledge base.')

        indexed = 0
        failed = 0
        for document in knowledge_base.documents.all():
            try:
                index_document(document)
                indexed += 1
            except Exception as exc:
                document.status = KnowledgeDocument.STATUS_FAILED
                document.error_message = str(exc)
                document.save(update_fields=['status', 'error_message', 'updated_at'])
                failed += 1

        return Response({'indexed': indexed, 'failed': failed})


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['knowledge_base', 'status', 'source_type', 'mime_type']
    search_fields = ['title', 'file_name', 'source_uri']
    ordering_fields = ['created_at', 'updated_at', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        knowledge_bases = accessible_knowledge_bases_for_user(self.request.user)
        return KnowledgeDocument.objects.filter(
            knowledge_base__in=knowledge_bases,
        ).select_related(
            'knowledge_base',
            'knowledge_base__project',
            'created_by',
        )

    def _can_manage_document(self, user, document):
        return (
            document.created_by_id == getattr(user, 'id', None)
            or _can_manage_knowledge_base(user, document.knowledge_base)
        )

    def _governance_response(self, document):
        serializer = self.get_serializer(document)
        return Response(serializer.data)

    def perform_create(self, serializer):
        document = serializer.save(created_by=self.request.user)
        if document.content_text:
            index_document(document)
        self._record_document_audit(document, 'Created knowledge document.', operation='create')

    def perform_update(self, serializer):
        document = self.get_object()
        if not (
            document.created_by_id == self.request.user.id
            or _can_manage_knowledge_base(self.request.user, document.knowledge_base)
        ):
            raise PermissionDenied('No permission to manage this document.')
        document = serializer.save()
        if document.content_text:
            index_document(document)

    def perform_destroy(self, instance):
        if not (
            instance.created_by_id == self.request.user.id
            or _can_manage_knowledge_base(self.request.user, instance.knowledge_base)
        ):
            raise PermissionDenied('No permission to manage this document.')
        instance.delete()

    @action(detail=True, methods=['post'])
    def mark_indexed(self, request, pk=None):
        document = self.get_object()
        if not (
            document.created_by_id == request.user.id
            or _can_manage_knowledge_base(request.user, document.knowledge_base)
        ):
            raise PermissionDenied('No permission to manage this document.')
        index_document(document)
        serializer = self.get_serializer(document)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def index(self, request, pk=None):
        document = self.get_object()
        if not self._can_manage_document(request.user, document):
            raise PermissionDenied('No permission to manage this document.')
        index_document(document)
        serializer = self.get_serializer(document)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='archive-governance')
    def archive_governance(self, request, pk=None):
        document = self.get_object()
        if not self._can_manage_document(request.user, document):
            raise PermissionDenied('No permission to manage this document.')
        metadata = dict(document.metadata or {})
        metadata['governance_archived'] = True
        metadata['governance_archived_at'] = timezone.now().isoformat()
        metadata['governance_archived_by'] = request.user.id
        metadata['governance_reason'] = request.data.get('reason') or 'Archived from governance center.'
        document.metadata = metadata
        document.save(update_fields=['metadata', 'updated_at'])
        self._record_document_audit(
            document,
            'Archived document from knowledge governance.',
            operation='archive_governance',
            metadata={'reason': metadata['governance_reason']},
        )
        return self._governance_response(document)

    @action(detail=True, methods=['post'], url_path='restore-governance')
    def restore_governance(self, request, pk=None):
        document = self.get_object()
        if not self._can_manage_document(request.user, document):
            raise PermissionDenied('No permission to manage this document.')
        metadata = dict(document.metadata or {})
        metadata['governance_archived'] = False
        metadata['governance_restored_at'] = timezone.now().isoformat()
        metadata['governance_restored_by'] = request.user.id
        document.metadata = metadata
        document.save(update_fields=['metadata', 'updated_at'])
        self._record_document_audit(
            document,
            'Restored document to knowledge governance.',
            operation='restore_governance',
        )
        return self._governance_response(document)

    @action(detail=True, methods=['post'], url_path='clean-chunks')
    def clean_chunks(self, request, pk=None):
        document = self.get_object()
        if not self._can_manage_document(request.user, document):
            raise PermissionDenied('No permission to manage this document.')
        remove_failed = bool(request.data.get('remove_failed', True))
        chunks = document.chunks.all()
        empty_ids = [
            chunk.id for chunk in chunks.only('id', 'content')
            if not (chunk.content or '').strip()
        ]
        failed_ids = []
        if remove_failed:
            failed_ids = list(chunks.filter(embedding_status='failed').values_list('id', flat=True))
        delete_ids = sorted(set(empty_ids + failed_ids))
        deleted_count = 0
        if delete_ids:
            deleted_count, _ = KnowledgeChunk.objects.filter(id__in=delete_ids).delete()
        if request.data.get('reindex', True):
            index_document(document)
        else:
            document.chunk_count = document.chunks.count()
            document.save(update_fields=['chunk_count', 'updated_at'])
        document.refresh_from_db()
        self._record_document_audit(
            document,
            'Cleaned knowledge document chunks.',
            operation='clean_chunks',
            metadata={'deleted_chunks': deleted_count, 'remove_failed': remove_failed},
        )
        return Response({
            'document': self.get_serializer(document).data,
            'deleted_chunks': deleted_count,
        })

    @action(detail=True, methods=['post'], url_path='mark-duplicate')
    def mark_duplicate(self, request, pk=None):
        document = self.get_object()
        if not self._can_manage_document(request.user, document):
            raise PermissionDenied('No permission to manage this document.')
        metadata = dict(document.metadata or {})
        metadata['duplicate_ignored'] = True
        metadata['duplicate_of'] = request.data.get('duplicate_of')
        metadata['duplicate_group'] = request.data.get('duplicate_group') or document.title
        metadata['duplicate_reason'] = request.data.get('reason') or 'Marked as duplicate from governance center.'
        metadata['duplicate_marked_at'] = timezone.now().isoformat()
        metadata['duplicate_marked_by'] = request.user.id
        document.metadata = metadata
        document.save(update_fields=['metadata', 'updated_at'])
        self._record_document_audit(
            document,
            'Marked knowledge document as duplicate.',
            operation='mark_duplicate',
            metadata={
                'duplicate_of': metadata['duplicate_of'],
                'duplicate_group': metadata['duplicate_group'],
            },
        )
        return self._governance_response(document)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        uploaded_file = request.FILES.get('file')
        if uploaded_file is None:
            return Response({'detail': 'No file was uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        uploaded_file.name = uploaded_file.name.split('\\')[-1].split('/')[-1]

        knowledge_base = accessible_knowledge_bases_for_user(request.user).filter(
            pk=request.data.get('knowledge_base')
        ).first()
        if knowledge_base is None:
            return Response({'detail': 'Knowledge base not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            validate_upload_file(uploaded_file)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title=request.data.get('title') or uploaded_file.name,
            source_type=KnowledgeDocument.SOURCE_UPLOAD,
            source_file=uploaded_file,
            file_name=uploaded_file.name,
            file_size=uploaded_file.size,
            mime_type=getattr(uploaded_file, 'content_type', '') or '',
            created_by=request.user,
        )

        try:
            document.content_text = extract_text_from_document_file(
                document.source_file.path,
                document.file_name,
            )
            document.save(update_fields=['content_text', 'updated_at'])
            index_document(document)
        except Exception as exc:
            document.status = KnowledgeDocument.STATUS_FAILED
            document.error_message = str(exc)
            document.save(update_fields=['status', 'error_message', 'updated_at'])

        serializer = self.get_serializer(document)
        self._record_document_audit(document, 'Uploaded knowledge document.', operation='upload')
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def import_ocr(self, request):
        knowledge_base = accessible_knowledge_bases_for_user(request.user).filter(
            pk=request.data.get('knowledge_base')
        ).first()
        if knowledge_base is None:
            return Response({'detail': 'Knowledge base not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from apps.ocr_service.models import OcrTask
        except Exception:
            return Response({'detail': 'OCR service is not available.'}, status=status.HTTP_400_BAD_REQUEST)

        projects = accessible_projects_for_user(request.user)
        task_ids = request.data.get('ocr_tasks') or request.data.get('ocr_task_ids')
        if task_ids is None and request.data.get('ocr_task'):
            task_ids = [request.data.get('ocr_task')]
        if task_ids is None and request.data.get('ocr_batch'):
            task_ids = list(OcrTask.objects.filter(batch_id=request.data.get('ocr_batch')).values_list('id', flat=True))
        if not isinstance(task_ids, list) or not task_ids:
            return Response({'detail': 'ocr_task, ocr_tasks, or ocr_batch is required.'}, status=status.HTTP_400_BAD_REQUEST)

        tasks = list(OcrTask.objects.filter(
            models.Q(project__in=projects) | models.Q(project__isnull=True, created_by=request.user),
            pk__in=task_ids,
        ).prefetch_related('pages').order_by('id'))
        if not tasks:
            return Response({'detail': 'OCR task not found.'}, status=status.HTTP_404_NOT_FOUND)
        invalid_tasks = [
            task.id for task in tasks
            if task.status != OcrTask.STATUS_SUCCEEDED or not task.extracted_text.strip()
        ]
        if invalid_tasks:
            return Response(
                {'detail': 'Only succeeded OCR tasks with extracted text can be imported.', 'invalid_task_ids': invalid_tasks},
                status=status.HTTP_400_BAD_REQUEST,
            )

        documents = [
            self._create_document_from_ocr_task(knowledge_base, task, request)
            for task in tasks
        ]
        if len(documents) == 1 and not isinstance(request.data.get('ocr_tasks'), list) and not request.data.get('ocr_batch'):
            serializer = self.get_serializer(documents[0])
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        serializer = self.get_serializer(documents, many=True)
        return Response({'count': len(documents), 'documents': serializer.data}, status=status.HTTP_201_CREATED)

    def _create_document_from_ocr_task(self, knowledge_base, task, request):
        text_version = request.data.get('text_version') or 'revised'
        use_original = text_version == 'original' or str(request.data.get('use_revised')).lower() in {'0', 'false', 'no'}

        def page_text_for_import(page):
            metadata = page.metadata if isinstance(page.metadata, dict) else {}
            if use_original:
                return metadata.get('original_text', page.text or '')
            return page.text or ''

        pages = [
            {
                'id': page.id,
                'page_number': page.page_number,
                'text': page_text_for_import(page),
                'confidence': page.confidence,
                'width': page.width,
                'height': page.height,
                'metadata': page.metadata,
            }
            for page in task.pages.all().order_by('page_number')
        ]
        if not pages:
            pages = [
                {
                    'page_number': page.get('page_number'),
                    'text': page.get('text', ''),
                    'confidence': page.get('confidence'),
                    'width': page.get('width') or 0,
                    'height': page.get('height') or 0,
                    'metadata': page.get('metadata') if isinstance(page.get('metadata'), dict) else {},
                }
                for page in (task.result_json or {}).get('pages', [])
                if isinstance(page, dict)
            ]

        result_json = task.result_json if isinstance(task.result_json, dict) else {}
        content_text = task.extracted_text
        if use_original:
            content_text = result_json.get('original_extracted_text') or '\n\n'.join(
                page.get('text', '') for page in pages
            ).strip()

        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title=request.data.get('title') or task.name,
            source_type=KnowledgeDocument.SOURCE_TEXT,
            source_uri=f'ocr-task:{task.id}',
            file_name=task.original_filename,
            file_size=task.file_size,
            mime_type=task.mime_type,
            content_text=content_text,
            metadata={
                'source': 'ocr_service',
                'ocr_task_id': task.id,
                'ocr_engine_id': task.engine_id,
                'ocr_batch_id': task.batch_id,
                'ocr_page_count': len(pages),
                'ocr_pages': pages,
                'ocr_text_version': 'original' if use_original else 'revised',
            },
            created_by=request.user,
        )
        index_document(document)
        self._record_document_audit(
            document,
            'Imported OCR result into knowledge base.',
            operation='import_ocr',
            metadata={
                'ocr_task_id': task.id,
                'ocr_batch_id': task.batch_id,
                'ocr_engine_id': task.engine_id,
                'ocr_page_count': len(pages),
                'ocr_text_version': 'original' if use_original else 'revised',
            },
        )
        return document

    def _record_document_audit(self, document, summary, *, operation, metadata=None):
        knowledge_base = document.knowledge_base
        record_unified_audit(
            domain='knowledge_base',
            action=UnifiedAuditLog.ACTION_CREATE,
            object_type='knowledge_document',
            object_id=document.id,
            object_name=document.title,
            project_id=knowledge_base.project_id,
            project_name=knowledge_base.project.name,
            actor=self.request.user,
            summary=summary,
            metadata={
                'operation': operation,
                'knowledge_base_id': knowledge_base.id,
                'source_type': document.source_type,
                'source_uri': document.source_uri,
                **(metadata or {}),
            },
        )


class KnowledgeChunkViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = KnowledgeChunkSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['document', 'embedding_status']
    search_fields = ['content']
    ordering_fields = ['chunk_index', 'created_at']
    ordering = ['document_id', 'chunk_index']

    def get_queryset(self):
        knowledge_bases = accessible_knowledge_bases_for_user(self.request.user)
        return KnowledgeChunk.objects.filter(
            document__knowledge_base__in=knowledge_bases,
        ).select_related('document', 'document__knowledge_base')


class KnowledgeQueryViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeQuerySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['knowledge_base', 'status']
    search_fields = ['question', 'answer']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        knowledge_bases = accessible_knowledge_bases_for_user(self.request.user)
        return KnowledgeQuery.objects.filter(
            knowledge_base__in=knowledge_bases,
        ).select_related(
            'knowledge_base',
            'knowledge_base__project',
            'created_by',
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        query = self.get_object()
        if not (
            query.created_by_id == self.request.user.id
            or _can_manage_knowledge_base(self.request.user, query.knowledge_base)
        ):
            raise PermissionDenied('No permission to manage this query.')
        serializer.save()

    def perform_destroy(self, instance):
        if not (
            instance.created_by_id == self.request.user.id
            or _can_manage_knowledge_base(self.request.user, instance.knowledge_base)
        ):
            raise PermissionDenied('No permission to manage this query.')
        instance.delete()

    @action(detail=False, methods=['post'])
    def ask(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.save(created_by=request.user)
        answer_query(query)
        payload = self.get_serializer(query).data
        payload['message'] = 'Knowledge retrieval completed.'
        return Response(payload, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def search(self, request):
        knowledge_base_id = request.query_params.get('knowledge_base')
        question = request.query_params.get('question', '')
        knowledge_base = accessible_knowledge_bases_for_user(request.user).filter(pk=knowledge_base_id).first()
        if knowledge_base is None:
            return Response({'detail': 'Knowledge base not found.'}, status=status.HTTP_404_NOT_FOUND)
        hits = search_knowledge_base(knowledge_base, question)
        return Response([
            {
                'document_id': hit.chunk.document_id,
                'document_title': hit.chunk.document.title,
                'chunk_id': hit.chunk.id,
                'chunk_index': hit.chunk.chunk_index,
                'page_number': (hit.chunk.metadata or {}).get('page_number'),
                'score': hit.score,
                'excerpt': hit.excerpt,
            }
            for hit in hits
        ])


class KnowledgeBaseSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_knowledge_base_summary_retrieve',
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        projects = accessible_projects_for_user(request.user)
        knowledge_bases = KnowledgeBase.objects.filter(project__in=projects)
        documents = KnowledgeDocument.objects.filter(knowledge_base__in=knowledge_bases)
        queries = KnowledgeQuery.objects.filter(knowledge_base__in=knowledge_bases)
        provider_counts = {
            (item['embedding_provider'] or 'local-hash'): item['count']
            for item in knowledge_bases.values('embedding_provider').annotate(count=Count('id'))
        }
        vector_store_counts = {
            item['vector_store']: item['count']
            for item in knowledge_bases.values('vector_store').annotate(count=Count('id'))
        }

        return Response({
            'projects': projects.count(),
            'knowledge_bases': knowledge_bases.count(),
            'documents': documents.count(),
            'ocr_linked_documents': documents.filter(metadata__source='ocr_service').count(),
            'chunks': KnowledgeChunk.objects.filter(document__in=documents).count(),
            'queries': queries.count(),
            'indexed_documents': documents.filter(status=KnowledgeDocument.STATUS_INDEXED).count(),
            'failed_documents': documents.filter(status=KnowledgeDocument.STATUS_FAILED).count(),
            'pending_queries': queries.filter(status=KnowledgeQuery.STATUS_PENDING).count(),
            'ai_answer_configured': bool(get_answer_model_config(request.user)),
            'embedding_providers': provider_counts,
            'vector_stores': vector_store_counts,
        })


class KnowledgeBaseMaintenanceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='api_knowledge_base_maintenance_create',
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        limit = request.data.get('limit') or request.query_params.get('limit')
        try:
            limit = int(limit) if limit else None
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid limit.'}, status=status.HTTP_400_BAD_REQUEST)
        knowledge_bases = accessible_knowledge_bases_for_user(request.user)
        queryset = KnowledgeDocument.objects.filter(knowledge_base__in=knowledge_bases)
        return Response(index_pending_documents(limit=limit, queryset=queryset))
