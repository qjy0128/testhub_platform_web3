from rest_framework import serializers

from apps.core.url_safety import validate_outbound_http_url
from apps.projects.unified import accessible_projects_for_user, user_can_access_project

from .models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeQuery


def _request_user(context):
    request = context.get('request')
    return getattr(request, 'user', None)


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    document_count = serializers.SerializerMethodField()
    query_count = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'project', 'project_name', 'name', 'description', 'status',
            'embedding_provider', 'embedding_model', 'vector_store', 'metadata',
            'document_count', 'query_count', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate_project(self, project):
        user = _request_user(self.context)
        if not user_can_access_project(user, project):
            raise serializers.ValidationError('Project is not accessible.')
        return project

    def get_document_count(self, obj) -> int:
        return getattr(obj, 'document_count', obj.documents.count())

    def get_query_count(self, obj) -> int:
        return getattr(obj, 'query_count', obj.queries.count())

    def validate_metadata(self, value):
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError('metadata must be an object.')

        embedding_settings = value.get('embedding')
        if not embedding_settings:
            return value
        if not isinstance(embedding_settings, dict):
            raise serializers.ValidationError('metadata.embedding must be an object.')

        base_url = (embedding_settings.get('base_url') or '').strip()
        if base_url:
            try:
                embedding_settings['base_url'] = validate_outbound_http_url(
                    base_url,
                    label='Embedding base URL',
                )
            except ValueError as exc:
                raise serializers.ValidationError({'embedding': {'base_url': str(exc)}})
        return value


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    knowledge_base_name = serializers.CharField(source='knowledge_base.name', read_only=True)
    project_id = serializers.IntegerField(source='knowledge_base.project_id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = KnowledgeDocument
        fields = [
            'id', 'knowledge_base', 'knowledge_base_name', 'project_id',
            'title', 'source_type', 'source_uri', 'file_name', 'file_size',
            'source_file', 'mime_type', 'content_hash', 'content_text', 'status',
            'chunk_count', 'error_message', 'metadata', 'created_by',
            'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'source_file', 'created_by', 'created_at', 'updated_at']

    def validate_knowledge_base(self, knowledge_base):
        user = _request_user(self.context)
        if not user_can_access_project(user, knowledge_base.project):
            raise serializers.ValidationError('Knowledge base is not accessible.')
        return knowledge_base


class KnowledgeChunkSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.title', read_only=True)
    knowledge_base_id = serializers.IntegerField(source='document.knowledge_base_id', read_only=True)

    class Meta:
        model = KnowledgeChunk
        fields = [
            'id', 'document', 'document_title', 'knowledge_base_id',
            'chunk_index', 'content', 'token_count', 'embedding_status',
            'embedding_provider', 'embedding_model', 'embedding_dimensions',
            'embedding_ref', 'metadata', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class KnowledgeQuerySerializer(serializers.ModelSerializer):
    knowledge_base_name = serializers.CharField(source='knowledge_base.name', read_only=True)
    project_id = serializers.IntegerField(source='knowledge_base.project_id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = KnowledgeQuery
        fields = [
            'id', 'knowledge_base', 'knowledge_base_name', 'project_id',
            'question', 'answer', 'citations', 'status', 'error_message',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'answer', 'citations', 'status', 'error_message', 'created_by', 'created_at']

    def validate_knowledge_base(self, knowledge_base):
        user = _request_user(self.context)
        if not user_can_access_project(user, knowledge_base.project):
            raise serializers.ValidationError('Knowledge base is not accessible.')
        return knowledge_base


def accessible_knowledge_bases_for_user(user):
    projects = accessible_projects_for_user(user)
    return KnowledgeBase.objects.filter(project__in=projects)
