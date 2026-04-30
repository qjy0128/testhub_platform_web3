/**
 * Core module APIs
 */
import request from '@/utils/api'

// Unified projects
export function getUnifiedProjects(params) {
  return request({
    url: '/projects/unified/',
    method: 'get',
    params
  })
}

export function getUnifiedProjectDetail(id) {
  return request({
    url: `/projects/unified/${id}/`,
    method: 'get'
  })
}

export function getMetaProjects(params) {
  return request({
    url: '/projects/meta/',
    method: 'get',
    params
  })
}

export function syncMetaProjectTree(projectId) {
  return request({
    url: `/projects/${projectId}/meta/sync/`,
    method: 'post'
  })
}

export function getProjectModuleBindings(projectId) {
  return request({
    url: `/projects/${projectId}/modules/`,
    method: 'get'
  })
}

export function getProjectPermissionPolicies(projectId, params) {
  return request({
    url: `/projects/${projectId}/permission-policies/`,
    method: 'get',
    params
  })
}

export function createProjectPermissionPolicy(projectId, data) {
  return request({
    url: `/projects/${projectId}/permission-policies/`,
    method: 'post',
    data
  })
}

export function updateProjectPermissionPolicy(projectId, policyId, data) {
  return request({
    url: `/projects/${projectId}/permission-policies/${policyId}/`,
    method: 'patch',
    data
  })
}

export function deleteProjectPermissionPolicy(projectId, policyId) {
  return request({
    url: `/projects/${projectId}/permission-policies/${policyId}/`,
    method: 'delete'
  })
}

export function getProjectModuleCatalog(params) {
  return request({
    url: '/projects/modules/catalog/',
    method: 'get',
    params
  })
}

export function createProjectModuleBinding(projectId, data) {
  return request({
    url: `/projects/${projectId}/modules/`,
    method: 'post',
    data
  })
}

export function deleteProjectModuleBinding(projectId, bindingId) {
  return request({
    url: `/projects/${projectId}/modules/${bindingId}/`,
    method: 'delete'
  })
}

// Unified scheduled jobs
export function getUnifiedScheduledJobs(params) {
  return request({
    url: '/core/scheduled-jobs/',
    method: 'get',
    params
  })
}

export function getSchedulerCapabilities() {
  return request({
    url: '/scheduler/capabilities/',
    method: 'get'
  })
}

export function runSchedulerDueJobs(data) {
  return request({
    url: '/scheduler/run-due/',
    method: 'post',
    data
  })
}

export function importApiPostmanCollection(projectId, data) {
  return request({
    url: `/api-testing/projects/${projectId}/import-postman/`,
    method: 'post',
    data
  })
}

export function importApiHar(projectId, data) {
  return request({
    url: `/api-testing/projects/${projectId}/import-har/`,
    method: 'post',
    data
  })
}

export function exportApiOpenApi(projectId) {
  return request({
    url: `/api-testing/projects/${projectId}/export-openapi/`,
    method: 'get'
  })
}

export function getApiSuiteParameterizedViews(suiteId) {
  return request({
    url: `/api-testing/test-suites/${suiteId}/parameterized-views/`,
    method: 'get'
  })
}

export function updateApiSuiteParameterizedViews(suiteId, data) {
  return request({
    url: `/api-testing/test-suites/${suiteId}/parameterized-views/`,
    method: 'post',
    data
  })
}

export function getUnifiedScheduledJobSummary() {
  return request({
    url: '/core/scheduled-jobs/summary/',
    method: 'get'
  })
}

export function getUnifiedScheduledJobHealth(params) {
  return request({
    url: '/core/scheduled-jobs/health/',
    method: 'get',
    params
  })
}

export function getUnifiedScheduledJobGraph(params) {
  return request({
    url: '/core/scheduled-jobs/graph/',
    method: 'get',
    params
  })
}

export function getUnifiedScheduledJobDetail(module, sourceId) {
  return request({
    url: `/core/scheduled-jobs/${module}/${sourceId}/`,
    method: 'get'
  })
}

export function pauseUnifiedScheduledJob(module, sourceId) {
  return request({
    url: `/core/scheduled-jobs/${module}/${sourceId}/pause/`,
    method: 'post'
  })
}

export function resumeUnifiedScheduledJob(module, sourceId) {
  return request({
    url: `/core/scheduled-jobs/${module}/${sourceId}/resume/`,
    method: 'post'
  })
}

export function runUnifiedScheduledJobNow(module, sourceId, data) {
  return request({
    url: `/core/scheduled-jobs/${module}/${sourceId}/run-now/`,
    method: 'post',
    data
  })
}

export function getUnifiedScheduledJobRuns(params) {
  return request({
    url: '/core/scheduled-job-runs/',
    method: 'get',
    params
  })
}

export function getUnifiedScheduledJobDependencies(params) {
  return request({
    url: '/core/scheduled-job-dependencies/',
    method: 'get',
    params
  })
}

export function getUnifiedSchedulerAlerts(params) {
  return request({
    url: '/core/scheduler-alerts/',
    method: 'get',
    params
  })
}

export function acknowledgeUnifiedSchedulerAlert(id) {
  return request({
    url: `/core/scheduler-alerts/${id}/acknowledge/`,
    method: 'post'
  })
}

export function resolveUnifiedSchedulerAlert(id) {
  return request({
    url: `/core/scheduler-alerts/${id}/resolve/`,
    method: 'post'
  })
}

export function notifyUnifiedSchedulerAlerts(data) {
  return request({
    url: '/core/scheduler-alerts/notify/',
    method: 'post',
    data
  })
}

export function createUnifiedScheduledJobDependency(data) {
  return request({
    url: '/core/scheduled-job-dependencies/',
    method: 'post',
    data
  })
}

export function updateUnifiedScheduledJobDependency(id, data) {
  return request({
    url: `/core/scheduled-job-dependencies/${id}/`,
    method: 'patch',
    data
  })
}

export function deleteUnifiedScheduledJobDependency(id) {
  return request({
    url: `/core/scheduled-job-dependencies/${id}/`,
    method: 'delete'
  })
}

export function getUnifiedAuditLogs(params) {
  return request({
    url: '/core/audit-logs/',
    method: 'get',
    params
  })
}

export function getUnifiedAuditLogSummary(params) {
  return request({
    url: '/core/audit-logs/summary/',
    method: 'get',
    params
  })
}

export function exportUnifiedAuditLogs(params) {
  return request({
    url: '/core/audit-logs/export/',
    method: 'get',
    params,
    responseType: 'blob'
  })
}

export function getRequestPerformanceMetrics(params) {
  return request({
    url: '/core/performance-metrics/',
    method: 'get',
    params
  })
}

export function getRequestPerformanceSummary(params) {
  return request({
    url: '/core/performance-metrics/summary/',
    method: 'get',
    params
  })
}

export function getRequestPerformanceTrends(params) {
  return request({
    url: '/core/performance-metrics/trends/',
    method: 'get',
    params
  })
}

export function getSlowRequests(params) {
  return request({
    url: '/core/performance-metrics/slow-requests/',
    method: 'get',
    params
  })
}

export function getErrorRequests(params) {
  return request({
    url: '/core/performance-metrics/error-requests/',
    method: 'get',
    params
  })
}

export function getStarAssetSummary() {
  return request({
    url: '/projects/star-assets/summary/',
    method: 'get'
  })
}

export function getStarAssetList(module, params) {
  return request({
    url: `/projects/star-assets/${module}/`,
    method: 'get',
    params
  })
}

export function getStarAssetDetail(assetId) {
  return request({
    url: `/projects/star-assets/detail/${assetId}/`,
    method: 'get'
  })
}

export function adoptStarAsset(assetId) {
  return request({
    url: `/projects/star-assets/detail/${assetId}/adopt/`,
    method: 'post'
  })
}

// Unified notification configs
export function getUnifiedNotificationConfigs(params) {
  return request({
    url: '/core/notification-configs/',
    method: 'get',
    params
  })
}

export function getUnifiedNotificationConfigDetail(id) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'get'
  })
}

export function createUnifiedNotificationConfig(data) {
  return request({
    url: '/core/notification-configs/',
    method: 'post',
    data
  })
}

export function updateUnifiedNotificationConfig(id, data) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'put',
    data
  })
}

export function deleteUnifiedNotificationConfig(id) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'delete'
  })
}

export function setDefaultNotificationConfig(id) {
  return request({
    url: `/core/notification-configs/${id}/set_default/`,
    method: 'post'
  })
}

export function getActiveNotificationConfigs() {
  return request({
    url: '/core/notification-configs/active_configs/',
    method: 'get'
  })
}

export function sendUnifiedNotificationTest(id, data) {
  return request({
    url: `/core/notification-configs/${id}/send_test/`,
    method: 'post',
    data
  })
}

export function getUnifiedNotificationTemplates(params) {
  return request({
    url: '/core/notification-templates/',
    method: 'get',
    params
  })
}

export function createUnifiedNotificationTemplate(data) {
  return request({
    url: '/core/notification-templates/',
    method: 'post',
    data
  })
}

export function updateUnifiedNotificationTemplate(id, data) {
  return request({
    url: `/core/notification-templates/${id}/`,
    method: 'put',
    data
  })
}

export function deleteUnifiedNotificationTemplate(id) {
  return request({
    url: `/core/notification-templates/${id}/`,
    method: 'delete'
  })
}

export function renderUnifiedNotificationTemplate(id, data) {
  return request({
    url: `/core/notification-templates/${id}/render/`,
    method: 'post',
    data
  })
}

export function getUnifiedNotificationSendLogs(params) {
  return request({
    url: '/core/notification-send-logs/',
    method: 'get',
    params
  })
}
