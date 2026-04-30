<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">Knowledge Base</h1>
        <p class="page-subtitle">Documents, chunks, and retrieval queries</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadPage">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
        <el-button :loading="maintenanceRunning" @click="handleIndexPending">
          <el-icon><Operation /></el-icon>
          Index Pending
        </el-button>
        <el-button :disabled="!knowledgeBases.length" @click="openDocumentDialog">
          <el-icon><DocumentAdd /></el-icon>
          New Document
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          New Base
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Bases</div>
        <div class="metric-value">{{ summary.knowledge_bases || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Documents</div>
        <div class="metric-value">{{ summary.documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">OCR Linked</div>
        <div class="metric-value">{{ summary.ocr_linked_documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Indexed</div>
        <div class="metric-value">{{ summary.indexed_documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Failed</div>
        <div class="metric-value danger-value">{{ summary.failed_documents || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Chunks</div>
        <div class="metric-value">{{ summary.chunks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Queries</div>
        <div class="metric-value">{{ summary.queries || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">AI Answer</div>
        <div class="metric-value metric-state">{{ summary.ai_answer_configured ? 'On' : 'Local' }}</div>
      </div>
    </div>

    <div class="quality-strip">
      <div class="quality-copy">
        <span>Index Quality</span>
        <strong>{{ indexQualityPercent }}%</strong>
      </div>
      <el-progress
        :percentage="indexQualityPercent"
        :stroke-width="10"
        :show-text="false"
        :status="summary.failed_documents ? 'exception' : 'success'"
      />
      <div class="quality-meta">
        {{ summary.indexed_documents || 0 }} indexed / {{ summary.documents || 0 }} total
      </div>
    </div>

    <div class="card-container">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Bases" name="bases">
          <div class="table-toolbar base-toolbar">
            <el-select v-model="baseFilters.project" clearable filterable placeholder="Project" @change="fetchKnowledgeBases">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-select v-model="baseFilters.status" clearable placeholder="Status" @change="fetchKnowledgeBases">
              <el-option label="Active" value="active" />
              <el-option label="Archived" value="archived" />
            </el-select>
            <el-input
              v-model="baseFilters.search"
              clearable
              placeholder="Search bases"
              @keyup.enter="fetchKnowledgeBases"
              @clear="fetchKnowledgeBases"
            />
            <el-button @click="fetchKnowledgeBases">
              <el-icon><Search /></el-icon>
              Search
            </el-button>
          </div>
          <el-table v-loading="loading" :data="knowledgeBases" style="width: 100%">
            <el-table-column prop="name" label="Name" min-width="180" />
            <el-table-column prop="project_name" label="Project" min-width="160" />
            <el-table-column prop="status" label="Status" width="110">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="embedding_provider" label="Provider" min-width="130">
              <template #default="{ row }">{{ row.embedding_provider || '--' }}</template>
            </el-table-column>
            <el-table-column prop="document_count" label="Docs" width="90" />
            <el-table-column prop="query_count" label="Queries" width="100" />
            <el-table-column prop="updated_at" label="Updated" width="170">
              <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="130">
              <template #default="{ row }">
                <el-button size="small" :loading="isBaseReindexing(row)" @click="handleReindexBase(row)">
                  Reindex
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-container">
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.pageSize"
              :page-sizes="[10, 20, 50]"
              :total="pagination.total"
              layout="total, sizes, prev, pager, next"
              @size-change="fetchKnowledgeBases"
              @current-change="fetchKnowledgeBases"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="Documents" name="documents">
          <div class="table-toolbar document-toolbar">
            <el-select v-model="documentFilters.knowledge_base" clearable filterable placeholder="Knowledge base" @change="fetchDocuments">
              <el-option
                v-for="base in knowledgeBases"
                :key="base.id"
                :label="base.name"
                :value="base.id"
              />
            </el-select>
            <el-select v-model="documentFilters.status" clearable placeholder="Status" @change="fetchDocuments">
              <el-option label="Pending" value="pending" />
              <el-option label="Indexing" value="indexing" />
              <el-option label="Indexed" value="indexed" />
              <el-option label="Failed" value="failed" />
            </el-select>
            <el-select v-model="documentFilters.source_type" clearable placeholder="Source" @change="fetchDocuments">
              <el-option label="Text" value="text" />
              <el-option label="Upload" value="upload" />
              <el-option label="URL" value="url" />
            </el-select>
            <el-input
              v-model="documentFilters.search"
              clearable
              placeholder="Search documents"
              @keyup.enter="fetchDocuments"
              @clear="fetchDocuments"
            />
            <el-button @click="fetchDocuments">
              <el-icon><Search /></el-icon>
              Search
            </el-button>
          </div>
          <div v-if="selectedDocuments.length" class="bulk-action-bar">
            <span>{{ selectedDocuments.length }} selected</span>
            <el-button size="small" type="primary" :loading="bulkIndexing" @click="handleBulkIndexDocuments()">
              Index selected
            </el-button>
            <el-button size="small" :disabled="!selectedFailedDocuments.length" :loading="bulkIndexing" @click="handleBulkIndexDocuments(selectedFailedDocuments)">
              Retry failed
            </el-button>
          </div>
          <el-table
            v-loading="loading"
            :data="documents"
            style="width: 100%"
            @selection-change="handleDocumentSelectionChange"
          >
            <el-table-column type="selection" width="44" />
            <el-table-column prop="title" label="Title" min-width="200" />
            <el-table-column prop="knowledge_base_name" label="Base" min-width="160" />
            <el-table-column prop="source_type" label="Source" width="100" />
            <el-table-column label="OCR Pages" width="110">
              <template #default="{ row }">
                {{ row.metadata?.ocr_page_count || '--' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="120">
              <template #default="{ row }">
                <el-tag :type="getDocumentStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="Chunks" width="90" />
            <el-table-column prop="updated_at" label="Updated" width="170">
              <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="190">
              <template #default="{ row }">
                <el-button size="small" @click="openDocumentDetail(row)">
                  Detail
                </el-button>
                <el-button size="small" :loading="isDocumentIndexing(row)" @click="handleIndexDocument(row)">
                  Index
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Ask" name="ask">
          <div class="ask-panel">
            <el-form label-position="top">
              <el-form-item label="Knowledge Base">
                <el-select v-model="askForm.knowledge_base" filterable placeholder="Select base" style="width: 100%">
                  <el-option
                    v-for="base in knowledgeBases"
                    :key="base.id"
                    :label="base.name"
                    :value="base.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="Question">
                <el-input v-model="askForm.question" type="textarea" :rows="4" maxlength="1000" show-word-limit />
              </el-form-item>
              <el-button type="primary" :loading="asking" @click="submitQuestion">Ask</el-button>
            </el-form>
            <div v-if="lastAnswer" class="answer-panel">
              <h3>Answer</h3>
              <pre>{{ lastAnswer.answer }}</pre>
              <h3 v-if="lastAnswer.citations?.length">Citations</h3>
              <div v-for="citation in lastAnswer.citations" :key="citation.chunk_id" class="citation-item">
                <strong>{{ citation.document_title }}</strong>
                <el-tag v-if="citation.page_number" size="small" type="info">Page {{ citation.page_number }}</el-tag>
                <p>{{ citation.excerpt }}</p>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="Governance" name="governance">
          <div class="governance-grid">
            <div class="governance-panel">
              <div class="governance-head">
                <div>
                  <h3>Index Exceptions</h3>
                  <p>{{ failedDocuments.length }} failed documents</p>
                </div>
                <el-button
                  size="small"
                  type="primary"
                  :disabled="!failedDocuments.length"
                  :loading="bulkIndexing"
                  @click="handleBulkIndexDocuments(failedDocuments)"
                >
                  Retry All
                </el-button>
              </div>
              <el-table :data="failedDocuments" size="small" max-height="260">
                <el-table-column prop="title" label="Document" min-width="180" show-overflow-tooltip />
                <el-table-column prop="knowledge_base_name" label="Base" min-width="140" show-overflow-tooltip />
                <el-table-column label="Actions" width="210">
                  <template #default="{ row }">
                    <el-button size="small" @click="openDocumentDetail(row)">Detail</el-button>
                    <el-button size="small" type="primary" :loading="isDocumentIndexing(row)" @click="handleIndexDocument(row)">
                      Retry
                    </el-button>
                    <el-button size="small" type="danger" plain :loading="isGovernanceBusy(row)" @click="handleArchiveDocument(row)">
                      Archive
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="governance-panel">
              <div class="governance-head">
                <div>
                  <h3>Duplicate Candidates</h3>
                  <p>{{ duplicateDocumentGroups.length }} title groups</p>
                </div>
              </div>
              <div v-if="duplicateDocumentGroups.length" class="duplicate-list">
                <div v-for="group in duplicateDocumentGroups" :key="group.key" class="duplicate-item">
                  <strong>{{ group.title }}</strong>
                  <span>{{ group.items.length }} documents</span>
                  <el-button size="small" link type="primary" @click="focusDocumentGroup(group)">
                    Review
                  </el-button>
                  <el-button size="small" link type="warning" @click="handleIgnoreDuplicateGroup(group)">
                    Ignore
                  </el-button>
                </div>
              </div>
              <el-empty v-else description="No duplicate candidates" />
            </div>

            <div class="governance-panel">
              <div class="governance-head">
                <div>
                  <h3>Low Quality Index</h3>
                  <p>{{ lowQualityDocuments.length }} documents need attention</p>
                </div>
                <el-button
                  size="small"
                  :disabled="!lowQualityDocuments.length"
                  :loading="bulkIndexing"
                  @click="handleBulkIndexDocuments(lowQualityDocuments)"
                >
                  Reindex
                </el-button>
              </div>
              <el-table :data="lowQualityDocuments" size="small" max-height="260">
                <el-table-column prop="title" label="Document" min-width="180" show-overflow-tooltip />
                <el-table-column label="Reason" min-width="150">
                  <template #default="{ row }">{{ qualityReason(row) }}</template>
                </el-table-column>
                <el-table-column label="Actions" width="190">
                  <template #default="{ row }">
                    <el-button size="small" :loading="isGovernanceBusy(row)" @click="handleCleanDocumentChunks(row)">
                      Clean
                    </el-button>
                    <el-button size="small" type="primary" :loading="isDocumentIndexing(row)" @click="handleIndexDocument(row)">
                      Reindex
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="governance-panel">
              <div class="governance-head">
                <div>
                  <h3>Source Mix</h3>
                  <p>Current document source distribution</p>
                </div>
              </div>
              <div class="source-mix">
                <div v-for="item in sourceMix" :key="item.source" class="source-mix-item">
                  <span>{{ item.source }}</span>
                  <strong>{{ item.count }}</strong>
                  <el-progress :percentage="item.percent" :show-text="false" :stroke-width="8" />
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="showCreateDialog" title="New Knowledge Base" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="130px">
        <el-form-item label="Project" prop="project">
          <el-select v-model="form.project" filterable placeholder="Select project" style="width: 100%">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Name" prop="name">
          <el-input v-model="form.name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item label="Embedding Provider">
          <el-input v-model="form.embedding_provider" placeholder="openai, qwen, local" />
        </el-form-item>
        <el-form-item label="Embedding Model">
          <el-input v-model="form.embedding_model" placeholder="text-embedding model" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitKnowledgeBase">
          Create
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDocumentDialog" title="New Document" width="680px">
      <el-form ref="documentFormRef" :model="documentForm" :rules="documentRules" label-width="130px">
        <el-form-item label="Mode">
          <el-segmented
            v-model="documentMode"
            :options="[
              { label: 'Text', value: 'text' },
              { label: 'File', value: 'file' },
              { label: 'OCR Task', value: 'ocr' },
              { label: 'OCR Batch', value: 'ocr_batch' }
            ]"
          />
        </el-form-item>
        <el-form-item label="Knowledge Base" prop="knowledge_base">
          <el-select v-model="documentForm.knowledge_base" filterable style="width: 100%">
            <el-option
              v-for="base in knowledgeBases"
              :key="base.id"
              :label="base.name"
              :value="base.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="documentMode !== 'ocr_batch'" label="Title" prop="title">
          <el-input v-model="documentForm.title" maxlength="300" show-word-limit />
        </el-form-item>
        <el-form-item v-if="documentMode === 'text'" label="Content" prop="content_text">
          <el-input v-model="documentForm.content_text" type="textarea" :rows="10" maxlength="20000" show-word-limit />
        </el-form-item>
        <el-form-item v-else-if="documentMode === 'file'" label="File">
          <el-upload
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            :file-list="documentFileList"
            :on-change="handleDocumentFileChange"
            :on-remove="handleDocumentFileRemove"
            class="upload-control"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">Drop file here or click to upload</div>
            <template #tip>
              <div class="el-upload__tip">txt, md, csv, json, pdf, docx up to 10MB</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item v-else-if="documentMode === 'ocr'" label="OCR Task" prop="ocr_task">
          <el-select v-model="documentForm.ocr_task" filterable style="width: 100%">
            <el-option
              v-for="task in ocrTasks"
              :key="task.id"
              :label="`${task.name} / ${task.project_name || '--'}`"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="documentMode === 'ocr_batch'" label="OCR Batch" prop="ocr_batch">
          <el-select v-model="documentForm.ocr_batch" filterable style="width: 100%">
            <el-option
              v-for="batch in ocrBatches"
              :key="batch.id"
              :label="`${batch.name} / ${batch.project_name || '--'} / ${batch.succeeded_tasks || 0} done`"
              :value="batch.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDocumentDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitDocument">
          Create And Index
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDocumentDetailDialog" size="680px" title="Document Detail">
      <div v-if="selectedDocument" class="document-detail">
        <div class="detail-head">
          <div>
            <h2>{{ selectedDocument.title }}</h2>
            <p>{{ selectedDocument.knowledge_base_name }} / {{ selectedDocument.source_type }}</p>
          </div>
          <div class="detail-actions">
            <el-tag :type="getDocumentStatusType(selectedDocument.status)">{{ selectedDocument.status }}</el-tag>
            <el-button
              v-if="selectedDocument.metadata?.ocr_task_id"
              size="small"
              @click="openOcrSource(selectedDocument)"
            >
              Open OCR
            </el-button>
            <el-button
              size="small"
              type="primary"
              :loading="isDocumentIndexing(selectedDocument)"
              @click="handleIndexDocument(selectedDocument)"
            >
              Reindex
            </el-button>
          </div>
        </div>

        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="Chunks">{{ selectedDocument.chunk_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="OCR Pages">{{ selectedDocument.metadata?.ocr_page_count || '--' }}</el-descriptions-item>
          <el-descriptions-item label="File">{{ selectedDocument.file_name || '--' }}</el-descriptions-item>
          <el-descriptions-item label="Updated">{{ formatDate(selectedDocument.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="Source URI" :span="2">{{ selectedDocument.source_uri || '--' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section">
          <div class="section-title">Content</div>
          <pre class="content-preview">{{ selectedDocument.content_text || selectedDocument.error_message || '--' }}</pre>
        </div>

        <div v-if="selectedDocument.metadata?.ocr_pages?.length" class="detail-section">
          <div class="section-title">OCR Pages</div>
          <div class="page-chip-list">
            <el-tag
              v-for="page in selectedDocument.metadata.ocr_pages"
              :key="page.id || page.page_number"
              type="info"
            >
              Page {{ page.page_number }}
            </el-tag>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-title">Chunks</div>
          <el-empty v-if="!loadingDocumentChunks && !documentChunks.length" description="No chunks" />
          <div v-loading="loadingDocumentChunks" class="chunk-list">
            <div v-for="chunk in documentChunks" :key="chunk.id" class="chunk-item">
              <div class="chunk-header">
                <span>#{{ chunk.chunk_index + 1 }}</span>
                <el-tag v-if="chunk.metadata?.page_number" size="small" type="info">
                  Page {{ chunk.metadata.page_number }}
                </el-tag>
              </div>
              <p>{{ chunk.content }}</p>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentAdd, Operation, Plus, Refresh, Search, UploadFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { getUnifiedProjects } from '@/api/core'
import { getOcrBatches, getOcrTasks } from '@/api/ocr-service'
import {
  askKnowledgeBase,
  archiveKnowledgeDocumentGovernance,
  cleanKnowledgeDocumentChunks,
  createKnowledgeBase,
  createKnowledgeDocument,
  getKnowledgeChunks,
  getKnowledgeBaseSummary,
  getKnowledgeBases,
  getKnowledgeDocuments,
  importOcrKnowledgeDocument,
  indexPendingKnowledgeDocuments,
  indexKnowledgeDocument,
  markKnowledgeDocumentDuplicate,
  reindexKnowledgeBase,
  uploadKnowledgeDocument
} from '@/api/knowledge-base'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const submitting = ref(false)
const asking = ref(false)
const maintenanceRunning = ref(false)
const bulkIndexing = ref(false)
const activeTab = ref('bases')
const knowledgeBases = ref([])
const documents = ref([])
const projects = ref([])
const ocrTasks = ref([])
const ocrBatches = ref([])
const showCreateDialog = ref(false)
const showDocumentDialog = ref(false)
const showDocumentDetailDialog = ref(false)
const documentMode = ref('text')
const formRef = ref()
const documentFormRef = ref()
const documentFile = ref(null)
const documentFileList = ref([])
const selectedDocument = ref(null)
const documentChunks = ref([])
const selectedDocuments = ref([])
const loadingDocumentChunks = ref(false)
const summary = reactive({})
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})
const form = reactive({
  project: null,
  name: '',
  description: '',
  embedding_provider: '',
  embedding_model: ''
})
const documentForm = reactive({
  knowledge_base: null,
  title: '',
  source_type: 'text',
  content_text: '',
  ocr_task: null,
  ocr_batch: null
})
const askForm = reactive({
  knowledge_base: null,
  question: ''
})
const lastAnswer = ref(null)
const indexingDocuments = ref({})
const reindexingBases = ref({})
const governanceBusy = ref({})
const baseFilters = reactive({
  project: null,
  status: '',
  search: ''
})
const documentFilters = reactive({
  knowledge_base: null,
  status: '',
  source_type: '',
  search: ''
})

const rules = computed(() => ({
  project: [{ required: true, message: 'Select project', trigger: 'change' }],
  name: [{ required: true, message: 'Enter name', trigger: 'blur' }]
}))
const documentRules = computed(() => ({
  knowledge_base: [{ required: true, message: 'Select knowledge base', trigger: 'change' }],
  title: documentMode.value === 'ocr_batch'
    ? []
    : [{ required: true, message: 'Enter title', trigger: 'blur' }],
  content_text: documentMode.value === 'text'
    ? [{ required: true, message: 'Enter content', trigger: 'blur' }]
    : [],
  ocr_task: documentMode.value === 'ocr'
    ? [{ required: true, message: 'Select OCR task', trigger: 'change' }]
    : [],
  ocr_batch: documentMode.value === 'ocr_batch'
    ? [{ required: true, message: 'Select OCR batch', trigger: 'change' }]
    : []
}))

const indexQualityPercent = computed(() => {
  const total = Number(summary.documents || 0)
  if (!total) {
    return 0
  }
  return Math.round((Number(summary.indexed_documents || 0) / total) * 100)
})

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

const resetForm = () => {
  form.project = projects.value[0]?.id || null
  form.name = ''
  form.description = ''
  form.embedding_provider = ''
  form.embedding_model = ''
  formRef.value?.clearValidate()
}

const resetDocumentForm = () => {
  documentMode.value = 'text'
  documentForm.knowledge_base = knowledgeBases.value[0]?.id || null
  documentForm.title = ''
  documentForm.source_type = 'text'
  documentForm.content_text = ''
  documentForm.ocr_task = null
  documentForm.ocr_batch = null
  documentFile.value = null
  documentFileList.value = []
  documentFormRef.value?.clearValidate()
}

const getDocumentStatusType = (status) => {
  const typeMap = {
    pending: 'info',
    indexing: 'warning',
    indexed: 'success',
    failed: 'danger'
  }
  return typeMap[status] || 'info'
}

const isDocumentIndexing = (document) => {
  return Boolean(indexingDocuments.value[document.id])
}

const isBaseReindexing = (base) => {
  return Boolean(reindexingBases.value[base.id])
}

const isGovernanceBusy = (document) => {
  return Boolean(governanceBusy.value[document.id])
}

const isGovernanceVisible = (document) => {
  return !document.metadata?.governance_archived && !document.metadata?.duplicate_ignored
}

const selectedFailedDocuments = computed(() => {
  return selectedDocuments.value.filter(document => document.status === 'failed')
})

const failedDocuments = computed(() => {
  return documents.value.filter(document => document.status === 'failed' && isGovernanceVisible(document))
})

const lowQualityDocuments = computed(() => {
  return documents.value.filter(document => {
    if (!isGovernanceVisible(document)) {
      return false
    }
    if (document.status === 'failed') {
      return false
    }
    if (document.status === 'indexed' && Number(document.chunk_count || 0) === 0) {
      return true
    }
    if (document.status === 'pending') {
      return true
    }
    return false
  })
})

const duplicateDocumentGroups = computed(() => {
  const groups = documents.value.reduce((acc, document) => {
    if (!isGovernanceVisible(document)) {
      return acc
    }
    const key = String(document.title || '').trim().toLowerCase()
    if (!key) {
      return acc
    }
    acc[key] = acc[key] || []
    acc[key].push(document)
    return acc
  }, {})
  return Object.entries(groups)
    .filter(([, items]) => items.length > 1)
    .map(([key, items]) => ({
      key,
      title: items[0].title,
      items
    }))
})

const sourceMix = computed(() => {
  const total = documents.value.length || 1
  const counts = documents.value.reduce((acc, document) => {
    const source = document.source_type || 'unknown'
    acc[source] = (acc[source] || 0) + 1
    return acc
  }, {})
  return Object.entries(counts).map(([source, count]) => ({
    source,
    count,
    percent: Math.round((count / total) * 100)
  }))
})

const fetchProjects = async () => {
  const response = await getUnifiedProjects({ page: 1, page_size: 200 })
  projects.value = normalizeListResponse(response.data).results
}

const fetchSummary = async () => {
  const response = await getKnowledgeBaseSummary()
  Object.keys(summary).forEach(key => delete summary[key])
  Object.assign(summary, response.data || {})
}

const fetchKnowledgeBases = async () => {
  const params = {
    page: pagination.page,
    page_size: pagination.pageSize
  }
  if (baseFilters.project) {
    params.project = baseFilters.project
  }
  if (baseFilters.status) {
    params.status = baseFilters.status
  }
  if (baseFilters.search.trim()) {
    params.search = baseFilters.search.trim()
  }
  const response = await getKnowledgeBases(params)
  const normalized = normalizeListResponse(response.data)
  knowledgeBases.value = normalized.results
  pagination.total = normalized.count
}

const fetchDocuments = async () => {
  const params = {
    page: 1,
    page_size: 200
  }
  if (documentFilters.knowledge_base) {
    params.knowledge_base = documentFilters.knowledge_base
  }
  if (documentFilters.status) {
    params.status = documentFilters.status
  }
  if (documentFilters.source_type) {
    params.source_type = documentFilters.source_type
  }
  if (documentFilters.search.trim()) {
    params.search = documentFilters.search.trim()
  }
  const response = await getKnowledgeDocuments(params)
  documents.value = normalizeListResponse(response.data).results
}

const fetchOcrTasks = async () => {
  const response = await getOcrTasks({ page: 1, page_size: 200, status: 'succeeded' })
  ocrTasks.value = normalizeListResponse(response.data).results
}

const fetchOcrBatches = async () => {
  const response = await getOcrBatches({ page: 1, page_size: 200, status: 'succeeded' })
  ocrBatches.value = normalizeListResponse(response.data).results
}

const loadPage = async () => {
  applyRouteFilters()
  loading.value = true
  try {
    await Promise.all([fetchProjects(), fetchSummary(), fetchKnowledgeBases(), fetchDocuments(), fetchOcrTasks(), fetchOcrBatches()])
    if (!askForm.knowledge_base && knowledgeBases.value.length) {
      askForm.knowledge_base = knowledgeBases.value[0].id
    }
  } catch (error) {
    ElMessage.error('Failed to load knowledge bases')
  } finally {
    loading.value = false
  }
}

const applyRouteFilters = () => {
  if (route.query?.tab) {
    activeTab.value = String(route.query.tab)
  }
  if (route.query?.document_status) {
    documentFilters.status = String(route.query.document_status)
  }
  if (route.query?.source_type) {
    documentFilters.source_type = String(route.query.source_type)
  }
}

const openCreateDialog = () => {
  resetForm()
  showCreateDialog.value = true
}

const openDocumentDialog = () => {
  resetDocumentForm()
  showDocumentDialog.value = true
}

const openDocumentDetail = async (document) => {
  selectedDocument.value = document
  documentChunks.value = []
  showDocumentDetailDialog.value = true
  loadingDocumentChunks.value = true
  try {
    const response = await getKnowledgeChunks({
      document: document.id,
      page: 1,
      page_size: 200
    })
    documentChunks.value = normalizeListResponse(response.data).results
  } catch (error) {
    ElMessage.error('Failed to load document chunks')
  } finally {
    loadingDocumentChunks.value = false
  }
}

const openOcrSource = (document) => {
  const taskId = document.metadata?.ocr_task_id
  if (!taskId) {
    return
  }
  router.push({
    path: '/ai-generation/ocr-service',
    query: { task: taskId }
  })
}

const focusDocumentGroup = (group) => {
  activeTab.value = 'documents'
  documentFilters.search = group.title
  fetchDocuments()
}

const qualityReason = (document) => {
  if (document.status === 'pending') {
    return 'Pending indexing'
  }
  if (document.status === 'indexed' && Number(document.chunk_count || 0) === 0) {
    return 'Indexed without chunks'
  }
  return 'Needs review'
}

const handleDocumentFileChange = (uploadFile, uploadFiles) => {
  documentFile.value = uploadFile.raw
  documentFileList.value = uploadFiles.slice(-1)
  if (!documentForm.title && uploadFile.name) {
    documentForm.title = uploadFile.name
  }
  return false
}

const handleDocumentFileRemove = () => {
  documentFile.value = null
  documentFileList.value = []
}

const submitKnowledgeBase = async () => {
  if (!formRef.value) {
    return
  }
  try {
    await formRef.value.validate()
  } catch (error) {
    return
  }

  submitting.value = true
  try {
    await createKnowledgeBase({ ...form })
    ElMessage.success('Knowledge base created')
    showCreateDialog.value = false
    await Promise.all([fetchSummary(), fetchKnowledgeBases()])
    if (!askForm.knowledge_base && knowledgeBases.value.length) {
      askForm.knowledge_base = knowledgeBases.value[0].id
    }
  } catch (error) {
    ElMessage.error('Failed to create knowledge base')
  } finally {
    submitting.value = false
  }
}

const submitDocument = async () => {
  if (!documentFormRef.value) {
    return
  }
  try {
    await documentFormRef.value.validate()
  } catch (error) {
    return
  }

  submitting.value = true
  try {
    if (documentMode.value === 'file') {
      if (!documentFile.value) {
        ElMessage.warning('Select a file')
        return
      }
      const formData = new FormData()
      formData.append('knowledge_base', documentForm.knowledge_base)
      formData.append('title', documentForm.title)
      formData.append('file', documentFile.value)
      await uploadKnowledgeDocument(formData)
    } else if (documentMode.value === 'ocr') {
      if (!documentForm.ocr_task) {
        ElMessage.warning('Select an OCR task')
        return
      }
      await importOcrKnowledgeDocument({
        knowledge_base: documentForm.knowledge_base,
        ocr_task: documentForm.ocr_task,
        title: documentForm.title
      })
    } else if (documentMode.value === 'ocr_batch') {
      if (!documentForm.ocr_batch) {
        ElMessage.warning('Select an OCR batch')
        return
      }
      await importOcrKnowledgeDocument({
        knowledge_base: documentForm.knowledge_base,
        ocr_batch: documentForm.ocr_batch
      })
    } else {
      await createKnowledgeDocument({
        knowledge_base: documentForm.knowledge_base,
        title: documentForm.title,
        source_type: 'text',
        content_text: documentForm.content_text
      })
    }
    ElMessage.success('Document indexed')
    showDocumentDialog.value = false
    activeTab.value = 'documents'
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to create document')
  } finally {
    submitting.value = false
  }
}

const handleIndexDocument = async (document) => {
  indexingDocuments.value = {
    ...indexingDocuments.value,
    [document.id]: true
  }
  try {
    const response = await indexKnowledgeDocument(document.id)
    ElMessage.success('Document indexed')
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
    if (selectedDocument.value?.id === document.id) {
      selectedDocument.value = response.data
      await openDocumentDetail(response.data)
    }
  } catch (error) {
    ElMessage.error('Failed to index document')
  } finally {
    indexingDocuments.value = {
      ...indexingDocuments.value,
      [document.id]: false
    }
  }
}

const updateDocumentInLists = (nextDocument) => {
  documents.value = documents.value.map(item => item.id === nextDocument.id ? nextDocument : item)
  selectedDocuments.value = selectedDocuments.value.map(item => item.id === nextDocument.id ? nextDocument : item)
  if (selectedDocument.value?.id === nextDocument.id) {
    selectedDocument.value = nextDocument
  }
}

const handleDocumentSelectionChange = (selection) => {
  selectedDocuments.value = selection
}

const handleBulkIndexDocuments = async (targetDocuments = selectedDocuments.value) => {
  const queue = targetDocuments.filter(document => document.status !== 'indexing')
  if (!queue.length) {
    ElMessage.warning('No indexable document selected')
    return
  }
  bulkIndexing.value = true
  let indexed = 0
  try {
    for (const document of queue) {
      const response = await indexKnowledgeDocument(document.id)
      updateDocumentInLists(response.data)
      if (response.data.status === 'indexed') {
        indexed += 1
      }
    }
    ElMessage.success(`Indexed ${indexed}/${queue.length} documents`)
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to index selected documents')
  } finally {
    bulkIndexing.value = false
  }
}

const setGovernanceBusy = (document, value) => {
  governanceBusy.value = {
    ...governanceBusy.value,
    [document.id]: value
  }
}

const handleArchiveDocument = async (document) => {
  setGovernanceBusy(document, true)
  try {
    const response = await archiveKnowledgeDocumentGovernance(document.id, {
      reason: 'Archived from governance panel.'
    })
    updateDocumentInLists(response.data)
    ElMessage.success('Document archived from governance')
    await Promise.all([fetchSummary(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to archive document')
  } finally {
    setGovernanceBusy(document, false)
  }
}

const handleCleanDocumentChunks = async (document) => {
  setGovernanceBusy(document, true)
  try {
    const response = await cleanKnowledgeDocumentChunks(document.id, {
      remove_failed: true,
      reindex: true
    })
    updateDocumentInLists(response.data.document)
    ElMessage.success(`Cleaned ${response.data.deleted_chunks || 0} chunks`)
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to clean chunks')
  } finally {
    setGovernanceBusy(document, false)
  }
}

const handleIgnoreDuplicateGroup = async (group) => {
  const [, ...duplicates] = group.items
  if (!duplicates.length) {
    return
  }
  try {
    for (const document of duplicates) {
      setGovernanceBusy(document, true)
      const response = await markKnowledgeDocumentDuplicate(document.id, {
        duplicate_of: group.items[0].id,
        duplicate_group: group.key,
        reason: 'Ignored duplicate candidate from governance panel.'
      })
      updateDocumentInLists(response.data)
      setGovernanceBusy(document, false)
    }
    ElMessage.success(`Ignored ${duplicates.length} duplicate document(s)`)
    await Promise.all([fetchSummary(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to mark duplicates')
  } finally {
    duplicates.forEach(document => setGovernanceBusy(document, false))
  }
}

const handleReindexBase = async (base) => {
  reindexingBases.value = {
    ...reindexingBases.value,
    [base.id]: true
  }
  try {
    const response = await reindexKnowledgeBase(base.id)
    ElMessage.success(`Reindexed ${response.data.indexed || 0} documents`)
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to reindex knowledge base')
  } finally {
    reindexingBases.value = {
      ...reindexingBases.value,
      [base.id]: false
    }
  }
}

const handleIndexPending = async () => {
  maintenanceRunning.value = true
  try {
    const response = await indexPendingKnowledgeDocuments()
    ElMessage.success(`Indexed ${response.data.indexed || 0} pending documents`)
    await Promise.all([fetchSummary(), fetchKnowledgeBases(), fetchDocuments()])
  } catch (error) {
    ElMessage.error('Failed to index pending documents')
  } finally {
    maintenanceRunning.value = false
  }
}

const submitQuestion = async () => {
  if (!askForm.knowledge_base || !askForm.question.trim()) {
    ElMessage.warning('Select a knowledge base and enter a question')
    return
  }

  asking.value = true
  try {
    const response = await askKnowledgeBase({ ...askForm })
    lastAnswer.value = response.data
    await fetchSummary()
  } catch (error) {
    ElMessage.error('Failed to ask knowledge base')
  } finally {
    asking.value = false
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

@media (max-width: 1200px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
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

.metric-state {
  font-size: 20px;
}

.danger-value {
  color: var(--el-color-danger);
}

.quality-strip {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) auto;
  gap: 14px;
  align-items: center;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.quality-copy {
  display: flex;
  align-items: baseline;
  gap: 8px;

  span {
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 20px;
  }
}

.quality-meta {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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

.bulk-action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);

  span {
    margin-right: auto;
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }
}

.base-toolbar {
  grid-template-columns: minmax(150px, 1fr) minmax(120px, 160px) minmax(180px, 1.4fr) auto;
}

.document-toolbar {
  grid-template-columns: minmax(160px, 1fr) minmax(120px, 160px) minmax(120px, 160px) minmax(180px, 1.4fr) auto;
}

.ask-panel {
  max-width: 900px;
}

.document-detail {
  display: grid;
  gap: 16px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

  h2 {
    margin: 0 0 6px;
    font-size: 18px;
  }

  p {
    margin: 0;
    color: var(--el-text-color-secondary);
  }
}

.detail-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-section {
  display: grid;
  gap: 8px;
}

.section-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.content-preview {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  font-family: inherit;
  line-height: 1.55;
}

.page-chip-list,
.chunk-list {
  display: grid;
  gap: 10px;
}

.page-chip-list {
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
}

.chunk-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;

  p {
    margin: 8px 0 0;
    color: var(--el-text-color-regular);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.chunk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.answer-panel {
  margin-top: 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-fill-color-lighter);

  h3 {
    margin: 0 0 10px;
    font-size: 15px;
  }

  pre {
    margin: 0;
    white-space: pre-wrap;
    font-family: inherit;
    line-height: 1.6;
  }
}

.governance-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.governance-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 14px;
  min-height: 260px;
}

.governance-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;

  h3 {
    margin: 0 0 4px;
    font-size: 15px;
  }

  p {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }
}

.duplicate-list,
.source-mix {
  display: grid;
  gap: 10px;
}

.duplicate-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 12px;

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  span {
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }
}

.source-mix-item {
  display: grid;
  grid-template-columns: 90px 40px minmax(120px, 1fr);
  align-items: center;
  gap: 10px;
  color: var(--el-text-color-secondary);

  strong {
    color: var(--el-text-color-primary);
  }
}

.citation-item {
  border-top: 1px solid var(--el-border-color-light);
  padding-top: 10px;
  margin-top: 10px;

  p {
    margin: 6px 0 0;
    color: var(--el-text-color-regular);
    line-height: 1.5;
  }
}

.upload-control {
  width: 100%;
}

@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .quality-strip {
    grid-template-columns: 1fr;
  }

  .base-toolbar,
  .document-toolbar {
    grid-template-columns: 1fr;
  }

  .governance-grid,
  .duplicate-item,
  .source-mix-item {
    grid-template-columns: 1fr;
  }
}
</style>
