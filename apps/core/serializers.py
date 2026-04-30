"""
Core 应用序列化器
"""
from copy import deepcopy

from rest_framework import serializers
from .models import (
    RequestPerformanceMetric,
    UnifiedAuditLog,
    UnifiedNotificationConfig,
    UnifiedNotificationSendLog,
    UnifiedNotificationTemplate,
    UnifiedSchedulerAlert,
    UnifiedScheduledJobDependency,
    UnifiedScheduledJobRun,
)
from .notification_safety import redact_webhook_url, validate_notification_webhook_bots
from .scheduler_engine import dependency_would_create_cycle
from apps.projects.module_registry import get_module_definition


class UnifiedNotificationConfigSerializer(serializers.ModelSerializer):
    """统一通知配置序列化器"""

    webhook_bots_display = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedNotificationConfig
        fields = [
            'id', 'name', 'config_type', 'webhook_bots',
            'is_default', 'is_active', 'created_at', 'updated_at',
            'created_by', 'webhook_bots_display'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'webhook_bots_display']
        extra_kwargs = {
            'webhook_bots': {'write_only': True, 'required': False, 'allow_null': True},
        }

    def get_webhook_bots_display(self, obj) -> list:
        """获取webhook机器人显示信息"""
        bots = obj.get_webhook_bots()
        display_list = []
        for bot in bots:
            display_list.append({
                'type': bot.get('type'),
                'name': bot.get('name'),
                'webhook_url': redact_webhook_url(bot.get('webhook_url')),
                'has_secret': bool(bot.get('secret')),
                'enabled': bot.get('enabled'),
                'enable_ui_automation': bot.get('enable_ui_automation'),
                'enable_api_testing': bot.get('enable_api_testing')
            })
        return display_list

    def _without_masked_credentials(self, webhook_bots):
        if not isinstance(webhook_bots, dict):
            return webhook_bots

        cleaned_bots = deepcopy(webhook_bots)
        for bot_config in cleaned_bots.values():
            if not isinstance(bot_config, dict):
                continue
            for field in ('webhook_url', 'secret'):
                value = bot_config.get(field)
                if isinstance(value, str) and ('***' in value or not value.strip()):
                    bot_config.pop(field, None)
        return cleaned_bots

    def _merge_webhook_bots(self, instance, webhook_bots):
        if webhook_bots is None or not isinstance(webhook_bots, dict):
            return webhook_bots

        merged_bots = deepcopy(instance.webhook_bots or {})
        for bot_type, bot_config in webhook_bots.items():
            if not isinstance(bot_config, dict):
                merged_bots[bot_type] = bot_config
                continue

            existing_config = dict(merged_bots.get(bot_type) or {})
            cleaned_config = self._without_masked_credentials({bot_type: bot_config}).get(bot_type, {})
            existing_config.update(cleaned_config)
            merged_bots[bot_type] = existing_config
        return merged_bots

    def validate_webhook_bots(self, value):
        try:
            return validate_notification_webhook_bots(self._without_masked_credentials(value))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def update(self, instance, validated_data):
        if 'webhook_bots' in validated_data:
            validated_data['webhook_bots'] = self._merge_webhook_bots(
                instance,
                validated_data['webhook_bots'],
            )
        return super().update(instance, validated_data)


class UnifiedNotificationTemplateSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)

    class Meta:
        model = UnifiedNotificationTemplate
        fields = [
            'id',
            'name',
            'event_type',
            'channel',
            'subject_template',
            'body_template',
            'content_type',
            'variables_schema',
            'is_default',
            'is_active',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_username', 'created_at', 'updated_at']


class UnifiedNotificationSendLogSerializer(serializers.ModelSerializer):
    config_name = serializers.CharField(source='config.name', read_only=True, allow_null=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)

    class Meta:
        model = UnifiedNotificationSendLog
        fields = [
            'id',
            'config',
            'config_name',
            'template',
            'template_name',
            'channel',
            'target',
            'subject',
            'content',
            'status',
            'error_message',
            'attachments',
            'payload',
            'response_status',
            'created_by',
            'created_by_username',
            'created_at',
        ]
        read_only_fields = fields


class UnifiedScheduledJobSerializer(serializers.Serializer):
    job_key = serializers.CharField()
    module = serializers.CharField()
    module_display = serializers.CharField()
    module_description = serializers.CharField(allow_blank=True)
    module_frontend_path = serializers.CharField(allow_blank=True)
    module_tag_type = serializers.CharField()
    source_id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    task_type = serializers.CharField()
    trigger_type = serializers.CharField()
    status = serializers.CharField()
    target_name = serializers.CharField(allow_blank=True)
    source_project_id = serializers.IntegerField(allow_null=True)
    source_project_name = serializers.CharField(allow_blank=True)
    unified_project_id = serializers.IntegerField(allow_null=True)
    unified_project_name = serializers.CharField(allow_blank=True)
    last_run_time = serializers.DateTimeField(allow_null=True)
    next_run_time = serializers.DateTimeField(allow_null=True)
    total_runs = serializers.IntegerField()
    successful_runs = serializers.IntegerField()
    failed_runs = serializers.IntegerField()
    created_by_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    last_unified_run_id = serializers.IntegerField(allow_null=True)
    last_unified_run_status = serializers.CharField(allow_blank=True)
    last_unified_run_at = serializers.DateTimeField(allow_null=True)
    running_run_id = serializers.IntegerField(allow_null=True)
    is_running = serializers.BooleanField()
    dependency_count = serializers.IntegerField()


class UnifiedScheduledJobRunSerializer(serializers.ModelSerializer):
    job_key = serializers.CharField(read_only=True)
    module_display = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedScheduledJobRun
        fields = [
            'id', 'job_key', 'module', 'module_display', 'source_id', 'job_name',
            'status', 'attempt', 'max_attempts', 'trigger_source', 'scheduled_for',
            'locked_until', 'worker_id', 'retry_of', 'result', 'error_message',
            'triggered_by', 'started_at', 'finished_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'job_key', 'module_display', 'triggered_by', 'started_at',
            'finished_at', 'created_at', 'updated_at',
        ]

    def get_module_display(self, obj) -> str:
        definition = get_module_definition(obj.module)
        return definition.display_name if definition else obj.module


class UnifiedScheduledJobDependencySerializer(serializers.ModelSerializer):
    upstream_key = serializers.CharField(read_only=True)
    downstream_key = serializers.CharField(read_only=True)
    upstream_module_display = serializers.SerializerMethodField()
    downstream_module_display = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedScheduledJobDependency
        fields = [
            'id', 'upstream_key', 'upstream_module', 'upstream_module_display',
            'upstream_source_id', 'downstream_key', 'downstream_module',
            'downstream_module_display', 'downstream_source_id', 'is_active',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'upstream_key', 'downstream_key', 'upstream_module_display',
            'downstream_module_display', 'created_by', 'created_at', 'updated_at',
        ]

    def _module_display(self, module):
        definition = get_module_definition(module)
        return definition.display_name if definition else module

    def get_upstream_module_display(self, obj) -> str:
        return self._module_display(obj.upstream_module)

    def get_downstream_module_display(self, obj) -> str:
        return self._module_display(obj.downstream_module)

    def validate(self, attrs):
        instance = self.instance
        upstream_module = attrs.get('upstream_module', getattr(instance, 'upstream_module', None))
        upstream_source_id = attrs.get('upstream_source_id', getattr(instance, 'upstream_source_id', None))
        downstream_module = attrs.get('downstream_module', getattr(instance, 'downstream_module', None))
        downstream_source_id = attrs.get('downstream_source_id', getattr(instance, 'downstream_source_id', None))
        is_active = attrs.get('is_active', getattr(instance, 'is_active', True))

        if (
            upstream_module == downstream_module
            and upstream_source_id == downstream_source_id
        ):
            raise serializers.ValidationError('A scheduled job cannot depend on itself.')

        if is_active and dependency_would_create_cycle(
            upstream_module,
            upstream_source_id,
            downstream_module,
            downstream_source_id,
            exclude_dependency_id=getattr(instance, 'id', None),
        ):
            raise serializers.ValidationError('This dependency would create a cycle.')

        return attrs


class UnifiedAuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, allow_null=True)
    job_key = serializers.CharField(read_only=True)

    class Meta:
        model = UnifiedAuditLog
        fields = [
            'id',
            'domain',
            'action',
            'object_type',
            'object_id',
            'object_name',
            'module',
            'source_id',
            'job_key',
            'project_id',
            'project_name',
            'summary',
            'metadata',
            'actor',
            'actor_username',
            'created_at',
        ]
        read_only_fields = fields


class UnifiedSchedulerAlertSerializer(serializers.ModelSerializer):
    acknowledged_by_username = serializers.CharField(source='acknowledged_by.username', read_only=True, allow_null=True)

    class Meta:
        model = UnifiedSchedulerAlert
        fields = [
            'id',
            'alert_key',
            'alert_type',
            'severity',
            'status',
            'module',
            'source_id',
            'job_key',
            'job_name',
            'project_id',
            'project_name',
            'message',
            'details',
            'occurrences',
            'first_seen_at',
            'last_seen_at',
            'acknowledged_by',
            'acknowledged_by_username',
            'acknowledged_at',
            'resolved_at',
            'last_notified_at',
            'notify_count',
        ]
        read_only_fields = fields


class RequestPerformanceMetricSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, allow_null=True)
    status_group = serializers.CharField(read_only=True)

    class Meta:
        model = RequestPerformanceMetric
        fields = [
            'id',
            'method',
            'path',
            'route_name',
            'query_string',
            'status_code',
            'status_group',
            'response_time_ms',
            'request_size',
            'response_size',
            'is_slow',
            'is_error',
            'remote_addr',
            'user',
            'username',
            'user_agent',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields
