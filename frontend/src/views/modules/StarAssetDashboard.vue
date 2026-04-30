<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">Unified Assets</h1>
        <p class="page-subtitle">Test cases, suites, and reviews across accessible projects</p>
      </div>
      <div class="header-actions">
        <el-button :disabled="!rows.length" @click="exportRows">
          <el-icon><Download /></el-icon>
          Export
        </el-button>
        <el-button :loading="loading" @click="loadPage">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Test Cases</div>
        <div class="metric-value">{{ summary.testcases?.total || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Active Cases</div>
        <div class="metric-value">{{ summary.testcases?.active || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Suites</div>
        <div class="metric-value">{{ summary.testsuites?.total || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Pending Reviews</div>
        <div class="metric-value">{{ summary.reviews?.pending || 0 }}</div>
      </div>
    </div>

    <div class="card-container">
      <el-tabs v-model="activeTab" @tab-change="fetchRows">
        <el-tab-pane label="Test Cases" name="testcases" />
        <el-tab-pane label="Test Suites" name="testsuites" />
        <el-tab-pane label="Reviews" name="reviews" />
      </el-tabs>

      <div class="asset-toolbar">
        <el-input
          v-model="filters.search"
          clearable
          placeholder="Search title"
          style="width: 220px"
          @keyup.enter="fetchRows"
          @clear="fetchRows"
        />
        <el-select v-model="filters.source_module" clearable placeholder="Module" style="width: 170px" @change="fetchRows">
          <el-option label="Manual" value="manual" />
          <el-option label="AI Testing" value="ai_testing" />
          <el-option label="API Testing" value="api_testing" />
          <el-option label="UI Automation" value="ui_automation" />
          <el-option label="APP Automation" value="app_automation" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="Status" style="width: 140px" @change="fetchRows">
          <el-option label="Draft" value="draft" />
          <el-option label="Ready" value="ready" />
          <el-option label="Active" value="active" />
          <el-option label="Pending" value="pending" />
          <el-option label="Approved" value="approved" />
          <el-option label="Rejected" value="rejected" />
          <el-option label="Failed" value="failed" />
          <el-option label="Passed" value="passed" />
        </el-select>
        <el-button type="primary" @click="openNativeView">
          <el-icon><Position /></el-icon>
          Open Module
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" style="width: 100%" @row-dblclick="openDetail">
        <el-table-column prop="title" label="Title" min-width="240" show-overflow-tooltip />
        <el-table-column prop="project_name" label="Project" min-width="180" show-overflow-tooltip />
        <el-table-column prop="module" label="Module" width="150">
          <template #default="{ row }">
            <el-tag :type="getModuleTagType(row.module)">{{ getModuleText(row.module) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="Status" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status || '--' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="Priority" width="120">
          <template #default="{ row }">{{ row.priority || '--' }}</template>
        </el-table-column>
        <el-table-column prop="type" label="Type" width="130" />
        <el-table-column prop="owner" label="Owner" width="140" show-overflow-tooltip />
        <el-table-column label="Related" width="110">
          <template #default="{ row }">
            {{ getRelatedCount(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="Updated" width="170">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="Actions" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">
              Detail
            </el-button>
            <el-button size="small" :disabled="!row.native_url" @click="openNativeAsset(row)">
              Open
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="showDetailDrawer" size="52%" title="Asset Detail">
      <div v-loading="detailLoading" class="detail-drawer">
        <template v-if="assetDetail">
          <div class="detail-header">
            <div>
              <h2>{{ assetDetail.title }}</h2>
              <p>{{ assetDetail.asset_key }}</p>
            </div>
            <div class="detail-actions">
              <el-button :disabled="!assetDetail.native_url" @click="openNativeAsset(assetDetail)">Open Source</el-button>
              <el-button
                v-if="assetDetail.asset_type === 'testcase' && assetDetail.module !== 'manual'"
                type="primary"
                :loading="adopting"
                @click="adoptAsset"
              >
                Adopt
              </el-button>
            </div>
          </div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Project">{{ assetDetail.project_name }}</el-descriptions-item>
            <el-descriptions-item label="Module">{{ getModuleText(assetDetail.module) }}</el-descriptions-item>
            <el-descriptions-item label="Status">{{ assetDetail.status || '--' }}</el-descriptions-item>
            <el-descriptions-item label="Priority">{{ assetDetail.priority || '--' }}</el-descriptions-item>
            <el-descriptions-item label="Updated">{{ formatDate(assetDetail.updated_at) }}</el-descriptions-item>
            <el-descriptions-item label="Snapshots">{{ assetDetail.snapshots?.length || 0 }}</el-descriptions-item>
          </el-descriptions>

          <div class="section-title">Payload</div>
          <pre class="json-block">{{ formatJson(assetDetail.latest_payload) }}</pre>

          <div class="section-title">Snapshots</div>
          <el-table :data="assetDetail.snapshots || []" size="small" style="width: 100%">
            <el-table-column prop="snapshot_hash" label="Hash" min-width="260" show-overflow-tooltip />
            <el-table-column prop="created_by" label="By" width="140" />
            <el-table-column prop="created_at" label="Created" width="170">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
          </el-table>

          <template v-if="assetDetail.snapshot_diff?.length">
            <div class="section-title">Latest Diff</div>
            <pre class="json-block">{{ assetDetail.snapshot_diff.join('\n') }}</pre>
          </template>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Position, Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { adoptStarAsset, getStarAssetDetail, getStarAssetList, getStarAssetSummary } from '@/api/core'

const router = useRouter()
const loading = ref(false)
const activeTab = ref('testcases')
const summary = ref({})
const rows = ref([])
const filters = reactive({
  search: '',
  source_module: '',
  status: ''
})
const showDetailDrawer = ref(false)
const detailLoading = ref(false)
const adopting = ref(false)
const assetDetail = ref(null)

const formatDate = (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--')
const formatJson = (value) => JSON.stringify(value || {}, null, 2)

const getModuleText = (module) => {
  const textMap = {
    manual: 'Manual',
    ai_testing: 'AI Testing',
    api_testing: 'API Testing',
    ui_automation: 'UI Automation',
    app_automation: 'APP Automation'
  }
  return textMap[module] || module || '--'
}

const getModuleTagType = (module) => {
  const typeMap = {
    manual: '',
    ai_testing: 'success',
    api_testing: 'warning',
    ui_automation: 'primary',
    app_automation: 'info'
  }
  return typeMap[module] || 'info'
}

const getRelatedCount = (row) => {
  if (row.asset_type === 'testcase') {
    return row.step_count || row.version_count || row.run_count || 0
  }
  if (row.asset_type === 'testsuite') {
    return row.case_count || row.script_count || 0
  }
  return row.reviewer_count || 0
}

const getStatusType = (status) => {
  const typeMap = {
    active: 'success',
    approved: 'success',
    pending: 'warning',
    in_progress: 'warning',
    rejected: 'danger',
    deprecated: 'info',
    draft: 'info'
  }
  return typeMap[String(status || '').toLowerCase()] || 'info'
}

const fetchSummary = async () => {
  const response = await getStarAssetSummary()
  summary.value = response.data || {}
}

const fetchRows = async () => {
  const params = { limit: 100 }
  Object.entries(filters).forEach(([key, value]) => {
    if (value) {
      params[key] = value
    }
  })
  const response = await getStarAssetList(activeTab.value, params)
  rows.value = Array.isArray(response.data) ? response.data : []
}

const loadPage = async () => {
  loading.value = true
  try {
    await Promise.all([fetchSummary(), fetchRows()])
  } catch (error) {
    ElMessage.error('Failed to load unified assets')
  } finally {
    loading.value = false
  }
}

const openNativeView = () => {
  const routeMap = {
    testcases: '/ai-generation/testcases',
    testsuites: '/ai-generation/testsuites',
    reviews: '/ai-generation/reviews'
  }
  router.push(routeMap[activeTab.value])
}

const openNativeAsset = (row) => {
  if (row?.native_url) {
    router.push(row.native_url)
  }
}

const openDetail = async (row) => {
  if (!row?.asset_id) {
    return
  }
  showDetailDrawer.value = true
  detailLoading.value = true
  try {
    const response = await getStarAssetDetail(row.asset_id)
    assetDetail.value = response.data
  } catch (error) {
    ElMessage.error('Failed to load asset detail')
  } finally {
    detailLoading.value = false
  }
}

const adoptAsset = async () => {
  if (!assetDetail.value?.asset_id) {
    return
  }
  adopting.value = true
  try {
    const response = await adoptStarAsset(assetDetail.value.asset_id)
    ElMessage.success('Asset adopted as manual test case')
    showDetailDrawer.value = false
    await Promise.all([fetchSummary(), fetchRows()])
    if (response.data?.native_url) {
      router.push(response.data.native_url)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || 'Failed to adopt asset')
  } finally {
    adopting.value = false
  }
}

const escapeCsv = (value) => {
  const text = String(value ?? '')
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const exportRows = () => {
  const headers = ['Title', 'Project', 'Module', 'Status', 'Priority', 'Type', 'Owner', 'Updated', 'Asset Key']
  const body = rows.value.map(row => [
    row.title,
    row.project_name,
    getModuleText(row.module),
    row.status,
    row.priority,
    row.type,
    row.owner,
    formatDate(row.updated_at),
    row.asset_key
  ])
  const csv = [headers, ...body].map(line => line.map(escapeCsv).join(',')).join('\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `unified-assets-${activeTab.value}.csv`
  link.click()
  URL.revokeObjectURL(url)
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

.header-actions {
  display: flex;
  gap: 10px;
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

.asset-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-bottom: 12px;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;

  h2 {
    margin: 0 0 6px;
    font-size: 20px;
  }

  p {
    margin: 0;
    color: var(--el-text-color-secondary);
  }
}

.detail-actions {
  display: flex;
  gap: 10px;
}

.section-title {
  margin: 18px 0 10px;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.json-block {
  max-height: 360px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 768px) {
  .page-header,
  .header-actions,
  .asset-toolbar,
  .detail-header,
  .detail-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .asset-toolbar {
    justify-content: flex-start;
  }
}
</style>
