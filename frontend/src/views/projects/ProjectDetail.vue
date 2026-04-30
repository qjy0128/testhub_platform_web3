<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ $t('project.projectDetail') }}</h1>
        <p v-if="project" class="page-subtitle">
          {{ project.name }}
        </p>
      </div>
      <div class="header-actions">
        <el-button @click="handleRefresh" :loading="loading">
          <el-icon><Refresh /></el-icon>
          {{ $t('common.refresh') }}
        </el-button>
        <el-button type="primary" @click="router.back()">
          <el-icon><ArrowLeft /></el-icon>
          {{ $t('common.back') }}
        </el-button>
      </div>
    </div>

    <div class="card-container" v-loading="loading">
      <template v-if="project">
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-label">{{ $t('project.status') }}</div>
            <div class="summary-value">
              <el-tag :type="getProjectStatusType(project.status)">
                {{ getProjectStatusText(project.status) }}
              </el-tag>
            </div>
          </div>
          <div class="summary-item">
            <div class="summary-label">{{ $t('project.boundModules') }}</div>
            <div class="summary-number">{{ project.module_summary?.total || 0 }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">{{ $t('project.scheduledJobs') }}</div>
            <div class="summary-number">{{ project.scheduled_job_summary?.total || 0 }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">{{ $t('project.activeScheduledJobs') }}</div>
            <div class="summary-number">{{ project.scheduled_job_summary?.active || 0 }}</div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane :label="$t('project.projectInfo')" name="info">
            <el-descriptions :column="2" border>
              <el-descriptions-item :label="$t('project.projectName')">{{ project.name }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.status')">
                <el-tag :type="getProjectStatusType(project.status)">
                  {{ getProjectStatusText(project.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('project.owner')">{{ project.owner?.username || '--' }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.createdAt')">{{ formatDate(project.created_at) }}</el-descriptions-item>
              <el-descriptions-item :label="$t('project.projectDescription')" :span="2">
                {{ project.description || $t('project.noDescription') }}
              </el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane label="Meta Project Tree" name="meta">
            <div class="tab-toolbar">
              <div class="binding-summary">
                <el-tag type="success">Root {{ project.meta_project ? 1 : 0 }}</el-tag>
                <el-tag>Modules {{ project.meta_project?.children?.length || 0 }}</el-tag>
              </div>
              <el-button v-if="canManageProject" @click="syncMetaTree">
                <el-icon><RefreshRight /></el-icon>
                Sync Tree
              </el-button>
            </div>
            <el-tree
              v-if="project.meta_project"
              class="meta-project-tree"
              :data="[project.meta_project]"
              node-key="id"
              default-expand-all
              :expand-on-click-node="false"
            >
              <template #default="{ data }">
                <div class="meta-node">
                  <el-tag size="small" :type="getMetaNodeTagType(data)">
                    {{ getMetaNodeTypeText(data) }}
                  </el-tag>
                  <span class="meta-node-title">{{ data.name }}</span>
                  <span v-if="data.module" class="meta-node-meta">
                    {{ data.module_display || getModuleText(data.module) }} #{{ data.object_id }}
                  </span>
                </div>
              </template>
            </el-tree>
            <el-empty v-else description="No meta project tree" />
          </el-tab-pane>

          <el-tab-pane :label="$t('project.projectMembers')" name="members">
            <div class="tab-toolbar">
              <el-button type="primary" :disabled="!canManageProject">
                {{ $t('project.addMember') }}
              </el-button>
            </div>
            <el-table :data="project.members || []" style="width: 100%">
              <el-table-column prop="user.username" :label="$t('project.username')" min-width="160" />
              <el-table-column prop="user.email" :label="$t('project.email')" min-width="200" />
              <el-table-column prop="role" :label="$t('project.role')" min-width="120" />
              <el-table-column prop="joined_at" :label="$t('project.joinedAt')" min-width="180">
                <template #default="{ row }">
                  {{ formatDate(row.joined_at) }}
                </template>
              </el-table-column>
              <el-table-column :label="$t('project.actions')" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="danger"
                    :disabled="!canManageProject"
                    @click="removeMember(row)"
                  >
                    {{ $t('common.delete') }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="$t('project.environments')" name="environments">
            <div class="tab-toolbar">
              <el-button type="primary" :disabled="!canManageProject">
                {{ $t('project.addEnvironment') }}
              </el-button>
            </div>
            <el-table :data="project.environments || []" style="width: 100%">
              <el-table-column prop="name" :label="$t('project.environmentName')" min-width="180" />
              <el-table-column prop="base_url" :label="$t('project.baseUrl')" min-width="220" />
              <el-table-column prop="description" :label="$t('project.description')" min-width="220" show-overflow-tooltip />
              <el-table-column prop="is_default" :label="$t('project.defaultEnvironment')" width="140">
                <template #default="{ row }">
                  <el-tag v-if="row.is_default" type="success">{{ $t('project.yes') }}</el-tag>
                  <span v-else>{{ $t('project.no') }}</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="$t('project.moduleBindings')" name="modules">
            <div class="tab-toolbar">
              <div class="binding-summary">
                <el-tag
                  v-for="module in getBoundModuleTags(project)"
                  :key="module.module"
                  :type="getModuleTagType(module)"
                >
                  {{ module.module_display || getModuleText(module.module) }} {{ project.module_summary?.[module.module] || 0 }}
                </el-tag>
              </div>
              <el-button v-if="canManageProject" type="primary" @click="openBindingDialog">
                <el-icon><Plus /></el-icon>
                {{ $t('project.addModuleBinding') }}
              </el-button>
            </div>
            <template v-if="project.modules?.length">
              <el-table :data="project.modules" style="width: 100%">
                <el-table-column :label="$t('project.moduleType')" min-width="160">
                  <template #default="{ row }">
                    <el-tag :type="getModuleTagType(row)">
                      {{ row.module_display || getModuleText(row.module) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="module_name" :label="$t('project.moduleName')" min-width="240" />
                <el-table-column prop="object_id" :label="$t('project.moduleObjectId')" width="120" />
                <el-table-column :label="$t('project.primaryBinding')" width="140">
                  <template #default="{ row }">
                    <el-tag v-if="row.is_primary" type="success">{{ $t('project.yes') }}</el-tag>
                    <span v-else>{{ $t('project.no') }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('project.createdAt')" min-width="180">
                  <template #default="{ row }">
                    {{ formatDate(row.created_at) }}
                  </template>
                </el-table-column>
                <el-table-column v-if="canManageProject" :label="$t('project.actions')" width="120" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      size="small"
                      type="danger"
                      @click="removeModuleBinding(row)"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>
            <el-empty v-else :description="$t('project.noModules')" />
          </el-tab-pane>

          <el-tab-pane :label="$t('project.scheduledJobs')" name="jobs">
            <div class="jobs-header">
              <div class="binding-summary">
                <el-tag>{{ $t('project.scheduledJobs') }} {{ project.scheduled_job_summary?.total || 0 }}</el-tag>
                <el-tag type="success">{{ $t('project.active') }} {{ project.scheduled_job_summary?.active || 0 }}</el-tag>
                <el-tag type="warning">{{ $t('project.paused') }} {{ project.scheduled_job_summary?.paused || 0 }}</el-tag>
                <el-tag type="danger">{{ $t('project.failedJobs') }} {{ project.scheduled_job_summary?.failed || 0 }}</el-tag>
              </div>
              <el-button @click="fetchScheduledJobs" :loading="jobsLoading">
                <el-icon><RefreshRight /></el-icon>
                {{ $t('common.refresh') }}
              </el-button>
            </div>

            <el-table v-if="scheduledJobs.length" :data="scheduledJobs" v-loading="jobsLoading" style="width: 100%">
              <el-table-column prop="name" :label="$t('project.jobName')" min-width="220" show-overflow-tooltip />
              <el-table-column :label="$t('project.moduleType')" width="150">
                <template #default="{ row }">
                  <el-tag :type="getModuleTagType(row)">{{ row.module_display || getModuleText(row.module) }}</el-tag>
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
              <el-table-column v-if="canManageProject" :label="$t('project.actions')" width="240" fixed="right">
                <template #default="{ row }">
                  <div class="job-actions">
                    <el-button
                      size="small"
                      type="primary"
                      :loading="isActionLoading(row, 'run')"
                      @click="handleJobAction(row, 'run')"
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
            <el-empty v-else :description="$t('project.noScheduledJobs')" />
          </el-tab-pane>

          <el-tab-pane label="Permission Matrix" name="permissions">
            <div class="tab-toolbar">
              <div class="binding-summary">
                <el-tag>{{ permissionPolicies.length }} policies</el-tag>
                <el-tag type="success">{{ permissionPolicies.filter(item => item.is_active).length }} active</el-tag>
              </div>
              <el-button v-if="canManageProject" type="primary" @click="openPolicyDialog()">
                <el-icon><Plus /></el-icon>
                Add Policy
              </el-button>
            </div>
            <el-table :data="permissionPolicies" style="width: 100%">
              <el-table-column label="Module" min-width="160">
                <template #default="{ row }">
                  <el-tag :type="row.module === '*' ? 'info' : getModuleTagType(row.module)">
                    {{ row.module === '*' ? 'All Modules' : getModuleText(row.module) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="action" label="Action" min-width="190" />
              <el-table-column label="Allowed Roles" min-width="220">
                <template #default="{ row }">
                  <div class="binding-summary no-margin">
                    <el-tag v-for="role in row.allowed_roles || []" :key="`${row.id}-${role}`" size="small">
                      {{ role }}
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="Active" width="120">
                <template #default="{ row }">
                  <el-switch
                    :model-value="row.is_active"
                    :disabled="!canManageProject"
                    :loading="isPolicyLoading(row, 'toggle')"
                    @change="handleTogglePolicy(row, $event)"
                  />
                </template>
              </el-table-column>
              <el-table-column prop="description" label="Description" min-width="220" show-overflow-tooltip />
              <el-table-column label="Actions" width="160" fixed="right">
                <template #default="{ row }">
                  <div class="job-actions">
                    <el-button
                      size="small"
                      :disabled="!canManageProject"
                      @click="openPolicyDialog(row)"
                    >
                      Edit
                    </el-button>
                    <el-button
                      size="small"
                      type="danger"
                      :disabled="!canManageProject"
                      :loading="isPolicyLoading(row, 'delete')"
                      @click="removePolicy(row)"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!permissionPolicies.length" description="No permission policies" />
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>

    <el-dialog
      v-model="showBindingDialog"
      :title="$t('project.addModuleBinding')"
      width="520px"
      destroy-on-close
    >
      <el-form
        ref="bindingFormRef"
        :model="bindingForm"
        :rules="bindingRules"
        label-width="110px"
      >
        <el-form-item :label="$t('project.bindingModule')" prop="module">
          <el-select
            v-model="bindingForm.module"
            style="width: 100%"
            @change="handleBindingModuleChange"
          >
            <el-option
              v-for="option in moduleTypeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('project.bindingProject')" prop="object_id">
          <el-select
            v-model="bindingForm.object_id"
            style="width: 100%"
            filterable
            :loading="moduleProjectsLoading"
            :disabled="!bindingForm.module"
            :no-data-text="$t('project.noAvailableModuleProjects')"
          >
            <el-option
              v-for="option in availableModuleProjects"
              :key="option.id"
              :label="`${option.name} (#${option.id})`"
              :value="option.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showBindingDialog = false">{{ $t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="bindingSubmitting"
          @click="submitModuleBinding"
        >
          {{ $t('project.createBinding') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showPolicyDialog"
      :title="policyEditingId ? 'Edit Policy' : 'Create Policy'"
      width="560px"
      destroy-on-close
    >
      <el-form
        ref="policyFormRef"
        :model="policyForm"
        :rules="policyRules"
        label-width="120px"
      >
        <el-form-item label="Module" prop="module">
          <el-select v-model="policyForm.module" style="width: 100%">
            <el-option label="All Modules (*)" value="*" />
            <el-option
              v-for="option in moduleCatalog"
              :key="option.key"
              :label="option.display_name"
              :value="option.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Action" prop="action">
          <el-select
            v-model="policyForm.action"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
          >
            <el-option v-for="item in policyActionOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="Allowed Roles" prop="allowed_roles">
          <el-select
            v-model="policyForm.allowed_roles"
            style="width: 100%"
            multiple
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option v-for="role in policyRoleOptions" :key="role" :label="role" :value="role" />
          </el-select>
        </el-form-item>
        <el-form-item label="Description" prop="description">
          <el-input v-model="policyForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="policyForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPolicyDialog = false">{{ $t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="policySubmitting"
          @click="submitPolicy"
        >
          {{ policyEditingId ? 'Update' : 'Create' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Delete, Plus, Refresh, RefreshRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/utils/api'
import { useUserStore } from '@/stores/user'
import { getApiProjects } from '@/api/api-testing'
import { getAppProjects } from '@/api/app-automation'
import { getUiProjects } from '@/api/ui_automation'
import {
  createProjectPermissionPolicy,
  createProjectModuleBinding,
  deleteProjectPermissionPolicy,
  deleteProjectModuleBinding,
  getProjectPermissionPolicies,
  getProjectModuleCatalog,
  getUnifiedProjectDetail,
  getUnifiedScheduledJobs,
  pauseUnifiedScheduledJob,
  resumeUnifiedScheduledJob,
  runUnifiedScheduledJobNow,
  syncMetaProjectTree,
  updateProjectPermissionPolicy
} from '@/api/core'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()

const loading = ref(false)
const jobsLoading = ref(false)
const activeTab = ref('info')
const project = ref(null)
const scheduledJobs = ref([])
const permissionPolicies = ref([])
const actionLoading = ref({})
const policyLoading = ref({})
const showBindingDialog = ref(false)
const showPolicyDialog = ref(false)
const moduleProjectsLoading = ref(false)
const bindingSubmitting = ref(false)
const policySubmitting = ref(false)
const moduleCatalog = ref([])
const moduleProjectOptions = ref([])
const bindingFormRef = ref()
const policyFormRef = ref()
const policyEditingId = ref(null)
const bindingForm = ref({
  module: '',
  object_id: null
})
const policyForm = ref({
  module: '*',
  action: 'scheduler.run_now',
  allowed_roles: ['owner', 'admin'],
  description: '',
  is_active: true
})

const currentUserId = computed(() => userStore.user?.id)
const currentMemberRole = computed(() => {
  return project.value?.members?.find(member => member.user?.id === currentUserId.value)?.role || ''
})
const canManageProject = computed(() => {
  if (!project.value || !currentUserId.value) {
    return false
  }
  if (project.value.owner?.id === currentUserId.value) {
    return true
  }
  return ['owner', 'admin'].includes(String(currentMemberRole.value || '').toLowerCase())
})
const moduleTypeOptions = computed(() => {
  return moduleCatalog.value
    .filter(module => module.supports_project_binding)
    .map(module => ({
      value: module.key,
      label: module.display_name
    }))
})
const boundModuleObjectIds = computed(() => {
  const ids = {}
  for (const module of project.value?.modules || []) {
    if (!ids[module.module]) {
      ids[module.module] = new Set()
    }
    ids[module.module].add(module.object_id)
  }
  return ids
})
const availableModuleProjects = computed(() => {
  const boundIds = boundModuleObjectIds.value[bindingForm.value.module] || new Set()
  return moduleProjectOptions.value.filter(option => !boundIds.has(option.id))
})
const bindingRules = computed(() => ({
  module: [
    { required: true, message: t('project.selectModuleType'), trigger: 'change' }
  ],
  object_id: [
    { required: true, message: t('project.selectModuleProject'), trigger: 'change' }
  ]
}))
const policyRoleOptions = ['owner', 'admin', 'developer', 'tester', 'viewer']
const policyActionOptions = [
  'scheduler.pause',
  'scheduler.resume',
  'scheduler.run_now',
  'scheduler.manage_dependency',
  'scheduler.manage'
]
const policyRules = computed(() => ({
  module: [{ required: true, message: 'Select module', trigger: 'change' }],
  action: [{ required: true, message: 'Enter action', trigger: 'change' }],
  allowed_roles: [{ type: 'array', required: true, min: 1, message: 'Select at least one role', trigger: 'change' }]
}))

const formatDate = (value) => {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--'
}

const normalizeProjectStatus = (status) => {
  return String(status || '').toLowerCase()
}

const normalizeJobStatus = (status) => {
  return String(status || '').toLowerCase()
}

const getProjectStatusType = (status) => {
  const typeMap = {
    active: 'success',
    paused: 'warning',
    completed: 'info',
    archived: 'info'
  }
  return typeMap[normalizeProjectStatus(status)] || 'info'
}

const getProjectStatusText = (status) => {
  const textMap = {
    active: t('project.active'),
    paused: t('project.paused'),
    completed: t('project.completed'),
    archived: t('project.archived')
  }
  return textMap[normalizeProjectStatus(status)] || status || '--'
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

const getMetaNodeTagType = (node) => {
  if (node?.node_type === 'meta_project') {
    return 'success'
  }
  return getModuleTagType(node?.module)
}

const getMetaNodeTypeText = (node) => {
  if (node?.node_type === 'meta_project') {
    return 'Meta'
  }
  return node?.module_display || getModuleText(node?.module)
}

const getBoundModuleTags = (targetProject) => {
  const seen = new Set()
  return (targetProject?.modules || []).filter((module) => {
    if (seen.has(module.module)) {
      return false
    }
    seen.add(module.module)
    return true
  })
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

const getActionLoadingKey = (job, action) => `${job.job_key}:${action}`

const isActionLoading = (job, action) => {
  return Boolean(actionLoading.value[getActionLoadingKey(job, action)])
}

const normalizeListResponse = (payload) => {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.results)) {
    return payload.results
  }
  return []
}

const getModuleProjectFetcher = (module) => {
  const fetcherMap = {
    api_testing: getApiProjects,
    ui_automation: getUiProjects,
    app_automation: getAppProjects
  }
  return fetcherMap[module]
}

const fetchProject = async () => {
  const response = await getUnifiedProjectDetail(route.params.id)
  project.value = response.data
}

const fetchModuleCatalog = async () => {
  try {
    const response = await getProjectModuleCatalog()
    moduleCatalog.value = normalizeListResponse(response.data)
  } catch (error) {
    moduleCatalog.value = []
  }
}

const fetchScheduledJobs = async () => {
  jobsLoading.value = true
  try {
    const response = await getUnifiedScheduledJobs({ project: route.params.id })
    scheduledJobs.value = response.data
  } catch (error) {
    ElMessage.error(t('project.fetchJobsFailed'))
  } finally {
    jobsLoading.value = false
  }
}

const fetchPermissionPolicies = async () => {
  try {
    const response = await getProjectPermissionPolicies(route.params.id, {
      page: 1,
      page_size: 200
    })
    permissionPolicies.value = normalizeListResponse(response.data)
  } catch (error) {
    permissionPolicies.value = []
  }
}

const loadPage = async () => {
  loading.value = true
  try {
    const tasks = [fetchProject(), fetchScheduledJobs(), fetchPermissionPolicies()]
    if (!moduleCatalog.value.length) {
      tasks.push(fetchModuleCatalog())
    }
    await Promise.all(tasks)
  } catch (error) {
    project.value = null
    scheduledJobs.value = []
    permissionPolicies.value = []
    ElMessage.error(t('project.fetchDetailFailed'))
  } finally {
    loading.value = false
  }
}

const handleRefresh = async () => {
  await loadPage()
}

const syncMetaTree = async () => {
  loading.value = true
  try {
    const response = await syncMetaProjectTree(route.params.id)
    project.value = {
      ...project.value,
      meta_project: response.data
    }
    ElMessage.success('Meta project tree synced')
  } catch (error) {
    ElMessage.error('Failed to sync meta project tree')
  } finally {
    loading.value = false
  }
}

const removeMember = async (member) => {
  try {
    await api.delete(`/projects/${route.params.id}/members/${member.id}/`)
    ElMessage.success(t('project.memberDeleteSuccess'))
    await fetchProject()
  } catch (error) {
    ElMessage.error(t('project.memberDeleteFailed'))
  }
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
    } else if (action === 'run') {
      await runUnifiedScheduledJobNow(job.module, job.source_id)
      ElMessage.success(t('project.runJobSuccess'))
    }

    await Promise.all([fetchProject(), fetchScheduledJobs()])
  } catch (error) {
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

const resetBindingForm = () => {
  bindingForm.value = {
    module: '',
    object_id: null
  }
  moduleProjectOptions.value = []
  bindingFormRef.value?.clearValidate()
}

const fetchModuleProjects = async (module) => {
  if (!module) {
    moduleProjectOptions.value = []
    return
  }

  const fetcher = getModuleProjectFetcher(module)
  if (!fetcher) {
    moduleProjectOptions.value = []
    return
  }

  moduleProjectsLoading.value = true
  try {
    const response = await fetcher({ page: 1, page_size: 200 })
    moduleProjectOptions.value = normalizeListResponse(response.data)
  } catch (error) {
    moduleProjectOptions.value = []
    ElMessage.error(t('project.fetchModuleProjectsFailed'))
  } finally {
    moduleProjectsLoading.value = false
  }
}

const openBindingDialog = async () => {
  resetBindingForm()
  showBindingDialog.value = true
}

const handleBindingModuleChange = async (module) => {
  bindingForm.value.object_id = null
  await fetchModuleProjects(module)
}

const submitModuleBinding = async () => {
  if (!bindingFormRef.value) {
    return
  }

  try {
    const valid = await bindingFormRef.value.validate()
    if (!valid) {
      return
    }
  } catch (error) {
    return
  }

  bindingSubmitting.value = true
  try {
    await createProjectModuleBinding(route.params.id, bindingForm.value)
    ElMessage.success(t('project.createBindingSuccess'))
    showBindingDialog.value = false
    await Promise.all([fetchProject(), fetchScheduledJobs()])
  } catch (error) {
    ElMessage.error(t('project.createBindingFailed'))
  } finally {
    bindingSubmitting.value = false
  }
}

const removeModuleBinding = async (binding) => {
  try {
    await ElMessageBox.confirm(
      t('project.deleteBindingConfirm'),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    await deleteProjectModuleBinding(route.params.id, binding.id)
    ElMessage.success(t('project.deleteBindingSuccess'))
    await Promise.all([fetchProject(), fetchScheduledJobs()])
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('project.deleteBindingFailed'))
    }
  }
}

const getPolicyLoadingKey = (policy, action) => `${policy.id}:${action}`

const isPolicyLoading = (policy, action) => Boolean(policyLoading.value[getPolicyLoadingKey(policy, action)])

const resetPolicyForm = () => {
  policyEditingId.value = null
  policyForm.value = {
    module: '*',
    action: 'scheduler.run_now',
    allowed_roles: ['owner', 'admin'],
    description: '',
    is_active: true
  }
  policyFormRef.value?.clearValidate()
}

const openPolicyDialog = (policy = null) => {
  if (policy) {
    policyEditingId.value = policy.id
    policyForm.value = {
      module: policy.module || '*',
      action: policy.action || '',
      allowed_roles: [...(policy.allowed_roles || [])],
      description: policy.description || '',
      is_active: Boolean(policy.is_active)
    }
  } else {
    resetPolicyForm()
  }
  showPolicyDialog.value = true
}

const submitPolicy = async () => {
  if (!policyFormRef.value) {
    return
  }
  try {
    const valid = await policyFormRef.value.validate()
    if (!valid) {
      return
    }
  } catch (error) {
    return
  }

  policySubmitting.value = true
  try {
    if (policyEditingId.value) {
      await updateProjectPermissionPolicy(route.params.id, policyEditingId.value, policyForm.value)
      ElMessage.success('Policy updated')
    } else {
      await createProjectPermissionPolicy(route.params.id, policyForm.value)
      ElMessage.success('Policy created')
    }
    showPolicyDialog.value = false
    await fetchPermissionPolicies()
  } catch (error) {
    ElMessage.error('Failed to save policy')
  } finally {
    policySubmitting.value = false
  }
}

const handleTogglePolicy = async (policy, isActive) => {
  const loadingKey = getPolicyLoadingKey(policy, 'toggle')
  policyLoading.value = {
    ...policyLoading.value,
    [loadingKey]: true
  }
  try {
    await updateProjectPermissionPolicy(route.params.id, policy.id, { is_active: isActive })
    policy.is_active = isActive
    ElMessage.success('Policy updated')
  } catch (error) {
    policy.is_active = !isActive
    ElMessage.error('Failed to update policy')
  } finally {
    policyLoading.value = {
      ...policyLoading.value,
      [loadingKey]: false
    }
  }
}

const removePolicy = async (policy) => {
  const loadingKey = getPolicyLoadingKey(policy, 'delete')
  policyLoading.value = {
    ...policyLoading.value,
    [loadingKey]: true
  }
  try {
    await ElMessageBox.confirm('Delete this permission policy?', t('common.warning'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    await deleteProjectPermissionPolicy(route.params.id, policy.id)
    ElMessage.success('Policy deleted')
    await fetchPermissionPolicies()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('Failed to delete policy')
    }
  } finally {
    policyLoading.value = {
      ...policyLoading.value,
      [loadingKey]: false
    }
  }
}

watch(
  () => route.params.id,
  () => {
    loadPage()
  }
)

watch(showBindingDialog, (visible) => {
  if (!visible) {
    resetBindingForm()
  }
})

watch(showPolicyDialog, (visible) => {
  if (!visible) {
    resetPolicyForm()
  }
})

onMounted(() => {
  loadPage()
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
  align-items: center;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.summary-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-bg-color);
}

.summary-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}

.summary-value,
.summary-number {
  min-height: 32px;
  display: flex;
  align-items: center;
}

.summary-number {
  font-size: 28px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tab-toolbar,
.jobs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.binding-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.binding-summary.no-margin {
  margin-bottom: 0;
}

.jobs-header .binding-summary {
  margin-bottom: 0;
}

.job-actions {
  display: flex;
  gap: 8px;
}

.meta-project-tree {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}

.meta-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.meta-node-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.meta-node-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header,
  .header-actions,
  .tab-toolbar,
  .jobs-header {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .job-actions {
    justify-content: flex-start;
  }
}
</style>
