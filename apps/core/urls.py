"""
Core 应用路由
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    RequestPerformanceMetricViewSet,
    UnifiedAuditLogViewSet,
    UnifiedNotificationConfigViewSet,
    UnifiedNotificationSendLogViewSet,
    UnifiedNotificationTemplateViewSet,
    UnifiedSchedulerAlertViewSet,
    UnifiedScheduledJobDependencyViewSet,
    UnifiedScheduledJobDetailView,
    UnifiedScheduledJobGraphView,
    UnifiedScheduledJobHealthView,
    UnifiedScheduledJobListView,
    UnifiedScheduledJobRunViewSet,
    UnifiedScheduledJobPauseView,
    UnifiedScheduledJobResumeView,
    UnifiedScheduledJobRunNowView,
    UnifiedScheduledJobSummaryView,
)

router = DefaultRouter()
router.register(r'audit-logs', UnifiedAuditLogViewSet, basename='unified-audit-log')
router.register(r'performance-metrics', RequestPerformanceMetricViewSet, basename='request-performance-metric')
router.register(r'notification-configs', UnifiedNotificationConfigViewSet, basename='unified-notification-config')
router.register(r'notification-templates', UnifiedNotificationTemplateViewSet, basename='unified-notification-template')
router.register(r'notification-send-logs', UnifiedNotificationSendLogViewSet, basename='unified-notification-send-log')
router.register(r'scheduler-alerts', UnifiedSchedulerAlertViewSet, basename='unified-scheduler-alert')
router.register(r'scheduled-job-runs', UnifiedScheduledJobRunViewSet, basename='unified-scheduled-job-run')
router.register(r'scheduled-job-dependencies', UnifiedScheduledJobDependencyViewSet, basename='unified-scheduled-job-dependency')

urlpatterns = [
    path('', include(router.urls)),
    path('scheduled-jobs/summary/', UnifiedScheduledJobSummaryView.as_view(), name='unified-scheduled-job-summary'),
    path('scheduled-jobs/health/', UnifiedScheduledJobHealthView.as_view(), name='unified-scheduled-job-health'),
    path('scheduled-jobs/graph/', UnifiedScheduledJobGraphView.as_view(), name='unified-scheduled-job-graph'),
    path('scheduled-jobs/', UnifiedScheduledJobListView.as_view(), name='unified-scheduled-job-list'),
    path(
        'scheduled-jobs/<str:module>/<int:source_id>/',
        UnifiedScheduledJobDetailView.as_view(),
        name='unified-scheduled-job-detail',
    ),
    path(
        'scheduled-jobs/<str:module>/<int:source_id>/pause/',
        UnifiedScheduledJobPauseView.as_view(),
        name='unified-scheduled-job-pause',
    ),
    path(
        'scheduled-jobs/<str:module>/<int:source_id>/resume/',
        UnifiedScheduledJobResumeView.as_view(),
        name='unified-scheduled-job-resume',
    ),
    path(
        'scheduled-jobs/<str:module>/<int:source_id>/run-now/',
        UnifiedScheduledJobRunNowView.as_view(),
        name='unified-scheduled-job-run-now',
    ),
]
