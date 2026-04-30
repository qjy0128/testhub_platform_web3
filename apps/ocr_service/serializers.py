from rest_framework import serializers

from apps.core.url_safety import validate_outbound_http_url
from apps.projects.unified import user_can_access_project

from .models import OcrBatch, OcrEngineConfig, OcrPage, OcrTask


def _request_user(context):
    request = context.get('request')
    return getattr(request, 'user', None)


class OcrEngineConfigSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    task_count = serializers.SerializerMethodField()

    class Meta:
        model = OcrEngineConfig
        fields = [
            'id', 'name', 'engine_type', 'base_url', 'model_name',
            'credential_ref', 'options', 'is_default', 'is_active',
            'last_checked_at', 'last_check_result', 'task_count',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_checked_at', 'last_check_result', 'created_by', 'created_at', 'updated_at']

    def get_task_count(self, obj) -> int:
        return getattr(obj, 'task_count', obj.tasks.count())

    def validate_base_url(self, value):
        value = (value or '').strip()
        if not value:
            return value
        try:
            return validate_outbound_http_url(value, label='OCR engine base URL')
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class OcrTaskSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    engine_name = serializers.CharField(source='engine.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    page_count = serializers.SerializerMethodField()

    class Meta:
        model = OcrTask
        fields = [
            'id', 'project', 'project_name', 'batch', 'engine', 'engine_name', 'name',
            'source_type', 'input_url', 'input_file', 'input_text', 'original_filename', 'file_size',
            'mime_type', 'status', 'extracted_text', 'result_json', 'confidence',
            'page_count', 'error_message', 'priority', 'attempt', 'max_attempts', 'started_at',
            'finished_at', 'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'input_file', 'status', 'extracted_text', 'result_json', 'confidence',
            'error_message', 'attempt', 'started_at', 'finished_at',
            'created_by', 'created_at', 'updated_at',
        ]

    def get_page_count(self, obj) -> int:
        return getattr(obj, 'page_count', obj.pages.count())

    def validate_project(self, project):
        if project is None:
            return project
        user = _request_user(self.context)
        if not user_can_access_project(user, project):
            raise serializers.ValidationError('Project is not accessible.')
        return project

    def validate_engine(self, engine):
        if engine is None:
            return engine
        user = _request_user(self.context)
        if not user or (engine.created_by_id != getattr(user, 'id', None) and not user.is_staff):
            raise serializers.ValidationError('OCR engine is not accessible.')
        if not engine.is_active:
            raise serializers.ValidationError('OCR engine is inactive.')
        return engine

    def validate_batch(self, batch):
        if batch is None:
            return batch
        user = _request_user(self.context)
        if batch.created_by_id == getattr(user, 'id', None):
            return batch
        if batch.project and user_can_access_project(user, batch.project):
            return batch
        raise serializers.ValidationError('OCR batch is not accessible.')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        batch = attrs.get('batch', getattr(self.instance, 'batch', None))
        project = attrs.get('project', getattr(self.instance, 'project', None))
        engine = attrs.get('engine', getattr(self.instance, 'engine', None))
        if batch and project and batch.project_id and batch.project_id != project.id:
            raise serializers.ValidationError({'project': 'Project must match the selected OCR batch.'})
        if batch and engine and batch.engine_id and batch.engine_id != engine.id:
            raise serializers.ValidationError({'engine': 'Engine must match the selected OCR batch.'})
        return attrs


class OcrBatchSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    engine_name = serializers.CharField(source='engine.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = OcrBatch
        fields = [
            'id', 'project', 'project_name', 'engine', 'engine_name', 'name',
            'status', 'total_tasks', 'succeeded_tasks', 'failed_tasks',
            'cancelled_tasks', 'metadata', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'total_tasks', 'succeeded_tasks', 'failed_tasks',
            'cancelled_tasks', 'created_by', 'created_at', 'updated_at',
        ]

    def validate_project(self, project):
        if project is None:
            return project
        user = _request_user(self.context)
        if not user_can_access_project(user, project):
            raise serializers.ValidationError('Project is not accessible.')
        return project

    def validate_engine(self, engine):
        if engine is None:
            return engine
        user = _request_user(self.context)
        if not user or (engine.created_by_id != getattr(user, 'id', None) and not user.is_staff):
            raise serializers.ValidationError('OCR engine is not accessible.')
        if not engine.is_active:
            raise serializers.ValidationError('OCR engine is inactive.')
        return engine


class OcrPageSerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source='task.name', read_only=True)

    class Meta:
        model = OcrPage
        fields = [
            'id', 'task', 'task_name', 'page_number', 'text', 'confidence',
            'width', 'height', 'result_json', 'metadata', 'created_at',
        ]
        read_only_fields = fields
