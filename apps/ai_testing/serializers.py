from rest_framework import serializers

from apps.projects.unified import user_can_access_project

from .models import AiTestingRun, AiTestingTask


def _request_user(context):
    request = context.get('request')
    return getattr(request, 'user', None)


class AiTestingTaskSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    run_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = AiTestingTask
        fields = [
            'id', 'project', 'project_name', 'name', 'description',
            'instruction', 'target_url', 'execution_mode', 'status',
            'browser_config', 'metadata', 'run_count',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate_project(self, project):
        user = _request_user(self.context)
        if not user_can_access_project(user, project):
            raise serializers.ValidationError('Project is not accessible.')
        return project


class AiTestingRunSerializer(serializers.ModelSerializer):
    task_name = serializers.CharField(source='task.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = AiTestingRun
        fields = [
            'id', 'task', 'task_name', 'project', 'project_name', 'status',
            'instruction_snapshot', 'target_url_snapshot', 'execution_mode',
            'planned_steps', 'executed_steps', 'artifacts', 'cost', 'logs',
            'error_message', 'created_by', 'created_by_name',
            'started_at', 'finished_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'task_name', 'project', 'project_name', 'instruction_snapshot',
            'target_url_snapshot', 'execution_mode', 'planned_steps',
            'executed_steps', 'artifacts', 'cost', 'logs', 'error_message',
            'created_by', 'started_at', 'finished_at', 'created_at', 'updated_at',
        ]
