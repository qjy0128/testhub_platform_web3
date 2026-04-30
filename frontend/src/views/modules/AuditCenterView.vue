<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">Audit Center</h1>
        <p class="page-subtitle">Unified operational audit timeline across modules.</p>
      </div>
      <div class="header-actions">
        <el-button :loading="exporting" @click="handleExport">
          Export CSV
        </el-button>
        <el-button :loading="loading" @click="loadPage">
          Refresh
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Logs</div>
        <div class="metric-value">{{ summary.total || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Domains</div>
        <div class="metric-value">{{ Object.keys(summary.domains || {}).length }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Actions</div>
        <div class="metric-value">{{ Object.keys(summary.actions || {}).length }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Modules</div>
        <div class="metric-value">{{ Object.keys(summary.modules || {}).length }}</div>
      </div>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="12">
          <el-col :xl="4" :lg="6" :md="8" :sm="12">
            <el-select v-model="filters.project_id" clearable filterable placeholder="Project" @change="handleSearch">
              <el-option v-for="item in projectOptions" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="6" :md="8" :sm="12">
            <el-select v-model="filters.domain" clearable filterable placeholder="Domain" @change="handleSearch">
              <el-option v-for="item in domainOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="6" :md="8" :sm="12">
            <el-select v-model="filters.action" clearable filterable placeholder="Action" @change="handleSearch">
              <el-option v-for="item in actionOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-col>
          <el-col :xl="4" :lg="6" :md="8" :sm="12">
            <el-select v-model="filters.module" clearable filterable placeholder="Module" @change="handleSearch">
              <el-option v-for="item in moduleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-col>
          <el-col :xl="5" :lg="8" :md="12" :sm="24">
            <el-date-picker
              v-model="filters.dateRange"
              type="datetimerange"
              range-separator="to"
              start-placeholder="From"
              end-placeholder="To"
              value-format="YYYY-MM-DDTHH:mm:ss"
              @change="handleSearch"
            />
          </el-col>
          <el-col :xl="3" :lg="6" :md="12" :sm="24">
            <el-input v-model="filters.search" placeholder="Search summary/target" clearable @keyup.enter="handleSearch" />
          </el-col>
        </el-row>
      </div>

      <el-table v-loading="loading" :data="logs" style="width: 100%" row-key="id">
        <el-table-column label="Time" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="domain" label="Domain" width="140" />
        <el-table-column prop="action" label="Action" width="120">
          <template #default="{ row }">
            <el-tag effect="plain">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="module" label="Module" width="150">
          <template #default="{ row }">{{ row.module || '--' }}</template>
        </el-table-column>
        <el-table-column prop="project_name" label="Project" min-width="180" show-overflow-tooltip />
        <el-table-column prop="actor_username" label="Actor" width="130">
          <template #default="{ row }">{{ row.actor_username || '--' }}</template>
        </el-table-column>
        <el-table-column prop="object_name" label="Target" min-width="220" show-overflow-tooltip />
        <el-table-column prop="summary" label="Summary" min-width="260" show-overflow-tooltip />
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="pagination.total"
          :page-size="pagination.page_size"
          :page-sizes="[20, 50, 100]"
          :current-page="pagination.page"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import {
  exportUnifiedAuditLogs,
  getUnifiedAuditLogs,
  getUnifiedAuditLogSummary,
  getUnifiedProjects
} from '@/api/core'

const loading = ref(false)
const exporting = ref(false)
const logs = ref([])
const summary = ref({})
const projectOptions = ref([])
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})
const filters = reactive({
  project_id: '',
  domain: '',
  action: '',
  module: '',
  search: '',
  dateRange: []
})

const domainOptions = computed(() => {
  return Object.keys(summary.value.domains || {}).map(key => ({ value: key, label: `${key} (${summary.value.domains[key]})` }))
})

const actionOptions = computed(() => {
  return Object.keys(summary.value.actions || {}).map(key => ({ value: key, label: `${key} (${summary.value.actions[key]})` }))
})

const moduleOptions = computed(() => {
  return Object.keys(summary.value.modules || {})
    .filter(key => key && key !== '-')
    .map(key => ({ value: key, label: `${key} (${summary.value.modules[key]})` }))
})

const formatDate = (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--')

const buildParams = () => {
  const params = {
    page: pagination.page,
    page_size: pagination.page_size
  }
  if (filters.project_id) params.project_id = filters.project_id
  if (filters.domain) params.domain = filters.domain
  if (filters.action) params.action = filters.action
  if (filters.module) params.module = filters.module
  if (filters.search) params.search = filters.search
  if (filters.dateRange?.length === 2) {
    params.created_at_after = filters.dateRange[0]
    params.created_at_before = filters.dateRange[1]
  }
  return params
}

const loadProjects = async () => {
  const response = await getUnifiedProjects({ page: 1, page_size: 200 })
  projectOptions.value = Array.isArray(response.data?.results) ? response.data.results : (response.data || [])
}

const loadSummary = async () => {
  const response = await getUnifiedAuditLogSummary(buildParams())
  summary.value = response.data || {}
}

const loadLogs = async () => {
  loading.value = true
  try {
    const response = await getUnifiedAuditLogs(buildParams())
    logs.value = Array.isArray(response.data?.results) ? response.data.results : (response.data || [])
    pagination.total = Number(response.data?.count || logs.value.length || 0)
  } catch (error) {
    logs.value = []
    pagination.total = 0
    ElMessage.error('Failed to load audit logs.')
  } finally {
    loading.value = false
  }
}

const loadPage = async () => {
  try {
    await Promise.all([loadProjects(), loadSummary(), loadLogs()])
  } catch (error) {
    ElMessage.error('Failed to load audit center.')
  }
}

const handleSearch = async () => {
  pagination.page = 1
  await Promise.all([loadSummary(), loadLogs()])
}

const handlePageChange = async (page) => {
  pagination.page = page
  await loadLogs()
}

const handleSizeChange = async (size) => {
  pagination.page_size = size
  pagination.page = 1
  await loadLogs()
}

const handleExport = async () => {
  exporting.value = true
  try {
    const response = await exportUnifiedAuditLogs(buildParams())
    const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.href = url
    link.download = `audit_logs_${dayjs().format('YYYYMMDD_HHmmss')}.csv`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error('Failed to export audit logs.')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await loadPage()
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

.filter-bar {
  margin-bottom: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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
}
</style>
