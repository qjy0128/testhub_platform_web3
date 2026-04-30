from django.contrib import admin

from .models import RequestPerformanceMetric, UnifiedNotificationSendLog, UnifiedNotificationTemplate


@admin.register(RequestPerformanceMetric)
class RequestPerformanceMetricAdmin(admin.ModelAdmin):
    list_display = [
        'method',
        'path',
        'status_code',
        'response_time_ms',
        'is_slow',
        'is_error',
        'user',
        'created_at',
    ]
    list_filter = ['method', 'status_code', 'is_slow', 'is_error', 'created_at']
    search_fields = ['path', 'route_name', 'user__username']
    readonly_fields = [field.name for field in RequestPerformanceMetric._meta.fields]
    ordering = ['-created_at']


@admin.register(UnifiedNotificationTemplate)
class UnifiedNotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'channel', 'content_type', 'is_default', 'is_active', 'created_by']
    list_filter = ['event_type', 'channel', 'content_type', 'is_default', 'is_active']
    search_fields = ['name', 'subject_template', 'body_template']


@admin.register(UnifiedNotificationSendLog)
class UnifiedNotificationSendLogAdmin(admin.ModelAdmin):
    list_display = ['channel', 'status', 'target', 'subject', 'config', 'template', 'created_at']
    list_filter = ['channel', 'status', 'created_at']
    search_fields = ['target', 'subject', 'content', 'error_message']
    readonly_fields = [field.name for field in UnifiedNotificationSendLog._meta.fields]
    ordering = ['-created_at']
