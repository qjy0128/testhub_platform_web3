<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">AI Testing</h1>
        <p class="page-subtitle">Browser tasks, execution plans, and run records</p>
      </div>
      <div class="header-actions">
        <el-button :loading="queueRunning" :disabled="!(summary.pending_runs || 0)" @click="handleRunQueue">
          Run Queue
        </el-button>
        <el-button :loading="loading" @click="loadPage">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
        <el-button type="primary" @click="openTaskDialog">
          <el-icon><Plus /></el-icon>
          New Task
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Tasks</div>
        <div class="metric-value">{{ summary.tasks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Active</div>
        <div class="metric-value">{{ summary.active_tasks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Runs</div>
        <div class="metric-value">{{ summary.runs || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Running</div>
        <div class="metric-value">{{ summary.running_runs || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Succeeded</div>
        <div class="metric-value">{{ summary.succeeded_runs || 0 }}</div>
      </div>
    </div>

    <div class="card-container">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Tasks" name="tasks">
          <div class="table-toolbar task-toolbar">
            <el-select v-model="taskFilters.project" clearable filterable placeholder="Project" @change="fetchTasks">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-select v-model="taskFilters.execution_mode" clearable placeholder="Mode" @change="fetchTasks">
              <el-option label="Text" value="browser_text" />
              <el-option label="Vision" value="browser_vision" />
            </el-select>
            <el-select v-model="taskFilters.status" clearable placeholder="Status" @change="fetchTasks">
              <el-option label="Active" value="active" />
              <el-option label="Archived" value="archived" />
            </el-select>
            <el-input
              v-model="taskFilters.search"
              clearable
              placeholder="Search tasks"
              @keyup.enter="fetchTasks"
              @clear="fetchTasks"
            />
            <el-button @click="fetchTasks">Search</el-button>
          </div>
          <el-table v-loading="loading" :data="tasks" style="width: 100%">
            <el-table-column prop="name" label="Name" min-width="180" show-overflow-tooltip />
            <el-table-column prop="project_name" label="Project" min-width="150" show-overflow-tooltip />
            <el-table-column prop="target_url" label="Target" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.target_url || '--' }}</template>
            </el-table-column>
            <el-table-column prop="execution_mode" label="Mode" width="140">
              <template #default="{ row }">
                <el-tag>{{ modeLabel(row.execution_mode) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="110">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="run_count" label="Runs" width="90" />
            <el-table-column prop="updated_at" label="Updated" width="170">
              <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="210" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleQueueRun(row)">Queue</el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="isTaskRunning(row)"
                  @click="handleStartRun(row)"
                >
                  Run
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Runs" name="runs">
          <div class="table-toolbar run-toolbar">
            <el-select v-model="runFilters.project" clearable filterable placeholder="Project" @change="fetchRuns">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-select v-model="runFilters.status" clearable placeholder="Status" @change="fetchRuns">
              <el-option label="Pending" value="pending" />
              <el-option label="Running" value="running" />
              <el-option label="Succeeded" value="succeeded" />
              <el-option label="Failed" value="failed" />
              <el-option label="Cancelled" value="cancelled" />
            </el-select>
            <el-select v-model="runFilters.execution_mode" clearable placeholder="Mode" @change="fetchRuns">
              <el-option label="Text" value="browser_text" />
              <el-option label="Vision" value="browser_vision" />
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
          <el-table v-loading="loading" :data="runs" style="width: 100%">
            <el-table-column prop="task_name" label="Task" min-width="180" show-overflow-tooltip />
            <el-table-column prop="project_name" label="Project" min-width="150" show-overflow-tooltip />
            <el-table-column prop="status" label="Status" width="120">
              <template #default="{ row }">
                <el-tag :type="runStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="execution_mode" label="Mode" width="140">
              <template #default="{ row }">{{ modeLabel(row.execution_mode) }}</template>
            </el-table-column>
            <el-table-column label="Progress" width="180">
              <template #default="{ row }">
                <el-progress
                  :percentage="runProgress(row)"
                  :status="row.status === 'failed' ? 'exception' : row.status === 'succeeded' ? 'success' : undefined"
                  :stroke-width="8"
                />
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="Created" width="170">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="230" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openRunDrawer(row)">Details</el-button>
                <el-button
                  v-if="row.status === 'pending' || row.status === 'failed'"
                  size="small"
                  type="primary"
                  :loading="isRunStarting(row)"
                  @click="handleStartQueuedRun(row)"
                >
                  Start
                </el-button>
                <el-button
                  v-if="row.status === 'running'"
                  size="small"
                  type="danger"
                  plain
                  :loading="isRunCancelling(row)"
                  @click="handleCancelRun(row)"
                >
                  Cancel
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="showTaskDialog" title="New AI Testing Task" width="680px">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="130px">
        <el-form-item label="Project" prop="project">
          <el-select v-model="taskForm.project" filterable placeholder="Select project" style="width: 100%">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Name" prop="name">
          <el-input v-model="taskForm.name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="Target URL">
          <el-input v-model="taskForm.target_url" maxlength="1000" />
        </el-form-item>
        <el-form-item label="Mode">
          <el-segmented
            v-model="taskForm.execution_mode"
            :options="[
              { label: 'Text', value: 'browser_text' },
              { label: 'Vision', value: 'browser_vision' }
            ]"
          />
        </el-form-item>
        <el-form-item label="Instruction" prop="instruction">
          <el-input
            v-model="taskForm.instruction"
            type="textarea"
            :rows="8"
            maxlength="8000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="taskForm.browser_config.enable_gif">Record GIF</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTaskDialog = false">Cancel</el-button>
        <el-button :loading="submitting" @click="submitTask(false)">Create</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTask(true)">Create And Run</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showRunDrawer" title="Run Details" size="50%">
      <template v-if="selectedRun">
        <div class="drawer-summary">
          <el-tag :type="runStatusType(selectedRun.status)">{{ selectedRun.status }}</el-tag>
          <span>{{ selectedRun.task_name }}</span>
          <span>{{ formatDate(selectedRun.started_at) }} - {{ formatDate(selectedRun.finished_at) }}</span>
        </div>

        <el-divider />

        <h3 class="section-title">Planned Steps</h3>
        <el-table
          :data="selectedRun.planned_steps || []"
          size="small"
          style="width: 100%"
          :row-class-name="plannedStepRowClass"
        >
          <el-table-column prop="index" label="#" width="70" />
          <el-table-column prop="title" label="Step" min-width="220" show-overflow-tooltip />
          <el-table-column prop="status" label="Status" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="stepStatusType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Evidence" width="170">
            <template #default="{ row }">
              <el-button
                v-for="item in stepEvidence(selectedRun, row).slice(0, 2)"
                :key="item.key"
                size="small"
                link
                type="primary"
                @click="openEvidence(item)"
              >
                {{ item.label }}
              </el-button>
              <span v-if="!stepEvidence(selectedRun, row).length" class="muted-text">--</span>
            </template>
          </el-table-column>
        </el-table>

        <h3 class="section-title">Execution Evidence</h3>
        <div class="evidence-grid">
          <div class="evidence-card" @click="openEvidenceGroup('screenshots')">
            <span>Screenshots</span>
            <strong>{{ artifactList(selectedRun, 'screenshots').length }}</strong>
          </div>
          <div class="evidence-card" @click="openEvidenceGroup('recordings')">
            <span>Recordings</span>
            <strong>{{ artifactList(selectedRun, 'recordings').length }}</strong>
          </div>
          <div class="evidence-card" @click="openEvidenceGroup('history_steps')">
            <span>History</span>
            <strong>{{ artifactList(selectedRun, 'history_steps').length }}</strong>
          </div>
        </div>
        <div v-if="runDiagnosis(selectedRun)" class="diagnosis-panel" :class="{ 'is-failed': selectedRun.status === 'failed' }">
          <strong>{{ selectedRun.status === 'failed' ? 'Failure Diagnosis' : 'Run Diagnosis' }}</strong>
          <p>{{ runDiagnosis(selectedRun) }}</p>
        </div>

        <h3 class="section-title">Executed Timeline</h3>
        <el-timeline v-if="selectedRun.executed_steps?.length">
          <el-timeline-item
            v-for="(event, index) in selectedRun.executed_steps"
            :key="`${event.task_id || index}-${event.created_at || index}`"
            :timestamp="formatDate(event.created_at)"
            :type="event.status === 'failed' ? 'danger' : event.status === 'completed' ? 'success' : 'primary'"
          >
            Step {{ event.task_id || index + 1 }} / {{ event.status || '--' }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="No execution timeline" />

        <h3 class="section-title">Logs</h3>
        <pre class="run-logs">{{ selectedRun.logs || selectedRun.error_message || '--' }}</pre>
      </template>
    </el-drawer>

    <el-dialog v-model="showEvidenceDialog" :title="selectedEvidence?.title || 'Execution Evidence'" width="860px">
      <template v-if="selectedEvidence">
        <img
          v-if="selectedEvidence.kind === 'image'"
          class="evidence-media"
          :src="selectedEvidence.url"
          :alt="selectedEvidence.title"
        />
        <img
          v-else-if="selectedEvidence.kind === 'gif'"
          class="evidence-media"
          :src="selectedEvidence.url"
          :alt="selectedEvidence.title"
        />
        <iframe
          v-else-if="selectedEvidence.kind === 'html'"
          class="evidence-frame"
          :src="selectedEvidence.url"
          title="AI testing report"
        />
        <pre v-else class="evidence-json">{{ evidenceText(selectedEvidence) }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { getUnifiedProjects } from '@/api/core'
import {
  cancelAiTestingRun,
  createAiTestingTask,
  getAiTestingRuns,
  getAiTestingSummary,
  getAiTestingTasks,
  runPendingAiTestingRuns,
  runAiTestingTask,
  startAiTestingRun
} from '@/api/ai-testing'

const loading = ref(false)
const submitting = ref(false)
const queueRunning = ref(false)
const activeTab = ref('tasks')
const projects = ref([])
const tasks = ref([])
const runs = ref([])
const summary = reactive({})
const showTaskDialog = ref(false)
const showRunDrawer = ref(false)
const showEvidenceDialog = ref(false)
const selectedRun = ref(null)
const selectedEvidence = ref(null)
const taskFormRef = ref()
const runningTasks = ref({})
const startingRuns = ref({})
const cancellingRuns = ref({})
let refreshTimer = null
const taskFilters = reactive({
  project: null,
  execution_mode: '',
  status: '',
  search: ''
})
const runFilters = reactive({
  project: null,
  status: '',
  execution_mode: '',
  search: ''
})

const taskForm = reactive({
  project: null,
  name: '',
  target_url: '',
  execution_mode: 'browser_text',
  instruction: '',
  browser_config: {
    enable_gif: true
  }
})

const taskRules = computed(() => ({
  project: [{ required: true, message: 'Select project', trigger: 'change' }],
  name: [{ required: true, message: 'Enter name', trigger: 'blur' }],
  instruction: [{ required: true, message: 'Enter instruction', trigger: 'blur' }]
}))

const normalizeListResponse = (payload) => {
  if (Array.isArray(payload)) {
    return {
      results: payload,
      count: payload.length
    }
  }
  return {
    results: payload?.results || [],
    count: payload?.count || 0
  }
}

const formatDate = (value) => {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--'
}

const modeLabel = (mode) => {
  return mode === 'browser_vision' ? 'Vision' : 'Text'
}

const runStatusType = (status) => {
  const typeMap = {
    pending: 'info',
    running: 'warning',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return typeMap[status] || 'info'
}

const stepStatusType = (status) => {
  const typeMap = {
    completed: 'success',
    failed: 'danger',
    skipped: 'info',
    in_progress: 'warning',
    pending: 'info'
  }
  return typeMap[status] || 'info'
}

const runProgress = (run) => {
  const steps = run.planned_steps || []
  if (!steps.length) {
    return run.status === 'succeeded' ? 100 : 0
  }
  const completed = steps.filter(step => ['completed', 'failed', 'skipped'].includes(step.status)).length
  return Math.round((completed / steps.length) * 100)
}

const isTaskRunning = (task) => Boolean(runningTasks.value[task.id])
const isRunStarting = (run) => Boolean(startingRuns.value[run.id])
const isRunCancelling = (run) => Boolean(cancellingRuns.value[run.id])

const fetchProjects = async () => {
  const response = await getUnifiedProjects({ page: 1, page_size: 200 })
  projects.value = normalizeListResponse(response.data).results
}

const fetchSummary = async () => {
  const response = await getAiTestingSummary()
  Object.keys(summary).forEach(key => delete summary[key])
  Object.assign(summary, response.data || {})
}

const fetchTasks = async () => {
  const params = { page: 1, page_size: 200 }
  if (taskFilters.project) {
    params.project = taskFilters.project
  }
  if (taskFilters.execution_mode) {
    params.execution_mode = taskFilters.execution_mode
  }
  if (taskFilters.status) {
    params.status = taskFilters.status
  }
  if (taskFilters.search.trim()) {
    params.search = taskFilters.search.trim()
  }
  const response = await getAiTestingTasks(params)
  tasks.value = normalizeListResponse(response.data).results
}

const fetchRuns = async () => {
  const params = { page: 1, page_size: 200 }
  if (runFilters.project) {
    params.project = runFilters.project
  }
  if (runFilters.status) {
    params.status = runFilters.status
  }
  if (runFilters.execution_mode) {
    params.execution_mode = runFilters.execution_mode
  }
  if (runFilters.search.trim()) {
    params.search = runFilters.search.trim()
  }
  const response = await getAiTestingRuns(params)
  runs.value = normalizeListResponse(response.data).results
  if (selectedRun.value) {
    selectedRun.value = runs.value.find(run => run.id === selectedRun.value.id) || selectedRun.value
  }
}

const loadPage = async () => {
  loading.value = true
  try {
    await Promise.all([fetchProjects(), fetchSummary(), fetchTasks(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to load AI testing')
  } finally {
    loading.value = false
  }
}

const refreshRunsIfNeeded = async () => {
  if (!runs.value.some(run => run.status === 'running')) {
    return
  }
  await Promise.all([fetchSummary(), fetchRuns()])
}

const resetTaskForm = () => {
  Object.assign(taskForm, {
    project: projects.value[0]?.id || null,
    name: '',
    target_url: '',
    execution_mode: 'browser_text',
    instruction: '',
    browser_config: {
      enable_gif: true
    }
  })
  taskFormRef.value?.clearValidate()
}

const openTaskDialog = () => {
  resetTaskForm()
  showTaskDialog.value = true
}

const submitTask = async (startImmediately) => {
  if (!taskFormRef.value) {
    return
  }
  try {
    await taskFormRef.value.validate()
  } catch (error) {
    return
  }

  submitting.value = true
  try {
    const taskResponse = await createAiTestingTask({ ...taskForm })
    if (startImmediately) {
      await runAiTestingTask(taskResponse.data.id, { start_immediately: true })
      activeTab.value = 'runs'
      ElMessage.success('AI testing task started')
    } else {
      ElMessage.success('AI testing task created')
    }
    showTaskDialog.value = false
    await Promise.all([fetchSummary(), fetchTasks(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to create AI testing task')
  } finally {
    submitting.value = false
  }
}

const handleQueueRun = async (task) => {
  try {
    await runAiTestingTask(task.id, { start_immediately: false })
    activeTab.value = 'runs'
    ElMessage.success('Run queued')
    await Promise.all([fetchSummary(), fetchTasks(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to queue run')
  }
}

const handleStartRun = async (task) => {
  runningTasks.value = {
    ...runningTasks.value,
    [task.id]: true
  }
  try {
    await runAiTestingTask(task.id, { start_immediately: true })
    activeTab.value = 'runs'
    ElMessage.success('Run started')
    await Promise.all([fetchSummary(), fetchTasks(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to start run')
  } finally {
    runningTasks.value = {
      ...runningTasks.value,
      [task.id]: false
    }
  }
}

const handleRunQueue = async () => {
  queueRunning.value = true
  try {
    const response = await runPendingAiTestingRuns({ limit: 5 })
    ElMessage.success(`Queue finished: ${response.data.succeeded || 0} succeeded, ${response.data.failed || 0} failed`)
    activeTab.value = 'runs'
    await Promise.all([fetchSummary(), fetchTasks(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to run AI testing queue')
  } finally {
    queueRunning.value = false
  }
}

const handleStartQueuedRun = async (run) => {
  startingRuns.value = {
    ...startingRuns.value,
    [run.id]: true
  }
  try {
    await startAiTestingRun(run.id)
    ElMessage.success('Run started')
    await Promise.all([fetchSummary(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to start queued run')
  } finally {
    startingRuns.value = {
      ...startingRuns.value,
      [run.id]: false
    }
  }
}

const handleCancelRun = async (run) => {
  cancellingRuns.value = {
    ...cancellingRuns.value,
    [run.id]: true
  }
  try {
    await cancelAiTestingRun(run.id)
    ElMessage.success('Run cancelled')
    await Promise.all([fetchSummary(), fetchRuns()])
  } catch (error) {
    ElMessage.error('Failed to cancel run')
  } finally {
    cancellingRuns.value = {
      ...cancellingRuns.value,
      [run.id]: false
    }
  }
}

const openRunDrawer = (run) => {
  selectedRun.value = run
  showRunDrawer.value = true
}

const artifactList = (run, key) => {
  const value = run?.artifacts?.[key]
  return Array.isArray(value) ? value : []
}

const normalizeArtifactPath = (value) => {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }
  if (/^https?:\/\//i.test(text) || text.startsWith('/')) {
    return text
  }
  if (text.startsWith('media/')) {
    return `/${text}`
  }
  return text
}

const evidenceKind = (url, fallback = 'data') => {
  const text = String(url || '').toLowerCase()
  if (/\.(png|jpe?g|webp|bmp|tiff?)($|\?)/.test(text)) {
    return 'image'
  }
  if (/\.gif($|\?)/.test(text)) {
    return 'gif'
  }
  if (/\.(html?|htm)($|\?)/.test(text)) {
    return 'html'
  }
  return fallback
}

const normalizeEvidenceItem = (raw, key, index, group) => {
  if (typeof raw === 'string') {
    const url = normalizeArtifactPath(raw)
    return {
      key: `${group}-${index}`,
      group,
      label: `${groupLabel(group)} ${index + 1}`,
      title: `${groupLabel(group)} ${index + 1}`,
      kind: evidenceKind(url),
      url,
      data: raw,
      stepId: null,
      stepIndex: index + 1
    }
  }
  const item = raw && typeof raw === 'object' ? raw : { value: raw }
  const pathValue = item.url || item.path || item.file || item.href || ''
  const url = normalizeArtifactPath(pathValue)
  const title = item.title || item.name || `${groupLabel(group)} ${index + 1}`
  return {
    key: `${group}-${item.id || item.index || index}`,
    group,
    label: item.label || title,
    title,
    kind: url ? evidenceKind(url) : 'data',
    url,
    data: item,
    stepId: item.task_id || item.step_id || item.id || null,
    stepIndex: item.index || item.step_index || index + 1
  }
}

const groupLabel = (group) => {
  const labels = {
    screenshots: 'Screenshot',
    recordings: 'Recording',
    reports: 'Report',
    history_steps: 'History'
  }
  return labels[group] || 'Evidence'
}

const evidenceItems = (run, group = null) => {
  if (!run) {
    return []
  }
  const groups = group ? [group] : ['screenshots', 'recordings', 'reports', 'history_steps']
  return groups.flatMap(name => artifactList(run, name).map((item, index) => normalizeEvidenceItem(item, `${name}-${index}`, index, name)))
}

const stepEvidence = (run, step) => {
  const stepId = step?.id || step?.task_id
  const stepIndex = step?.index
  return evidenceItems(run).filter(item => {
    return (stepId && String(item.stepId) === String(stepId)) ||
      (stepIndex && Number(item.stepIndex) === Number(stepIndex))
  })
}

const openEvidence = (item) => {
  selectedEvidence.value = item
  showEvidenceDialog.value = true
}

const openEvidenceGroup = (group) => {
  const first = evidenceItems(selectedRun.value, group)[0]
  if (first) {
    openEvidence(first)
  }
}

const evidenceText = (item) => {
  if (!item) {
    return ''
  }
  if (typeof item.data === 'string') {
    return item.data
  }
  return JSON.stringify(item.data, null, 2)
}

const firstFailedStep = (run) => {
  return (run?.planned_steps || []).find(step => step.status === 'failed') || null
}

const plannedStepRowClass = ({ row }) => {
  if (row.status === 'failed') {
    return 'is-failed-step'
  }
  const failed = firstFailedStep(selectedRun.value)
  if (failed && (failed.id === row.id || failed.index === row.index)) {
    return 'is-failed-step'
  }
  return ''
}

const runDiagnosis = (run) => {
  if (!run) {
    return ''
  }
  if (run.error_message) {
    return run.error_message
  }
  const failedStep = (run.planned_steps || []).find(step => step.status === 'failed')
  if (failedStep) {
    return `Step ${failedStep.index || failedStep.id || ''} failed: ${failedStep.title || failedStep.description || 'check execution evidence and logs'}.`
  }
  const activeSteps = (run.planned_steps || []).filter(step => ['pending', 'in_progress', 'running'].includes(step.status))
  if (run.status === 'failed' && activeSteps.length) {
    return `${activeSteps.length} step(s) did not finish before the run ended.`
  }
  if (run.status === 'succeeded') {
    return 'All planned steps finished successfully.'
  }
  return ''
}

onMounted(() => {
  loadPage()
  refreshTimer = window.setInterval(refreshRunsIfNeeded, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<style scoped lang="scss">
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
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

.drawer-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
}

.section-title {
  margin: 18px 0 12px;
  font-size: 15px;
  font-weight: 600;
}

.table-toolbar {
  display: grid;
  gap: 10px;
  margin-bottom: 12px;

  :deep(.el-select),
  :deep(.el-input) {
    width: 100%;
  }
}

.task-toolbar,
.run-toolbar {
  grid-template-columns: minmax(150px, 1fr) minmax(120px, 160px) minmax(120px, 160px) minmax(180px, 1.3fr) auto;
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.evidence-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;

  &:hover {
    border-color: var(--el-color-primary-light-5);
    background: var(--el-color-primary-light-9);
  }

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

.muted-text {
  color: var(--el-text-color-secondary);
}

:deep(.is-failed-step) {
  --el-table-tr-bg-color: var(--el-color-danger-light-9);
}

.evidence-media,
.evidence-frame {
  display: block;
  width: 100%;
  max-height: 70vh;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  object-fit: contain;
}

.evidence-frame {
  height: 70vh;
}

.evidence-json {
  max-height: 70vh;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  line-height: 1.55;
}

.diagnosis-panel {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-lighter);

  p {
    margin: 6px 0 0;
    color: var(--el-text-color-regular);
    line-height: 1.55;
  }
}

.diagnosis-panel.is-failed {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.run-logs {
  min-height: 220px;
  max-height: 420px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-primary);
  padding: 12px;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  line-height: 1.55;
}

@media (max-width: 1200px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .task-toolbar,
  .run-toolbar,
  .evidence-grid {
    grid-template-columns: 1fr;
  }
}
</style>
