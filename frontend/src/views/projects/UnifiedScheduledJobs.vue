<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ $t('project.scheduledJobs') }}</h1>
        <p class="page-subtitle">{{ $t('project.scheduledJobsSubtitle') }}</p>
      </div>
      <div class="header-actions">
        <el-button :disabled="jobs.length < 2" @click="openDependencyDialog">
          <el-icon><Plus /></el-icon>
          Dependency
        </el-button>
        <el-button @click="loadPage" :loading="loading">
          <el-icon><Refresh /></el-icon>
          {{ $t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Jobs</div>
        <div class="metric-value">{{ summary.total || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Active</div>
        <div class="metric-value">{{ summary.active || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Blocked</div>
        <div class="metric-value">{{ summary.blocked || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Run Failed</div>
        <div class="metric-value">{{ summary.runs?.failed || 0 }}</div>
      </div>
    </div>

    <div class="health-panel" :class="{ 'is-unhealthy': health.status === 'unhealthy' }">
      <div class="health-header">
        <div>
          <div class="health-title">Scheduler Health</div>
          <div class="health-subtitle">Checked {{ formatDate(health.checked_at) }}</div>
        </div>
        <el-tag :type="healthStatusType" effect="light">
          {{ health.status || 'healthy' }}
        </el-tag>
      </div>
      <div class="health-grid">
        <div class="health-metric">
          <span>Due Now</span>
          <strong>{{ health.counts?.due_now || 0 }}</strong>
        </div>
        <div class="health-metric">
          <span>Overdue</span>
          <strong>{{ health.counts?.overdue || 0 }}</strong>
        </div>
        <div class="health-metric">
          <span>Blocked</span>
          <strong>{{ health.counts?.blocked || 0 }}</strong>
        </div>
        <div class="health-metric">
          <span>Stale Running</span>
          <strong>{{ health.counts?.stale_running || 0 }}</strong>
        </div>
        <div class="health-metric">
          <span>Recent Failed</span>
          <strong>{{ health.counts?.recent_failed || 0 }}</strong>
        </div>
      </div>
      <el-table v-if="healthAlerts.length" :data="healthAlerts" class="alerts-table" size="small">
        <el-table-column label="Severity" width="110">
          <template #default="{ row }">
            <el-tag :type="getAlertTagType(row.severity)" effect="plain">
              {{ row.severity }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="Type" width="140" />
        <el-table-column prop="job_name" label="Job" min-width="220" show-overflow-tooltip />
        <el-table-column prop="module_display" label="Module" width="150" />
        <el-table-column prop="message" label="Message" min-width="260" show-overflow-tooltip />
      </el-table>
    </div>

    <div class="ops-panel">
      <div class="ops-header">
        <div>
          <div class="ops-title">Scheduler Operations</div>
          <div class="ops-subtitle">
            Backend {{ schedulerCapabilities.backend || '--' }} / configured {{ schedulerCapabilities.configured_backend || '--' }}
          </div>
        </div>
        <el-button type="primary" :loading="dueRunning" @click="handleRunDueJobs">
          Run Due Jobs
        </el-button>
      </div>
      <div class="ops-grid">
        <div class="ops-card">
          <span>Queue Mode</span>
          <strong>{{ schedulerCapabilities.supports_async_queue ? 'Async' : 'Local' }}</strong>
        </div>
        <div class="ops-card">
          <span>Dependencies</span>
          <strong>{{ schedulerCapabilities.supports_dependencies ? 'On' : 'Off' }}</strong>
        </div>
        <div class="ops-card">
          <span>Retries</span>
          <strong>{{ schedulerCapabilities.supports_retries ? 'On' : 'Off' }}</strong>
        </div>
        <div class="ops-card">
          <span>Alerts</span>
          <strong>{{ schedulerCapabilities.supports_alerts ? 'On' : 'Off' }}</strong>
        </div>
      </div>
      <div class="ops-form">
        <el-select v-model="dueRunForm.modules" multiple clearable collapse-tags placeholder="Modules">
          <el-option
            v-for="option in moduleOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-input-number v-model="dueRunForm.limit" :min="1" :max="100" controls-position="right" />
        <el-input-number v-model="dueRunForm.max_attempts" :min="1" :max="5" controls-position="right" />
        <el-checkbox v-model="dueRunForm.dry_run">Dry run</el-checkbox>
      </div>
      <el-alert
        v-if="lastDueRunResult"
        class="ops-result"
        :type="lastDueRunResult.queued ? 'success' : 'info'"
        :closable="false"
        show-icon
      >
        <template #title>
          {{ dueRunResultText }}
        </template>
      </el-alert>
    </div>

    <div class="scheduler-insight-grid">
      <div class="insight-panel">
        <div class="insight-head">
          <div>
            <div class="ops-title">Schedule Calendar</div>
            <div class="ops-subtitle">Next 7 days planned runs</div>
          </div>
        </div>
        <div class="calendar-grid">
          <div v-for="day in scheduleCalendar" :key="day.key" class="calendar-day">
            <div class="calendar-date">
              <strong>{{ day.label }}</strong>
              <span>{{ day.count }} jobs</span>
            </div>
            <div v-if="day.items.length" class="calendar-items">
              <button
                v-for="item in day.items.slice(0, 4)"
                :key="item.job_key"
                class="calendar-job"
                type="button"
                @click="openRunDialog(item)"
              >
                <span>{{ item.name }}</span>
                <small>{{ dayjs(item.next_run_time).format('HH:mm') }} · {{ item.module_display || getModuleText(item.module) }}</small>
              </button>
              <div v-if="day.items.length > 4" class="calendar-more">+{{ day.items.length - 4 }} more</div>
            </div>
            <el-empty v-else description="No runs" :image-size="40" />
          </div>
        </div>
      </div>

      <div class="insight-panel">
        <div class="insight-head">
          <div>
            <div class="ops-title">Worker Queue</div>
            <div class="ops-subtitle">Runtime pressure and queue health</div>
          </div>
          <el-tag :type="healthStatusType">{{ schedulerCapabilities.supports_async_queue ? 'Async queue' : 'Local runner' }}</el-tag>
        </div>
        <div class="queue-grid">
          <div v-for="metric in queueMetrics" :key="metric.key" class="queue-card" :class="metric.tone">
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
          </div>
        </div>
        <div class="queue-note">
          {{ queueHealthText }}
        </div>
      </div>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :xl="6" :lg="8" :md="12" :sm="24">
            <el-select
              v-model="filters.project"
              clearable
              filterable
              style="width: 100%"
              :placeholder="$t('project.filterProject')"
              @change="handleFilterChange"
            >
              <el-option
                v-for="option in projectOptions"
                :key="option.id"
                :label="option.name"
                :value="option.id"
              />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="5" :md="6" :sm="12">
            <el-select
              v-model="filters.module"
              clearable
              style="width: 100%"
              :placeholder="$t('project.filterModule')"
              @change="handleFilterChange"
            >
              <el-option
                v-for="option in moduleOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="5" :md="6" :sm="12">
            <el-select
              v-model="filters.status"
              clearable
              style="width: 100%"
              :placeholder="$t('project.filterStatus')"
              @change="handleFilterChange"
            >
              <el-option
                v-for="option in statusOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="6" :md="8" :sm="12">
            <el-select
              v-model="filters.trigger_type"
              clearable
              style="width: 100%"
              :placeholder="$t('project.filterTriggerType')"
              @change="handleFilterChange"
            >
              <el-option
                v-for="option in triggerOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-col>
        </el-row>
      </div>

      <el-table v-loading="loading" :data="jobs" style="width: 100%">
        <el-table-column prop="name" :label="$t('project.jobName')" min-width="220" show-overflow-tooltip />
        <el-table-column :label="$t('project.projectName')" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link
              v-if="row.unified_project_id"
              type="primary"
              @click="goToProject(row.unified_project_id)"
            >
              {{ row.unified_project_name || '--' }}
            </el-link>
            <span v-else>{{ row.source_project_name || '--' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.moduleType')" width="150">
          <template #default="{ row }">
            <el-tag :type="getModuleTagType(row)">
              {{ row.module_display || getModuleText(row.module) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.taskType')" width="140">
          <template #default="{ row }">
            {{ getTaskTypeText(row.task_type) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.triggerType')" width="140">
          <template #default="{ row }">
            {{ getTriggerTypeText(row.trigger_type) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.targetName')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.target_name || '--' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.status')" width="120">
          <template #default="{ row }">
            <el-tag :type="getJobStatusType(row.status)">
              {{ getJobStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('project.nextRunTime')" min-width="180">
          <template #default="{ row }">
            {{ formatDate(row.next_run_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_runs" :label="$t('project.totalRuns')" width="100" />
        <el-table-column :label="$t('project.actions')" width="200" fixed="right">
          <template #default="{ row }">
            <div class="job-actions">
              <el-button
                size="small"
                type="primary"
                :loading="isActionLoading(row, 'run')"
                @click="openRunDialog(row)"
              >
                <el-icon><VideoPlay /></el-icon>
              </el-button>
              <el-button
                v-if="normalizeJobStatus(row.status) === 'active'"
                size="small"
                type="warning"
                :loading="isActionLoading(row, 'pause')"
                @click="handleJobAction(row, 'pause')"
              >
                <el-icon><VideoPause /></el-icon>
              </el-button>
              <el-button
                v-else-if="normalizeJobStatus(row.status) === 'paused'"
                size="small"
                type="success"
                :loading="isActionLoading(row, 'resume')"
                @click="handleJobAction(row, 'resume')"
              >
                <el-icon><RefreshRight /></el-icon>
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !jobs.length" :description="$t('project.noScheduledJobs')" />

      <div class="section-title">Dependency Graph</div>
      <div class="dependency-graph">
        <el-empty v-if="!graphNodes.length" description="No scheduled jobs" />
        <svg
          v-else
          class="dependency-svg"
          :viewBox="`0 0 900 ${graphHeight}`"
          preserveAspectRatio="xMinYMin meet"
        >
          <defs>
            <marker
              id="dependency-arrow"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" class="dependency-arrow" />
            </marker>
          </defs>
          <line
            v-for="edge in graphEdges"
            :key="edge.id"
            class="dependency-edge"
            :x1="edge.upstream.x + 220"
            :y1="edge.upstream.y + 34"
            :x2="edge.downstream.x"
            :y2="edge.downstream.y + 34"
            marker-end="url(#dependency-arrow)"
          />
          <g
            v-for="node in graphNodes"
            :key="node.id"
            class="graph-node"
            @click="selectGraphNode(node)"
          >
            <rect
              :x="node.x"
              :y="node.y"
              width="220"
              height="68"
              rx="8"
              ry="8"
              :class="graphNodeClass(node)"
            />
            <text :x="node.x + 14" :y="node.y + 26" class="graph-node-title">
              {{ truncateText(node.name, 22) }}
            </text>
            <text :x="node.x + 14" :y="node.y + 48" class="graph-node-meta">
              {{ graphNodeMeta(node) }}
            </text>
          </g>
        </svg>
      </div>

      <div class="section-title section-title-with-action">
        <span>Alert Center</span>
        <el-button size="small" :loading="notifySubmitting" @click="handleNotifyActiveAlerts">
          Push Active Alerts
        </el-button>
      </div>
      <div class="sub-filter-bar alert-filter-bar">
        <el-select v-model="alertFilters.status" clearable placeholder="Alert status" @change="fetchPersistedAlerts">
          <el-option label="Open" value="open" />
          <el-option label="Acknowledged" value="acknowledged" />
          <el-option label="Resolved" value="resolved" />
        </el-select>
        <el-select v-model="alertFilters.severity" clearable placeholder="Severity" @change="fetchPersistedAlerts">
          <el-option label="Critical" value="critical" />
          <el-option label="Danger" value="danger" />
          <el-option label="Warning" value="warning" />
          <el-option label="Info" value="info" />
        </el-select>
        <el-input
          v-model="alertFilters.search"
          clearable
          placeholder="Search alerts"
          @keyup.enter="fetchPersistedAlerts"
          @clear="fetchPersistedAlerts"
        />
        <el-button @click="fetchPersistedAlerts">Search</el-button>
      </div>
      <el-table :data="persistedAlerts" style="width: 100%">
        <el-table-column prop="last_seen_at" label="Last Seen" width="170">
          <template #default="{ row }">{{ formatDate(row.last_seen_at) }}</template>
        </el-table-column>
        <el-table-column prop="severity" label="Severity" width="110">
          <template #default="{ row }">
            <el-tag :type="getAlertTagType(row.severity)" effect="plain">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="alert_type" label="Type" width="150" />
        <el-table-column prop="job_name" label="Job" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="Status" width="130">
          <template #default="{ row }">
            <el-tag :type="getAlertStatusTagType(row.status)" effect="light">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="occurrences" label="Count" width="90" />
        <el-table-column label="Actions" width="230">
          <template #default="{ row }">
            <div class="job-actions">
              <el-button size="small" @click="focusJob(row)">
                Focus
              </el-button>
              <el-button
                size="small"
                type="warning"
                :disabled="row.status === 'resolved'"
                :loading="isAlertActionLoading(row, 'ack')"
                @click="handleAlertAction(row, 'ack')"
              >
                Ack
              </el-button>
              <el-button
                size="small"
                type="success"
                :disabled="row.status === 'resolved'"
                :loading="isAlertActionLoading(row, 'resolve')"
                @click="handleAlertAction(row, 'resolve')"
              >
                Resolve
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-title">Recent Runs</div>
      <div class="sub-filter-bar run-filter-bar">
        <el-select v-model="runFilters.status" clearable placeholder="Run status" @change="fetchRuns">
          <el-option label="Pending" value="pending" />
          <el-option label="Running" value="running" />
          <el-option label="Succeeded" value="succeeded" />
          <el-option label="Failed" value="failed" />
          <el-option label="Skipped" value="skipped" />
        </el-select>
        <el-select v-model="runFilters.trigger_source" clearable placeholder="Trigger" @change="fetchRuns">
          <el-option label="Manual" value="manual" />
          <el-option label="Scheduler" value="scheduler" />
          <el-option label="Retry" value="retry" />
        </el-select>
        <el-input
          v-model="runFilters.search"
          clearable
          placeholder="Search runs"
          @keyup.enter="fetchRuns"
          @clear="fetchRuns"
        />
        <el-button @click="fetchRuns">Search</el-button>
      </div>
      <el-table :data="runs" style="width: 100%">
        <el-table-column prop="job_name" label="Job" min-width="220" show-overflow-tooltip />
        <el-table-column prop="module_display" label="Module" width="150" />
        <el-table-column prop="status" label="Status" width="120">
          <template #default="{ row }">
            <el-tag :type="getRunStatusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempt" label="Attempt" width="90" />
        <el-table-column prop="started_at" label="Started" width="170">
          <template #default="{ row }">{{ formatDate(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="Error" min-width="220" show-overflow-tooltip />
        <el-table-column label="Actions" width="90">
          <template #default="{ row }">
            <el-button size="small" @click="focusJob(row)">
              Focus
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-title">Dependencies</div>
      <div class="sub-filter-bar dependency-filter-bar">
        <el-select v-model="dependencyFilters.module" clearable placeholder="Dependency module">
          <el-option
            v-for="option in moduleOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-select v-model="dependencyFilters.active" clearable placeholder="Active state" @change="fetchDependencies">
          <el-option label="Active" value="true" />
          <el-option label="Inactive" value="false" />
        </el-select>
      </div>
      <el-table :data="filteredDependencies" style="width: 100%">
        <el-table-column prop="upstream_key" label="Upstream" min-width="170" />
        <el-table-column prop="downstream_key" label="Downstream" min-width="170" />
        <el-table-column prop="is_active" label="Active" width="120">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_active"
              :loading="isDependencyLoading(row)"
              @change="handleToggleDependency(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="100">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              :loading="isDependencyLoading(row)"
              @click="handleDeleteDependency(row)"
            />
          </template>
        </el-table-column>
      </el-table>

      <div class="section-title">Audit Trail</div>
      <div class="sub-filter-bar audit-filter-bar">
        <el-select v-model="auditFilters.action" clearable placeholder="Action" @change="fetchAuditLogs">
          <el-option label="Create" value="create" />
          <el-option label="Update" value="update" />
          <el-option label="Delete" value="delete" />
          <el-option label="Run" value="run" />
          <el-option label="Pause" value="pause" />
          <el-option label="Resume" value="resume" />
        </el-select>
        <el-input
          v-model="auditFilters.search"
          clearable
          placeholder="Search audit"
          @keyup.enter="fetchAuditLogs"
          @clear="fetchAuditLogs"
        />
        <el-button @click="fetchAuditLogs">Search</el-button>
      </div>
      <el-table :data="auditLogs" style="width: 100%">
        <el-table-column prop="created_at" label="Time" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="action" label="Action" width="120">
          <template #default="{ row }">
            <el-tag effect="plain">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="object_name" label="Target" min-width="220" show-overflow-tooltip />
        <el-table-column prop="module" label="Module" width="150">
          <template #default="{ row }">{{ row.module || '--' }}</template>
        </el-table-column>
        <el-table-column prop="actor_username" label="Actor" width="140">
          <template #default="{ row }">{{ row.actor_username || '--' }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="Summary" min-width="260" show-overflow-tooltip />
      </el-table>
    </div>

    <el-dialog v-model="showDependencyDialog" title="New Dependency" width="560px">
      <el-form label-width="120px">
        <el-form-item label="Upstream">
          <el-select v-model="dependencyForm.upstream" filterable style="width: 100%">
            <el-option
              v-for="job in jobs"
              :key="job.job_key"
              :label="jobOptionLabel(job)"
              :value="job.job_key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Downstream">
          <el-select v-model="dependencyForm.downstream" filterable style="width: 100%">
            <el-option
              v-for="job in jobs"
              :key="job.job_key"
              :label="jobOptionLabel(job)"
              :value="job.job_key"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDependencyDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="dependencySubmitting" @click="submitDependency">
          Create
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showRunDialog" title="Run Scheduled Job" width="520px">
      <el-form label-width="130px">
        <el-form-item label="Job">
          <span>{{ selectedRunJob ? jobOptionLabel(selectedRunJob) : '--' }}</span>
        </el-form-item>
        <el-form-item label="Max Attempts">
          <el-input-number v-model="runForm.max_attempts" :min="1" :max="5" />
        </el-form-item>
        <el-form-item label="Force">
          <el-switch v-model="runForm.force" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRunDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="runSubmitting" @click="submitRunNow">
          Run
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete, Plus, Refresh, RefreshRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import {
  acknowledgeUnifiedSchedulerAlert,
  getProjectModuleCatalog,
  getUnifiedSchedulerAlerts,
  createUnifiedScheduledJobDependency,
  deleteUnifiedScheduledJobDependency,
  getUnifiedAuditLogs,
  notifyUnifiedSchedulerAlerts,
  getUnifiedScheduledJobDependencies,
  getUnifiedScheduledJobGraph,
  getUnifiedScheduledJobHealth,
  getUnifiedScheduledJobRuns,
  getUnifiedScheduledJobSummary,
  getUnifiedProjects,
  getUnifiedScheduledJobs,
  getSchedulerCapabilities,
  pauseUnifiedScheduledJob,
  resolveUnifiedSchedulerAlert,
  resumeUnifiedScheduledJob,
  runSchedulerDueJobs,
  runUnifiedScheduledJobNow,
  updateUnifiedScheduledJobDependency
} from '@/api/core'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

const loading = ref(false)
const jobs = ref([])
const runs = ref([])
const dependencies = ref([])
const graph = ref({ nodes: [], edges: [] })
const health = ref({ status: 'healthy', counts: {}, alerts: [] })
const persistedAlerts = ref([])
const auditLogs = ref([])
const projectOptions = ref([])
const moduleCatalog = ref([])
const actionLoading = ref({})
const alertActionLoading = ref({})
const dependencyLoading = ref({})
const dependencySubmitting = ref(false)
const notifySubmitting = ref(false)
const runSubmitting = ref(false)
const dueRunning = ref(false)
const showDependencyDialog = ref(false)
const showRunDialog = ref(false)
const selectedRunJob = ref(null)
const summary = ref({})
const schedulerCapabilities = ref({})
const lastDueRunResult = ref(null)
const dependencyForm = reactive({
  upstream: '',
  downstream: ''
})
const runForm = reactive({
  max_attempts: 1,
  force: false
})
const dueRunForm = reactive({
  modules: [],
  limit: 20,
  max_attempts: 3,
  dry_run: false
})
const filters = ref({
  project: '',
  module: '',
  status: '',
  trigger_type: ''
})
const runFilters = reactive({
  status: '',
  trigger_source: '',
  search: ''
})
const alertFilters = reactive({
  status: 'open',
  severity: '',
  search: ''
})
const dependencyFilters = reactive({
  module: '',
  active: ''
})
const auditFilters = reactive({
  action: '',
  search: ''
})

const statusAliasMap = {
  enabled: 'ACTIVE',
  active: 'ACTIVE',
  disabled: 'PAUSED',
  paused: 'PAUSED',
  completed: 'COMPLETED',
  failed: 'FAILED'
}

const moduleOptions = computed(() => {
  return moduleCatalog.value
    .filter(module => module.supports_scheduled_jobs)
    .map(module => ({
      value: module.key,
      label: module.display_name
    }))
})

const statusOptions = computed(() => [
  { value: 'ACTIVE', label: t('project.active') },
  { value: 'PAUSED', label: t('project.paused') },
  { value: 'COMPLETED', label: t('project.completed') },
  { value: 'FAILED', label: t('project.failedJobs') }
])

const triggerOptions = computed(() => [
  { value: 'CRON', label: t('project.triggerCron') },
  { value: 'INTERVAL', label: t('project.triggerInterval') },
  { value: 'ONCE', label: t('project.triggerOnce') }
])

const scheduleCalendar = computed(() => {
  const today = dayjs().startOf('day')
  return Array.from({ length: 7 }, (_, offset) => {
    const date = today.add(offset, 'day')
    const key = date.format('YYYY-MM-DD')
    const items = jobs.value
      .filter(job => job.next_run_time && dayjs(job.next_run_time).format('YYYY-MM-DD') === key)
      .sort((left, right) => dayjs(left.next_run_time).valueOf() - dayjs(right.next_run_time).valueOf())
    return {
      key,
      label: offset === 0 ? 'Today' : date.format('MM-DD'),
      count: items.length,
      items
    }
  })
})

const queueMetrics = computed(() => {
  const counts = health.value.counts || {}
  return [
    { key: 'due_now', label: 'Due Now', value: counts.due_now || 0, tone: counts.due_now ? 'is-warn' : '' },
    { key: 'overdue', label: 'Overdue', value: counts.overdue || 0, tone: counts.overdue ? 'is-danger' : '' },
    { key: 'stale_running', label: 'Stale Running', value: counts.stale_running || 0, tone: counts.stale_running ? 'is-danger' : '' },
    { key: 'recent_failed', label: 'Recent Failed', value: counts.recent_failed || 0, tone: counts.recent_failed ? 'is-danger' : '' },
    { key: 'blocked', label: 'Blocked', value: counts.blocked || 0, tone: counts.blocked ? 'is-warn' : '' },
    { key: 'active', label: 'Active Jobs', value: summary.value.active || 0, tone: '' }
  ]
})

const queueHealthText = computed(() => {
  const counts = health.value.counts || {}
  if (counts.stale_running || counts.overdue) {
    return 'Worker attention required: stale or overdue jobs detected.'
  }
  if (counts.due_now) {
    return 'Queue has due work ready to dispatch.'
  }
  return 'Queue pressure is normal.'
})

const graphNodes = computed(() => {
  const columns = 3
  return (graph.value.nodes || []).map((node, index) => ({
    ...node,
    x: 70 + (index % columns) * 280,
    y: 46 + Math.floor(index / columns) * 112
  }))
})

const graphNodeMap = computed(() => {
  return graphNodes.value.reduce((acc, node) => {
    acc[node.id] = node
    return acc
  }, {})
})

const graphEdges = computed(() => {
  return (graph.value.edges || [])
    .map(edge => ({
      ...edge,
      upstream: graphNodeMap.value[edge.upstream_key],
      downstream: graphNodeMap.value[edge.downstream_key]
    }))
    .filter(edge => edge.upstream && edge.downstream)
})

const graphHeight = computed(() => {
  return Math.max(240, 110 + Math.ceil(graphNodes.value.length / 3) * 112)
})

const healthAlerts = computed(() => health.value.alerts || [])

const healthStatusType = computed(() => {
  return health.value.status === 'unhealthy' ? 'danger' : 'success'
})

const dueRunResultText = computed(() => {
  const result = lastDueRunResult.value
  if (!result) {
    return ''
  }
  if (result.queued) {
    return `Queued by ${result.backend || 'scheduler'}: ${result.task_id || '--'}`
  }
  const summaryPayload = result.summary || {}
  return `Due ${summaryPayload.due || 0}, succeeded ${summaryPayload.succeeded || 0}, failed ${summaryPayload.failed || 0}, skipped ${summaryPayload.skipped || 0}`
})

const filteredDependencies = computed(() => {
  if (!dependencyFilters.module) {
    return dependencies.value
  }
  return dependencies.value.filter(dependency => {
    return dependency.upstream_module === dependencyFilters.module ||
      dependency.downstream_module === dependencyFilters.module
  })
})

const normalizeListResponse = (payload) => {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.results)) {
    return payload.results
  }
  return []
}

const normalizeJobStatus = (status) => String(status || '').toLowerCase()

const getActionLoadingKey = (job, action) => `${job.job_key}:${action}`

const isActionLoading = (job, action) => Boolean(actionLoading.value[getActionLoadingKey(job, action)])

const formatDate = (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--')

const truncateText = (value, maxLength = 24) => {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text
}

const graphNodeMeta = (node) => {
  const flags = []
  if (node.blocked) {
    flags.push('blocked')
  }
  if (node.is_running) {
    flags.push('running')
  }
  return `${node.module_display || node.module} / ${node.status || '--'}${flags.length ? ` / ${flags.join(', ')}` : ''}`
}

const graphNodeClass = (node) => {
  if (node.is_running) {
    return 'node-running'
  }
  if (node.blocked) {
    return 'node-blocked'
  }
  const statusText = String(node.status || '').toLowerCase()
  if (statusText === 'active') {
    return 'node-active'
  }
  if (statusText === 'paused') {
    return 'node-paused'
  }
  if (statusText === 'failed') {
    return 'node-failed'
  }
  return 'node-default'
}

const selectGraphNode = (node) => {
  const tableRow = jobs.value.find(job => job.job_key === node.id)
  if (tableRow?.unified_project_id) {
    goToProject(tableRow.unified_project_id)
  }
}

const getModuleTagType = (module) => {
  if (typeof module === 'object' && module) {
    return module.module_tag_type || module.tag_type || 'info'
  }
  const definition = moduleCatalog.value.find(item => item.key === module)
  return definition?.tag_type || 'info'
}

const getModuleText = (module) => {
  const definition = moduleCatalog.value.find(item => item.key === module)
  if (definition) {
    return definition.display_name
  }
  const textMap = {
    api_testing: t('project.apiTesting'),
    ui_automation: t('project.uiAutomation'),
    app_automation: t('project.appAutomation')
  }
  return textMap[module] || module
}

const getTaskTypeText = (taskType) => {
  const textMap = {
    TEST_SUITE: t('project.taskTypeTestSuite'),
    TEST_CASE: t('project.taskTypeTestCase'),
    API_REQUEST: t('project.taskTypeApiRequest')
  }
  return textMap[taskType] || taskType || '--'
}

const getTriggerTypeText = (triggerType) => {
  const textMap = {
    CRON: t('project.triggerCron'),
    INTERVAL: t('project.triggerInterval'),
    ONCE: t('project.triggerOnce')
  }
  return textMap[triggerType] || triggerType || '--'
}

const getJobStatusType = (status) => {
  const typeMap = {
    active: 'success',
    paused: 'warning',
    completed: 'info',
    failed: 'danger'
  }
  return typeMap[normalizeJobStatus(status)] || 'info'
}

const getJobStatusText = (status) => {
  const textMap = {
    active: t('project.active'),
    paused: t('project.paused'),
    completed: t('project.completed'),
    failed: t('project.failedJobs')
  }
  return textMap[normalizeJobStatus(status)] || status || '--'
}

const getRunStatusType = (status) => {
  const typeMap = {
    pending: 'info',
    running: 'warning',
    succeeded: 'success',
    failed: 'danger',
    skipped: 'info'
  }
  return typeMap[String(status || '').toLowerCase()] || 'info'
}

const getAlertTagType = (severity) => {
  const typeMap = {
    critical: 'danger',
    danger: 'danger',
    warning: 'warning',
    info: 'info'
  }
  return typeMap[String(severity || '').toLowerCase()] || 'info'
}

const getAlertStatusTagType = (statusValue) => {
  const typeMap = {
    open: 'danger',
    acknowledged: 'warning',
    resolved: 'success'
  }
  return typeMap[String(statusValue || '').toLowerCase()] || 'info'
}

const fetchProjects = async () => {
  try {
    const response = await getUnifiedProjects({ page: 1, page_size: 200 })
    projectOptions.value = normalizeListResponse(response.data)
  } catch (error) {
    ElMessage.error(t('project.fetchListFailed'))
  }
}

const buildFilterParams = () => {
  const params = {}
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) {
      params[key] = value
    }
  }
  return params
}

const applyRouteFilters = () => {
  const query = route.query || {}
  if (query.project) {
    filters.value.project = Number(query.project) || String(query.project)
  }
  if (query.module) {
    filters.value.module = String(query.module)
  }
  if (query.status) {
    const status = String(query.status)
    filters.value.status = statusAliasMap[status.toLowerCase()] || status
  }
  if (query.trigger_type) {
    filters.value.trigger_type = String(query.trigger_type).toUpperCase()
  }
}

const fetchJobs = async () => {
  loading.value = true
  try {
    const response = await getUnifiedScheduledJobs(buildFilterParams())
    jobs.value = normalizeListResponse(response.data)
  } catch (error) {
    jobs.value = []
    ElMessage.error(t('project.fetchJobsFailed'))
  } finally {
    loading.value = false
  }
}

const fetchGraph = async () => {
  try {
    const response = await getUnifiedScheduledJobGraph(buildFilterParams())
    graph.value = response.data || { nodes: [], edges: [] }
  } catch (error) {
    graph.value = { nodes: [], edges: [] }
  }
}

const fetchHealth = async () => {
  try {
    const response = await getUnifiedScheduledJobHealth(buildFilterParams())
    health.value = response.data || { status: 'healthy', counts: {}, alerts: [] }
  } catch (error) {
    health.value = { status: 'healthy', counts: {}, alerts: [] }
  }
}

const fetchPersistedAlerts = async () => {
  try {
    const params = {
      page: 1,
      page_size: 20
    }
    if (filters.value.project) {
      params.project_id = filters.value.project
    }
    if (filters.value.module) {
      params.module = filters.value.module
    }
    if (alertFilters.status) {
      params.status = alertFilters.status
    }
    if (alertFilters.severity) {
      params.severity = alertFilters.severity
    }
    if (alertFilters.search.trim()) {
      params.search = alertFilters.search.trim()
    }
    const response = await getUnifiedSchedulerAlerts(params)
    persistedAlerts.value = normalizeListResponse(response.data)
  } catch (error) {
    persistedAlerts.value = []
  }
}

const handleFilterChange = async () => {
  await Promise.all([fetchJobs(), fetchGraph(), fetchHealth(), fetchRuns(), fetchDependencies(), fetchAuditLogs()])
  await fetchPersistedAlerts()
}

const fetchSummary = async () => {
  try {
    const response = await getUnifiedScheduledJobSummary()
    summary.value = response.data || {}
  } catch (error) {
    summary.value = {}
  }
}

const fetchSchedulerCapabilities = async () => {
  try {
    const response = await getSchedulerCapabilities()
    schedulerCapabilities.value = response.data || {}
  } catch (error) {
    schedulerCapabilities.value = {}
  }
}

const fetchRuns = async () => {
  try {
    const params = {
      page: 1,
      page_size: 20
    }
    if (filters.value.module) {
      params.module = filters.value.module
    }
    if (runFilters.status) {
      params.status = runFilters.status
    }
    if (runFilters.trigger_source) {
      params.trigger_source = runFilters.trigger_source
    }
    if (runFilters.search.trim()) {
      params.search = runFilters.search.trim()
    }
    const response = await getUnifiedScheduledJobRuns(params)
    runs.value = normalizeListResponse(response.data)
  } catch (error) {
    runs.value = []
  }
}

const fetchDependencies = async () => {
  try {
    const params = {
      page: 1,
      page_size: 200
    }
    if (dependencyFilters.active) {
      params.is_active = dependencyFilters.active
    }
    const response = await getUnifiedScheduledJobDependencies(params)
    dependencies.value = normalizeListResponse(response.data)
  } catch (error) {
    dependencies.value = []
  }
}

const fetchAuditLogs = async () => {
  try {
    const params = {
      domain: 'scheduler',
      page: 1,
      page_size: 20
    }
    if (filters.value.project) {
      params.project_id = filters.value.project
    }
    if (filters.value.module) {
      params.module = filters.value.module
    }
    if (auditFilters.action) {
      params.action = auditFilters.action
    }
    if (auditFilters.search.trim()) {
      params.search = auditFilters.search.trim()
    }
    const response = await getUnifiedAuditLogs(params)
    auditLogs.value = normalizeListResponse(response.data)
  } catch (error) {
    auditLogs.value = []
  }
}

const getAlertActionLoadingKey = (alert, action) => `${alert.id}:${action}`

const isAlertActionLoading = (alert, action) => Boolean(alertActionLoading.value[getAlertActionLoadingKey(alert, action)])

const handleAlertAction = async (alert, action) => {
  const loadingKey = getAlertActionLoadingKey(alert, action)
  alertActionLoading.value = {
    ...alertActionLoading.value,
    [loadingKey]: true
  }
  try {
    if (action === 'ack') {
      await acknowledgeUnifiedSchedulerAlert(alert.id)
      ElMessage.success('Alert acknowledged')
    } else if (action === 'resolve') {
      await resolveUnifiedSchedulerAlert(alert.id)
      ElMessage.success('Alert resolved')
    }
    await fetchPersistedAlerts()
  } catch (error) {
    ElMessage.error('Failed to update alert')
  } finally {
    alertActionLoading.value = {
      ...alertActionLoading.value,
      [loadingKey]: false
    }
  }
}

const handleNotifyActiveAlerts = async () => {
  notifySubmitting.value = true
  try {
    const response = await notifyUnifiedSchedulerAlerts({ status: 'open' })
    const result = response.data || {}
    ElMessage.success(`Notified ${result.sent || 0}/${result.bots || 0} bots`)
    await fetchPersistedAlerts()
  } catch (error) {
    ElMessage.error('Failed to push alerts')
  } finally {
    notifySubmitting.value = false
  }
}

const handleRunDueJobs = async () => {
  dueRunning.value = true
  try {
    const response = await runSchedulerDueJobs({
      modules: dueRunForm.modules,
      limit: dueRunForm.limit,
      max_attempts: dueRunForm.max_attempts,
      dry_run: dueRunForm.dry_run,
      async_queue: schedulerCapabilities.value.supports_async_queue
    })
    lastDueRunResult.value = response.data || {}
    ElMessage.success(dueRunForm.dry_run ? 'Dry run completed' : 'Due jobs dispatched')
    await Promise.all([fetchJobs(), fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    ElMessage.error('Failed to run due scheduled jobs')
  } finally {
    dueRunning.value = false
  }
}

const goToProject = (projectId) => {
  router.push(`/ai-generation/projects/${projectId}`)
}

const focusJob = async (target) => {
  const jobKey = typeof target === 'string' ? target : target?.job_key
  const { module, source_id: sourceId } = splitJobKey(jobKey)
  if (!module || !sourceId) {
    return
  }
  const jobName = typeof target === 'object'
    ? target.job_name || target.name || ''
    : ''
  filters.value.module = module
  runFilters.search = jobName || String(sourceId)
  alertFilters.search = jobKey || jobName
  auditFilters.search = jobName || jobKey
  await handleFilterChange()
}

const handleJobAction = async (job, action) => {
  const loadingKey = getActionLoadingKey(job, action)
  actionLoading.value = {
    ...actionLoading.value,
    [loadingKey]: true
  }

  try {
    if (action === 'pause') {
      await pauseUnifiedScheduledJob(job.module, job.source_id)
      ElMessage.success(t('project.pauseJobSuccess'))
    } else if (action === 'resume') {
      await resumeUnifiedScheduledJob(job.module, job.source_id)
      ElMessage.success(t('project.resumeJobSuccess'))
    }

    await Promise.all([fetchJobs(), fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    if (error?.response?.status === 409) {
      ElMessage.warning(error.response.data?.detail || 'Dependency check failed')
      await Promise.all([fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchAuditLogs()])
      await fetchPersistedAlerts()
      return
    }
    const messageMap = {
      pause: t('project.pauseJobFailed'),
      resume: t('project.resumeJobFailed'),
      run: t('project.runJobFailed')
    }
    ElMessage.error(messageMap[action] || t('common.error'))
  } finally {
    actionLoading.value = {
      ...actionLoading.value,
      [loadingKey]: false
    }
  }
}

const jobOptionLabel = (job) => `${job.module_display || job.module} / ${job.name}`

const openRunDialog = (job) => {
  selectedRunJob.value = job
  runForm.max_attempts = 1
  runForm.force = false
  showRunDialog.value = true
}

const submitRunNow = async () => {
  const job = selectedRunJob.value
  if (!job) {
    return
  }

  const loadingKey = getActionLoadingKey(job, 'run')
  runSubmitting.value = true
  actionLoading.value = {
    ...actionLoading.value,
    [loadingKey]: true
  }

  try {
    await runUnifiedScheduledJobNow(job.module, job.source_id, {
      max_attempts: runForm.max_attempts,
      force: runForm.force
    })
    ElMessage.success(t('project.runJobSuccess'))
    showRunDialog.value = false
    await Promise.all([fetchJobs(), fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    if (error?.response?.status === 409) {
      ElMessage.warning(error.response.data?.detail || 'Dependency check failed')
      await Promise.all([fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchAuditLogs()])
      await fetchPersistedAlerts()
      return
    }
    ElMessage.error(t('project.runJobFailed'))
  } finally {
    runSubmitting.value = false
    actionLoading.value = {
      ...actionLoading.value,
      [loadingKey]: false
    }
  }
}

const splitJobKey = (jobKey) => {
  const [module, sourceId] = String(jobKey || '').split(':')
  return {
    module,
    source_id: Number(sourceId)
  }
}

const openDependencyDialog = () => {
  dependencyForm.upstream = jobs.value[0]?.job_key || ''
  dependencyForm.downstream = jobs.value[1]?.job_key || ''
  showDependencyDialog.value = true
}

const submitDependency = async () => {
  const upstream = splitJobKey(dependencyForm.upstream)
  const downstream = splitJobKey(dependencyForm.downstream)
  if (!upstream.module || !downstream.module || !upstream.source_id || !downstream.source_id) {
    ElMessage.warning('Select upstream and downstream jobs')
    return
  }
  dependencySubmitting.value = true
  try {
    await createUnifiedScheduledJobDependency({
      upstream_module: upstream.module,
      upstream_source_id: upstream.source_id,
      downstream_module: downstream.module,
      downstream_source_id: downstream.source_id,
      is_active: true
    })
    ElMessage.success('Dependency created')
    showDependencyDialog.value = false
    await Promise.all([fetchDependencies(), fetchGraph(), fetchHealth(), fetchSummary(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    ElMessage.error('Failed to create dependency')
  } finally {
    dependencySubmitting.value = false
  }
}

const isDependencyLoading = (dependency) => Boolean(dependencyLoading.value[dependency.id])

const handleToggleDependency = async (dependency) => {
  dependencyLoading.value = {
    ...dependencyLoading.value,
    [dependency.id]: true
  }
  try {
    await updateUnifiedScheduledJobDependency(dependency.id, { is_active: dependency.is_active })
    ElMessage.success('Dependency updated')
    await Promise.all([fetchGraph(), fetchHealth(), fetchSummary(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    dependency.is_active = !dependency.is_active
    ElMessage.error('Failed to update dependency')
  } finally {
    dependencyLoading.value = {
      ...dependencyLoading.value,
      [dependency.id]: false
    }
  }
}

const handleDeleteDependency = async (dependency) => {
  dependencyLoading.value = {
    ...dependencyLoading.value,
    [dependency.id]: true
  }
  try {
    await deleteUnifiedScheduledJobDependency(dependency.id)
    ElMessage.success('Dependency deleted')
    await Promise.all([fetchDependencies(), fetchGraph(), fetchHealth(), fetchSummary(), fetchAuditLogs()])
    await fetchPersistedAlerts()
  } catch (error) {
    ElMessage.error('Failed to delete dependency')
  } finally {
    dependencyLoading.value = {
      ...dependencyLoading.value,
      [dependency.id]: false
    }
  }
}

const fetchModuleCatalog = async () => {
  try {
    const response = await getProjectModuleCatalog({ scheduled: true })
    moduleCatalog.value = normalizeListResponse(response.data)
  } catch (error) {
    moduleCatalog.value = []
  }
}

const loadPage = async () => {
  applyRouteFilters()
  await Promise.all([fetchModuleCatalog(), fetchProjects(), fetchSchedulerCapabilities(), fetchJobs(), fetchGraph(), fetchHealth(), fetchSummary(), fetchRuns(), fetchDependencies(), fetchAuditLogs()])
  await fetchPersistedAlerts()
}

onMounted(async () => {
  await loadPage()
})
</script>

<style lang="scss" scoped>
.page-subtitle {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 14px 16px;
}

.metric-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}

.metric-value {
  color: var(--el-text-color-primary);
  font-size: 28px;
  line-height: 1;
  font-weight: 600;
}

.health-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 16px;
  margin-bottom: 16px;
}

.ops-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 16px;
  margin-bottom: 16px;
}

.ops-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.ops-title {
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.ops-subtitle {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.ops-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.ops-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;

  span {
    display: block;
    margin-bottom: 6px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 20px;
  }
}

.ops-form {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 130px 130px auto;
  gap: 10px;
  align-items: center;
}

.ops-result {
  margin-top: 12px;
}

.scheduler-insight-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.6fr);
  gap: 16px;
  margin-bottom: 20px;
}

.insight-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-bg-color);
}

.insight-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(110px, 1fr));
  gap: 10px;
  overflow-x: auto;
}

.calendar-day {
  min-height: 190px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px;
  background: var(--el-fill-color-extra-light);
}

.calendar-date {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.calendar-date strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.calendar-date span,
.calendar-more {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.calendar-items {
  display: grid;
  gap: 8px;
}

.calendar-job {
  width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 8px;
  text-align: left;
  background: var(--el-bg-color);
  cursor: pointer;
}

.calendar-job span,
.calendar-job small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.calendar-job span {
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.calendar-job small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
}

.queue-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.queue-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}

.queue-card.is-warn {
  border-color: var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
}

.queue-card.is-danger {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.queue-card span {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 6px;
}

.queue-card strong {
  color: var(--el-text-color-primary);
  font-size: 22px;
}

.queue-note {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.health-panel.is-unhealthy {
  border-color: var(--el-color-warning-light-5);
}

.health-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.health-title {
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.health-subtitle {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.health-metric {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}

.health-metric span {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 6px;
}

.health-metric strong {
  color: var(--el-text-color-primary);
  font-size: 22px;
}

.alerts-table {
  margin-top: 14px;
}

.filter-bar {
  margin-bottom: 20px;
}

.sub-filter-bar {
  display: grid;
  gap: 10px;
  margin-bottom: 12px;

  :deep(.el-select),
  :deep(.el-input) {
    width: 100%;
  }
}

.alert-filter-bar,
.run-filter-bar {
  grid-template-columns: minmax(130px, 170px) minmax(130px, 170px) minmax(180px, 1fr) auto;
}

.dependency-filter-bar,
.audit-filter-bar {
  grid-template-columns: minmax(150px, 220px) minmax(180px, 1fr) auto;
}

.job-actions {
  display: flex;
  gap: 8px;
}

.section-title {
  margin: 24px 0 12px;
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.section-title-with-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dependency-graph {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
  min-height: 240px;
  overflow: auto;
}

.dependency-svg {
  display: block;
  min-width: 900px;
  width: 100%;
}

.dependency-edge {
  stroke: var(--el-border-color-darker);
  stroke-width: 2;
  fill: none;
}

.dependency-arrow {
  fill: var(--el-border-color-darker);
}

.graph-node {
  cursor: pointer;
}

.graph-node rect {
  fill: var(--el-bg-color);
  stroke: var(--el-border-color);
  stroke-width: 1.5;
  transition: stroke 0.2s ease, filter 0.2s ease;
}

.graph-node:hover rect {
  filter: drop-shadow(0 4px 10px rgb(31 45 61 / 12%));
  stroke: var(--el-color-primary);
}

.graph-node .node-active {
  stroke: var(--el-color-success);
}

.graph-node .node-paused {
  stroke: var(--el-color-warning);
}

.graph-node .node-running {
  fill: var(--el-color-primary-light-9);
  stroke: var(--el-color-primary);
}

.graph-node .node-blocked {
  fill: var(--el-color-warning-light-9);
  stroke: var(--el-color-warning);
}

.graph-node .node-failed {
  fill: var(--el-color-danger-light-9);
  stroke: var(--el-color-danger);
}

.graph-node-title {
  fill: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.graph-node-meta {
  fill: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 768px) {
  .page-header,
  .header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .health-grid {
    grid-template-columns: 1fr;
  }

  .ops-header {
    flex-direction: column;
  }

  .ops-grid,
  .ops-form,
  .scheduler-insight-grid,
  .queue-grid {
    grid-template-columns: 1fr;
  }

  .alert-filter-bar,
  .run-filter-bar,
  .dependency-filter-bar,
  .audit-filter-bar {
    grid-template-columns: 1fr;
  }
}
</style>
