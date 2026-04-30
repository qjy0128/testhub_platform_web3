<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">Module Map</h1>
        <p class="page-subtitle">TestHub Star Edition</p>
      </div>
      <el-button :loading="loading" @click="loadPage">
        <el-icon><Refresh /></el-icon>
        Refresh
      </el-button>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Available Modules</div>
        <div class="metric-value">{{ availableModuleCount }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Unified Projects</div>
        <div class="metric-value">{{ projectCount }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Scheduled Jobs</div>
        <div class="metric-value">{{ scheduledJobCount }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">OCR Linked Docs</div>
        <div class="metric-value">{{ knowledgeSummary.ocr_linked_documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Knowledge Docs</div>
        <div class="metric-value">{{ knowledgeSummary.documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">OCR Pages</div>
        <div class="metric-value">{{ ocrSummary.pages || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">OCR Tasks</div>
        <div class="metric-value">{{ ocrSummary.tasks || 0 }}</div>
      </div>
    </div>

    <div class="card-container" v-loading="loading">
      <div class="toolbar">
        <el-segmented v-model="activeCategory" :options="categoryOptions" />
      </div>

      <div class="module-grid">
        <div
          v-for="module in filteredModules"
          :key="module.key"
          class="module-card"
          :class="{ planned: module.status !== 'available' }"
        >
          <div class="module-card-header">
            <div class="module-icon">
              <el-icon><component :is="getModuleIcon(module.key)" /></el-icon>
            </div>
            <div class="module-title">
              <h2>{{ module.display_name }}</h2>
              <div class="module-meta">
                <el-tag size="small" :type="module.tag_type || 'info'">{{ module.category }}</el-tag>
                <el-tag size="small" :type="getStatusType(module.status)">
                  {{ module.status }}
                </el-tag>
              </div>
            </div>
          </div>

          <p class="module-description">{{ module.description }}</p>

          <div v-if="getModuleStats(module.key).length" class="module-stats">
            <div v-for="stat in getModuleStats(module.key)" :key="stat.label" class="module-stat">
              <span>{{ stat.label }}</span>
              <strong>{{ stat.value }}</strong>
            </div>
          </div>

          <div class="module-flags">
            <span v-if="module.star_module">Star</span>
            <span v-if="module.supports_project_binding">Project Binding</span>
            <span v-if="module.supports_scheduled_jobs">Scheduler</span>
          </div>

          <div class="module-actions">
            <el-button
              type="primary"
              size="small"
              :disabled="!module.frontend_path || module.status !== 'available'"
              @click="openModule(module)"
            >
              Open
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  AlarmClock,
  Collection,
  Cpu,
  DataAnalysis,
  Document,
  Files,
  Folder,
  MagicStick,
  Monitor,
  Refresh,
  Search,
  View
} from '@element-plus/icons-vue'
import { getProjectModuleCatalog, getUnifiedProjects, getUnifiedScheduledJobs } from '@/api/core'
import { getKnowledgeBaseSummary } from '@/api/knowledge-base'
import { getOcrServiceSummary } from '@/api/ocr-service'

const router = useRouter()
const loading = ref(false)
const modules = ref([])
const activeCategory = ref('all')
const projectCount = ref(0)
const scheduledJobCount = ref(0)
const knowledgeSummary = reactive({})
const ocrSummary = reactive({})

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

const availableModuleCount = computed(() => {
  return modules.value.filter(module => module.status === 'available').length
})

const categoryOptions = computed(() => {
  const categories = Array.from(new Set(modules.value.map(module => module.category))).filter(Boolean)
  return [
    { label: 'All', value: 'all' },
    ...categories.map(category => ({ label: category, value: category }))
  ]
})

const filteredModules = computed(() => {
  if (activeCategory.value === 'all') {
    return modules.value
  }
  return modules.value.filter(module => module.category === activeCategory.value)
})

const getStatusType = (status) => {
  return status === 'available' ? 'success' : 'info'
}

const getModuleIcon = (moduleKey) => {
  const iconMap = {
    api_testing: DataAnalysis,
    ui_automation: Monitor,
    app_automation: View,
    ai_testing: MagicStick,
    knowledge_base: Files,
    ocr_service: Search,
    scheduler: AlarmClock,
    testcases: Document,
    testsuites: Collection,
    reviews: Cpu,
    unified_projects: Folder
  }
  return iconMap[moduleKey] || Folder
}

const getModuleStats = (moduleKey) => {
  const statMap = {
    knowledge_base: [
      { label: 'Docs', value: knowledgeSummary.documents || 0 },
      { label: 'OCR Linked', value: knowledgeSummary.ocr_linked_documents || 0 },
      { label: 'Chunks', value: knowledgeSummary.chunks || 0 }
    ],
    ocr_service: [
      { label: 'Tasks', value: ocrSummary.tasks || 0 },
      { label: 'Pages', value: ocrSummary.pages || 0 },
      { label: 'Failed', value: ocrSummary.failed_tasks || 0 }
    ],
    scheduler: [
      { label: 'Jobs', value: scheduledJobCount.value }
    ],
    unified_projects: [
      { label: 'Projects', value: projectCount.value }
    ]
  }
  return statMap[moduleKey] || []
}

const openModule = (module) => {
  if (module.frontend_path && module.status === 'available') {
    router.push(getModuleRoute(module))
  }
}

const getModuleRoute = (module) => {
  const queryMap = {
    knowledge_base: { tab: 'documents' },
    ocr_service: { tab: 'tasks' },
    scheduler: { status: 'enabled' }
  }
  return {
    path: module.frontend_path,
    query: queryMap[module.key] || {}
  }
}

const applySummary = (target, payload) => {
  Object.keys(target).forEach(key => delete target[key])
  Object.assign(target, payload || {})
}

const loadPage = async () => {
  loading.value = true
  try {
    const [
      moduleResponse,
      projectResponse,
      jobResponse,
      knowledgeResponse,
      ocrResponse
    ] = await Promise.allSettled([
      getProjectModuleCatalog({ star: true }),
      getUnifiedProjects({ page: 1, page_size: 1 }),
      getUnifiedScheduledJobs(),
      getKnowledgeBaseSummary(),
      getOcrServiceSummary()
    ])

    if (moduleResponse.status === 'fulfilled') {
      modules.value = normalizeListResponse(moduleResponse.value.data).results
    }
    if (projectResponse.status === 'fulfilled') {
      projectCount.value = normalizeListResponse(projectResponse.value.data).count
    }
    if (jobResponse.status === 'fulfilled') {
      scheduledJobCount.value = normalizeListResponse(jobResponse.value.data).count
    }
    if (knowledgeResponse.status === 'fulfilled') {
      applySummary(knowledgeSummary, knowledgeResponse.value.data)
    }
    if (ocrResponse.status === 'fulfilled') {
      applySummary(ocrSummary, ocrResponse.value.data)
    }
  } catch (error) {
    ElMessage.error('Failed to load module map')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPage()
})
</script>

<style scoped lang="scss">
.page-subtitle {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
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

.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.module-card {
  min-height: 220px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.module-card.planned {
  background: var(--el-fill-color-lighter);
}

.module-card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.module-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.module-title {
  min-width: 0;

  h2 {
    margin: 0 0 8px;
    font-size: 17px;
    font-weight: 600;
  }
}

.module-meta,
.module-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.module-description {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  min-height: 42px;
}

.module-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.module-stat {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 8px;
  background: var(--el-fill-color-lighter);

  span {
    display: block;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    margin-bottom: 4px;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 18px;
    line-height: 1;
  }
}

.module-flags {
  min-height: 24px;

  span {
    border: 1px solid var(--el-border-color);
    border-radius: 999px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 22px;
    padding: 0 8px;
  }
}

.module-actions {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1200px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .toolbar {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
