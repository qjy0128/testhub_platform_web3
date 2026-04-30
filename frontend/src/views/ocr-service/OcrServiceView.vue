<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">OCR Service</h1>
        <p class="page-subtitle">Engine configs and extraction tasks</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadPage">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
        <el-button :loading="runningPending" @click="handleRunPending">
          <el-icon><Operation /></el-icon>
          Run Pending
        </el-button>
        <el-button @click="openEngineDialog">
          <el-icon><Setting /></el-icon>
          New Engine
        </el-button>
        <el-button @click="openBatchDialog">
          <el-icon><Files /></el-icon>
          New Batch
        </el-button>
        <el-button type="primary" @click="openTaskDialog">
          <el-icon><Plus /></el-icon>
          New Task
        </el-button>
      </div>
    </div>

    <div class="overview-grid">
      <div class="metric-item">
        <div class="metric-label">Engines</div>
        <div class="metric-value">{{ summary.engines || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Batches</div>
        <div class="metric-value">{{ summary.batches || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Tasks</div>
        <div class="metric-value">{{ summary.tasks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Pages</div>
        <div class="metric-value">{{ summary.pages || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Pending</div>
        <div class="metric-value">{{ summary.pending_tasks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Failed</div>
        <div class="metric-value">{{ summary.failed_tasks || 0 }}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Succeeded</div>
        <div class="metric-value">{{ summary.succeeded_tasks || 0 }}</div>
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
            <el-select v-model="taskFilters.status" clearable placeholder="Status" @change="fetchTasks">
              <el-option label="Pending" value="pending" />
              <el-option label="Running" value="running" />
              <el-option label="Succeeded" value="succeeded" />
              <el-option label="Failed" value="failed" />
              <el-option label="Cancelled" value="cancelled" />
            </el-select>
            <el-select v-model="taskFilters.source_type" clearable placeholder="Source" @change="fetchTasks">
              <el-option label="Image" value="image" />
              <el-option label="PDF" value="pdf" />
              <el-option label="Text" value="text" />
              <el-option label="Other" value="other" />
            </el-select>
            <el-input
              v-model="taskFilters.search"
              clearable
              placeholder="Search tasks"
              @keyup.enter="fetchTasks"
              @clear="fetchTasks"
            />
            <el-button @click="fetchTasks">
              <el-icon><Search /></el-icon>
              Search
            </el-button>
          </div>
          <div v-if="selectedTasks.length" class="bulk-action-bar">
            <span>{{ selectedTasks.length }} selected</span>
            <el-button size="small" type="primary" :loading="bulkRunning" @click="handleBulkRunTasks">
              Run selected
            </el-button>
            <el-button size="small" :loading="bulkRetrying" @click="handleBulkRetryTasks">
              Retry failed
            </el-button>
            <el-button size="small" :disabled="!selectedSucceededTasks.length" @click="openImportDialog('tasks', selectedSucceededTasks)">
              Import succeeded
            </el-button>
            <el-button size="small" type="danger" plain :loading="bulkCancelling" @click="handleBulkCancelTasks">
              Cancel runnable
            </el-button>
          </div>
          <el-table
            v-loading="loading"
            :data="tasks"
            style="width: 100%"
            @selection-change="handleTaskSelectionChange"
          >
            <el-table-column type="selection" width="44" />
            <el-table-column prop="name" label="Name" min-width="180" />
            <el-table-column prop="project_name" label="Project" min-width="150">
              <template #default="{ row }">{{ row.project_name || '--' }}</template>
            </el-table-column>
            <el-table-column prop="engine_name" label="Engine" min-width="150">
              <template #default="{ row }">{{ row.engine_name || '--' }}</template>
            </el-table-column>
            <el-table-column prop="source_type" label="Source" width="100" />
            <el-table-column prop="page_count" label="Pages" width="90">
              <template #default="{ row }">{{ row.page_count || 0 }}</template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="120">
              <template #default="{ row }">
                <el-tag :type="getTaskStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Text" min-width="220">
              <template #default="{ row }">
                <span class="text-preview">{{ row.extracted_text || row.error_message || '--' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="Created" width="170">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="210" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openTaskDetail(row)">
                  Detail
                </el-button>
                <el-button
                  size="small"
                  :disabled="row.status !== 'succeeded'"
                  @click="openImportDialog('task', row)"
                >
                  Import
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="isTaskRunning(row)"
                  :disabled="row.status === 'cancelled'"
                  @click="handleRunTask(row)"
                >
                  Run
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Batches" name="batches">
          <div class="table-toolbar batch-filter-toolbar">
            <el-select v-model="batchFilters.project" clearable filterable placeholder="Project" @change="fetchBatches">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
            <el-select v-model="batchFilters.status" clearable placeholder="Status" @change="fetchBatches">
              <el-option label="Pending" value="pending" />
              <el-option label="Running" value="running" />
              <el-option label="Succeeded" value="succeeded" />
              <el-option label="Partial" value="partial" />
              <el-option label="Failed" value="failed" />
              <el-option label="Cancelled" value="cancelled" />
            </el-select>
            <el-input
              v-model="batchFilters.search"
              clearable
              placeholder="Search batches"
              @keyup.enter="fetchBatches"
              @clear="fetchBatches"
            />
            <el-button @click="fetchBatches">
              <el-icon><Search /></el-icon>
              Search
            </el-button>
          </div>
          <el-table v-loading="loading" :data="batches" style="width: 100%">
            <el-table-column prop="name" label="Name" min-width="180" />
            <el-table-column prop="project_name" label="Project" min-width="150">
              <template #default="{ row }">{{ row.project_name || '--' }}</template>
            </el-table-column>
            <el-table-column prop="engine_name" label="Engine" min-width="150">
              <template #default="{ row }">{{ row.engine_name || '--' }}</template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="120">
              <template #default="{ row }">
                <el-tag :type="getTaskStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_tasks" label="Total" width="90" />
            <el-table-column prop="succeeded_tasks" label="Succeeded" width="110" />
            <el-table-column prop="failed_tasks" label="Failed" width="90" />
            <el-table-column prop="cancelled_tasks" label="Cancelled" width="110" />
            <el-table-column prop="created_at" label="Created" width="170">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="Actions" width="310" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openBatchDetail(row)">
                  Detail
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="isBatchRunning(row)"
                  :disabled="row.status === 'succeeded' || row.status === 'cancelled'"
                  @click="handleRunBatch(row)"
                >
                  Run
                </el-button>
                <el-button
                  size="small"
                  :disabled="row.status !== 'succeeded'"
                  @click="openImportDialog('batch', row)"
                >
                  Import
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="row.status === 'succeeded' || row.status === 'failed' || row.status === 'cancelled'"
                  @click="handleCancelBatch(row)"
                >
                  Cancel
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Engines" name="engines">
          <el-table v-loading="loading" :data="engines" style="width: 100%">
            <el-table-column prop="name" label="Name" min-width="180" />
            <el-table-column prop="engine_type" label="Type" width="120" />
            <el-table-column prop="model_name" label="Model" min-width="160">
              <template #default="{ row }">{{ row.model_name || '--' }}</template>
            </el-table-column>
            <el-table-column prop="is_default" label="Default" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" type="success">Default</el-tag>
                <span v-else>--</span>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="Active" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'">
                  {{ row.is_active ? 'Yes' : 'No' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="task_count" label="Tasks" width="90" />
            <el-table-column label="Actions" width="210">
              <template #default="{ row }">
                <el-button
                  size="small"
                  :disabled="row.is_default"
                  @click="handleSetDefault(row)"
                >
                  Default
                </el-button>
                <el-button size="small" :loading="isPreflighting(row)" @click="handlePreflight(row)">
                  Check
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-alert
            v-if="lastPreflight"
            class="preflight-alert"
            :type="lastPreflight.ready ? 'success' : 'warning'"
            :closable="false"
            show-icon
          >
            <template #title>
              {{ lastPreflight.ready ? 'Engine ready' : 'Engine needs attention' }}
            </template>
            <div>
              Capabilities: {{ lastPreflight.capabilities?.join(', ') || '--' }}
            </div>
            <div v-if="lastPreflight.issues?.length">
              Issues: {{ lastPreflight.issues.join('; ') }}
            </div>
          </el-alert>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="showEngineDialog" title="New OCR Engine" width="560px">
      <el-form ref="engineFormRef" :model="engineForm" :rules="engineRules" label-width="120px">
        <el-form-item label="Name" prop="name">
          <el-input v-model="engineForm.name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="Type" prop="engine_type">
          <el-select v-model="engineForm.engine_type" style="width: 100%">
            <el-option label="GPT-4V" value="gpt4v" />
            <el-option label="GLM-4V" value="glm4v" />
            <el-option label="EasyOCR" value="easyocr" />
            <el-option label="Tesseract" value="tesseract" />
            <el-option label="Custom" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="engineForm.base_url" />
        </el-form-item>
        <el-form-item label="Model">
          <el-input v-model="engineForm.model_name" />
        </el-form-item>
        <el-form-item label="Credential Ref">
          <el-input v-model="engineForm.credential_ref" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="engineForm.is_default">Default engine</el-checkbox>
          <el-checkbox v-model="engineForm.is_active">Active</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEngineDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEngine">
          Create
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showBatchDialog" title="New OCR Batch" width="760px">
      <el-form ref="batchFormRef" :model="batchForm" :rules="batchRules" label-width="120px">
        <el-form-item label="Mode">
          <el-segmented
            v-model="batchMode"
            :options="[
              { label: 'Text Items', value: 'text' },
              { label: 'Files', value: 'file' }
            ]"
          />
        </el-form-item>
        <el-form-item label="Name" prop="name">
          <el-input v-model="batchForm.name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="Project">
          <el-select v-model="batchForm.project" clearable filterable placeholder="Optional" style="width: 100%">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Engine">
          <el-select v-model="batchForm.engine" clearable filterable placeholder="Default engine" style="width: 100%">
            <el-option
              v-for="engine in engines"
              :key="engine.id"
              :label="engine.name"
              :value="engine.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="batchForm.run_immediately">Run immediately</el-checkbox>
        </el-form-item>
      </el-form>

      <template v-if="batchMode === 'text'">
        <div class="batch-toolbar">
          <el-button size="small" @click="addBatchItem">
            <el-icon><Plus /></el-icon>
            Add Item
          </el-button>
        </div>

        <div class="batch-items">
          <div v-for="(item, index) in batchItems" :key="item.key" class="batch-item">
            <div class="batch-item-header">
              <span>Item {{ index + 1 }}</span>
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="batchItems.length === 1"
                @click="removeBatchItem(index)"
              >
                Remove
              </el-button>
            </div>
            <el-input v-model="item.name" placeholder="Name" maxlength="200" />
            <el-input
              v-model="item.input_text"
              type="textarea"
              :rows="4"
              placeholder="Input text"
              maxlength="20000"
              show-word-limit
            />
          </div>
        </div>
      </template>
      <el-upload
        v-else
        drag
        multiple
        action="#"
        :auto-upload="false"
        :file-list="batchFileList"
        :on-change="handleBatchFileChange"
        :on-remove="handleBatchFileRemove"
        class="upload-control"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">Drop images or PDFs here</div>
        <template #tip>
          <div class="el-upload__tip">png, jpg, webp, tiff, pdf up to 20MB each</div>
        </template>
      </el-upload>

      <template #footer>
        <el-button @click="showBatchDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitBatch">
          Create
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showTaskDialog" title="New OCR Task" width="560px">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="120px">
        <el-form-item label="Mode">
          <el-segmented
            v-model="taskMode"
            :options="[
              { label: 'Text', value: 'text' },
              { label: 'File', value: 'file' }
            ]"
          />
        </el-form-item>
        <el-form-item label="Name" prop="name">
          <el-input v-model="taskForm.name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="Project">
          <el-select v-model="taskForm.project" clearable filterable placeholder="Optional" style="width: 100%">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Engine">
          <el-select v-model="taskForm.engine" clearable filterable placeholder="Default engine" style="width: 100%">
            <el-option
              v-for="engine in engines"
              :key="engine.id"
              :label="engine.name"
              :value="engine.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="taskMode === 'text'" label="Source" prop="source_type">
          <el-select v-model="taskForm.source_type" style="width: 100%">
            <el-option label="Text" value="text" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="taskMode === 'text'" label="Input URL">
          <el-input v-model="taskForm.input_url" />
        </el-form-item>
        <el-form-item v-if="taskMode === 'text'" label="Input Text" prop="input_text">
          <el-input v-model="taskForm.input_text" type="textarea" :rows="8" maxlength="20000" show-word-limit />
        </el-form-item>
        <el-form-item v-if="taskMode === 'file'" label="File">
          <el-upload
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            :file-list="taskFileList"
            :on-change="handleTaskFileChange"
            :on-remove="handleTaskFileRemove"
            class="upload-control"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">Drop image or PDF here</div>
            <template #tip>
              <div class="el-upload__tip">png, jpg, webp, tiff, pdf up to 20MB</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="taskMode === 'text'" label="File Name">
          <el-input v-model="taskForm.original_filename" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTaskDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTask">
          Create
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showTaskDetailDialog" size="640px" title="OCR Result">
      <div v-if="selectedTask" class="task-detail">
        <div class="detail-head">
          <div>
            <h2>{{ selectedTask.name }}</h2>
            <p>{{ selectedTask.project_name || '--' }} / {{ selectedTask.engine_name || '--' }}</p>
          </div>
          <el-tag :type="getTaskStatusType(selectedTask.status)">{{ selectedTask.status }}</el-tag>
        </div>

        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="Source">{{ selectedTask.source_type }}</el-descriptions-item>
          <el-descriptions-item label="Pages">{{ selectedTask.page_count || taskPages.length || 0 }}</el-descriptions-item>
          <el-descriptions-item label="File">{{ selectedTask.original_filename || '--' }}</el-descriptions-item>
          <el-descriptions-item label="Created">{{ formatDate(selectedTask.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="quality-panel">
          <div class="quality-item">
            <span>Confidence</span>
            <strong>{{ confidenceLabel(selectedTask.confidence) }}</strong>
          </div>
          <div class="quality-item">
            <span>Review State</span>
            <strong>{{ ocrReviewState(selectedTask) }}</strong>
          </div>
          <div class="quality-item">
            <span>Import Readiness</span>
            <strong>{{ selectedTask.status === 'succeeded' ? 'Ready' : 'Blocked' }}</strong>
          </div>
        </div>

        <div v-if="sourcePreviewUrl(selectedTask)" class="result-section">
          <div class="section-title">Source Preview</div>
          <div class="source-preview">
            <img
              v-if="previewKind(selectedTask) === 'image'"
              :src="sourcePreviewUrl(selectedTask)"
              :alt="selectedTask.original_filename || selectedTask.name"
            />
            <iframe
              v-else-if="previewKind(selectedTask) === 'pdf'"
              :src="sourcePreviewUrl(selectedTask)"
              title="OCR source preview"
            />
            <el-alert
              v-else
              type="info"
              :closable="false"
              title="Preview is not available for this source type"
            />
          </div>
        </div>

        <div class="result-section">
          <div class="section-title">Extracted Text</div>
          <pre class="result-text">{{ selectedTask.extracted_text || selectedTask.error_message || '--' }}</pre>
        </div>

        <div class="result-section">
          <div class="section-title">Pages</div>
          <el-empty v-if="!loadingTaskPages && !taskPages.length" description="No page result" />
          <div v-loading="loadingTaskPages" class="page-result-list">
            <div v-for="page in taskPages" :key="page.id || page.page_number" class="page-result-item">
              <div class="page-result-header">
                <div class="page-title-line">
                  <span>Page {{ page.page_number }}</span>
                  <el-tag
                    v-if="page.metadata?.review_state === 'revised'"
                    size="small"
                    type="success"
                  >
                    Revised
                  </el-tag>
                </div>
                <div class="page-actions">
                  <el-tag
                    v-if="page.confidence !== null && page.confidence !== undefined"
                    size="small"
                    :type="pageConfidenceType(page.confidence)"
                  >
                    {{ Number(page.confidence).toFixed(2) }}
                  </el-tag>
                  <el-button
                    v-if="editingPageId !== page.id"
                    size="small"
                    text
                    @click="startPageRevision(page)"
                  >
                    Edit
                  </el-button>
                  <template v-else>
                    <el-button size="small" text @click="cancelPageRevision">Cancel</el-button>
                    <el-button
                      size="small"
                      type="primary"
                      :loading="revisionSaving"
                      @click="savePageRevision(page)"
                    >
                      Save
                    </el-button>
                  </template>
                </div>
              </div>
              <div class="page-quality-note">{{ pageQualityNote(page) }}</div>
              <el-input
                v-if="editingPageId === page.id"
                v-model="pageRevisionText"
                type="textarea"
                :rows="8"
                resize="vertical"
              />
              <pre v-else>{{ page.text || '--' }}</pre>
              <div v-if="page.metadata?.revisions?.length" class="revision-note">
                {{ page.metadata.revisions.length }} revision(s), latest {{ formatDate(lastRevisionAt(page)) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="showBatchDetailDialog" size="720px" title="OCR Batch">
      <div v-if="selectedBatch" class="batch-detail">
        <div class="detail-head">
          <div>
            <h2>{{ selectedBatch.name }}</h2>
            <p>{{ selectedBatch.project_name || '--' }} / {{ selectedBatch.engine_name || '--' }}</p>
          </div>
          <el-tag :type="getTaskStatusType(selectedBatch.status)">{{ selectedBatch.status }}</el-tag>
        </div>

        <div class="batch-progress">
          <div class="batch-progress-item">
            <span>Total</span>
            <strong>{{ selectedBatch.total_tasks || 0 }}</strong>
          </div>
          <div class="batch-progress-item">
            <span>Succeeded</span>
            <strong>{{ selectedBatch.succeeded_tasks || 0 }}</strong>
          </div>
          <div class="batch-progress-item">
            <span>Failed</span>
            <strong>{{ selectedBatch.failed_tasks || 0 }}</strong>
          </div>
          <div class="batch-progress-item">
            <span>Cancelled</span>
            <strong>{{ selectedBatch.cancelled_tasks || 0 }}</strong>
          </div>
        </div>

        <el-table v-loading="loadingBatchTasks" :data="batchTasks" style="width: 100%">
          <el-table-column prop="name" label="Task" min-width="180" />
          <el-table-column prop="source_type" label="Source" width="100" />
          <el-table-column prop="page_count" label="Pages" width="90">
            <template #default="{ row }">{{ row.page_count || 0 }}</template>
          </el-table-column>
          <el-table-column prop="status" label="Status" width="120">
            <template #default="{ row }">
              <el-tag :type="getTaskStatusType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Actions" width="160">
            <template #default="{ row }">
              <el-button size="small" @click="openTaskDetail(row)">
                Detail
              </el-button>
              <el-button
                size="small"
                type="primary"
                :loading="isTaskRunning(row)"
                :disabled="row.status === 'cancelled'"
                @click="handleRunTask(row)"
              >
                Run
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <el-dialog v-model="showImportDialog" title="Import OCR To Knowledge Base" width="520px">
      <el-form label-width="130px">
        <el-form-item label="Knowledge Base">
          <el-select v-model="importForm.knowledge_base" filterable style="width: 100%">
            <el-option
              v-for="base in knowledgeBases"
              :key="base.id"
              :label="`${base.name} / ${base.project_name}`"
              :value="base.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Source">
          <el-input :model-value="importSourceLabel" disabled />
        </el-form-item>
        <el-form-item label="Text Version">
          <el-radio-group v-model="importForm.text_version">
            <el-radio-button label="revised">Revised</el-radio-button>
            <el-radio-button label="original">Original OCR</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showImportDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">
          Import And Index
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Files, Operation, Plus, Refresh, Search, Setting, UploadFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { getUnifiedProjects } from '@/api/core'
import { getKnowledgeBases, importOcrKnowledgeDocument } from '@/api/knowledge-base'
import {
  cancelOcrBatch,
  cancelOcrTask,
  createOcrBatch,
  createOcrEngine,
  createOcrTask,
  getOcrBatches,
  getOcrEngines,
  getOcrServiceSummary,
  getOcrTask,
  getOcrTaskPages,
  getOcrTasks,
  preflightOcrEngine,
  reviseOcrTaskPage,
  retryOcrTask,
  runOcrBatch,
  runPendingOcrTasks,
  runOcrTask,
  setDefaultOcrEngine,
  uploadOcrBatch,
  uploadOcrTask
} from '@/api/ocr-service'

const route = useRoute()
const loading = ref(false)
const submitting = ref(false)
const runningPending = ref(false)
const importing = ref(false)
const bulkRunning = ref(false)
const bulkRetrying = ref(false)
const bulkCancelling = ref(false)
const activeTab = ref('tasks')
const engines = ref([])
const batches = ref([])
const tasks = ref([])
const projects = ref([])
const knowledgeBases = ref([])
const runningTasks = ref({})
const runningBatches = ref({})
const preflightingEngines = ref({})
const lastPreflight = ref(null)
const taskMode = ref('text')
const batchMode = ref('text')
const taskFile = ref(null)
const taskFileList = ref([])
const batchFiles = ref([])
const batchFileList = ref([])
const showEngineDialog = ref(false)
const showBatchDialog = ref(false)
const showTaskDialog = ref(false)
const showTaskDetailDialog = ref(false)
const showBatchDetailDialog = ref(false)
const showImportDialog = ref(false)
const engineFormRef = ref()
const batchFormRef = ref()
const taskFormRef = ref()
const summary = reactive({})
const selectedTask = ref(null)
const selectedBatch = ref(null)
const taskPages = ref([])
const batchTasks = ref([])
const selectedTasks = ref([])
const loadingTaskPages = ref(false)
const loadingBatchTasks = ref(false)
const editingPageId = ref(null)
const pageRevisionText = ref('')
const revisionSaving = ref(false)
const importTarget = ref(null)
const importTargetType = ref('task')
const engineForm = reactive({
  name: '',
  engine_type: 'tesseract',
  base_url: '',
  model_name: '',
  credential_ref: '',
  is_default: false,
  is_active: true,
  options: {}
})
const taskForm = reactive({
  project: null,
  engine: null,
  name: '',
  source_type: 'text',
  input_url: '',
  input_text: '',
  original_filename: ''
})
const batchForm = reactive({
  project: null,
  engine: null,
  name: '',
  run_immediately: false
})
const batchItems = ref([])
const importForm = reactive({
  knowledge_base: null,
  text_version: 'revised'
})
const taskFilters = reactive({
  project: null,
  status: '',
  source_type: '',
  search: ''
})
const batchFilters = reactive({
  project: null,
  status: '',
  search: ''
})

const engineRules = computed(() => ({
  name: [{ required: true, message: 'Enter name', trigger: 'blur' }],
  engine_type: [{ required: true, message: 'Select type', trigger: 'change' }]
}))
const taskRules = computed(() => ({
  name: [{ required: true, message: 'Enter name', trigger: 'blur' }],
  source_type: [{ required: true, message: 'Select source type', trigger: 'change' }],
  input_text: taskMode.value === 'text'
    ? [{ required: true, message: 'Enter text to extract', trigger: 'blur' }]
    : []
}))
const batchRules = computed(() => ({
  name: [{ required: true, message: 'Enter name', trigger: 'blur' }]
}))

const normalizeListResponse = (payload) => {
  if (Array.isArray(payload)) {
    return payload
  }
  return payload?.results || []
}

const formatDate = (value) => {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--'
}

const getTaskStatusType = (status) => {
  const typeMap = {
    pending: 'info',
    running: 'warning',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return typeMap[status] || 'info'
}

const confidenceLabel = (value) => {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  return Number(value).toFixed(2)
}

const pageConfidenceType = (confidence) => {
  const value = Number(confidence)
  if (Number.isNaN(value)) {
    return 'info'
  }
  if (value >= 0.85) {
    return 'success'
  }
  if (value >= 0.65) {
    return 'warning'
  }
  return 'danger'
}

const ocrReviewState = (task) => {
  if (!task || task.status !== 'succeeded') {
    return 'Needs run'
  }
  const confidence = Number(task.confidence)
  if (!Number.isNaN(confidence) && confidence < 0.65) {
    return 'Needs review'
  }
  if (!task.extracted_text?.trim()) {
    return 'No text'
  }
  return 'Passed'
}

const pageQualityNote = (page) => {
  const textLength = String(page.text || '').trim().length
  const confidence = Number(page.confidence)
  if (!textLength) {
    return 'No text extracted from this page.'
  }
  if (!Number.isNaN(confidence) && confidence < 0.65) {
    return 'Low confidence; manual verification recommended.'
  }
  return `${textLength} characters extracted.`
}

const lastRevisionAt = (page) => {
  const revisions = Array.isArray(page?.metadata?.revisions) ? page.metadata.revisions : []
  return revisions[revisions.length - 1]?.created_at
}

const sourcePreviewUrl = (task) => {
  return task?.input_file || task?.input_url || ''
}

const previewKind = (task) => {
  const mimeType = String(task?.mime_type || '').toLowerCase()
  const url = String(sourcePreviewUrl(task)).toLowerCase()
  if (mimeType.includes('pdf') || url.endsWith('.pdf')) {
    return 'pdf'
  }
  if (mimeType.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|tiff?)($|\?)/.test(url)) {
    return 'image'
  }
  return 'other'
}

const isTaskRunning = (task) => {
  return Boolean(runningTasks.value[task.id])
}

const isBatchRunning = (batch) => {
  return Boolean(runningBatches.value[batch.id])
}

const isPreflighting = (engine) => {
  return Boolean(preflightingEngines.value[engine.id])
}

const importSourceLabel = computed(() => {
  if (!importTarget.value) {
    return '--'
  }
  if (importTargetType.value === 'tasks') {
    return `Selected tasks / ${importTarget.value.length || 0} items`
  }
  return `${importTargetType.value === 'batch' ? 'Batch' : 'Task'} / ${importTarget.value.name}`
})

const selectedSucceededTasks = computed(() => {
  return selectedTasks.value.filter(task => task.status === 'succeeded')
})

const fetchProjects = async () => {
  const response = await getUnifiedProjects({ page: 1, page_size: 200 })
  projects.value = normalizeListResponse(response.data)
}

const fetchKnowledgeBases = async () => {
  const response = await getKnowledgeBases({ page: 1, page_size: 200 })
  knowledgeBases.value = normalizeListResponse(response.data)
}

const fetchSummary = async () => {
  const response = await getOcrServiceSummary()
  Object.keys(summary).forEach(key => delete summary[key])
  Object.assign(summary, response.data || {})
}

const fetchEngines = async () => {
  const response = await getOcrEngines({ page: 1, page_size: 200 })
  engines.value = normalizeListResponse(response.data)
}

const fetchBatches = async () => {
  const params = {
    page: 1,
    page_size: 200
  }
  if (batchFilters.project) {
    params.project = batchFilters.project
  }
  if (batchFilters.status) {
    params.status = batchFilters.status
  }
  if (batchFilters.search.trim()) {
    params.search = batchFilters.search.trim()
  }
  const response = await getOcrBatches(params)
  batches.value = normalizeListResponse(response.data)
}

const fetchTasks = async () => {
  const params = {
    page: 1,
    page_size: 200
  }
  if (taskFilters.project) {
    params.project = taskFilters.project
  }
  if (taskFilters.status) {
    params.status = taskFilters.status
  }
  if (taskFilters.source_type) {
    params.source_type = taskFilters.source_type
  }
  if (taskFilters.search.trim()) {
    params.search = taskFilters.search.trim()
  }
  const response = await getOcrTasks(params)
  tasks.value = normalizeListResponse(response.data)
}

const loadPage = async () => {
  const focusTaskId = route.query?.task ? String(route.query.task) : ''
  applyRouteFilters()
  if (focusTaskId) {
    activeTab.value = 'tasks'
  }
  loading.value = true
  try {
    await Promise.all([fetchProjects(), fetchKnowledgeBases(), fetchSummary(), fetchEngines(), fetchBatches(), fetchTasks()])
    if (focusTaskId) {
      await focusOcrTask(focusTaskId)
    }
  } catch (error) {
    ElMessage.error('Failed to load OCR service')
  } finally {
    loading.value = false
  }
}

const applyRouteFilters = () => {
  if (route.query?.tab) {
    activeTab.value = String(route.query.tab)
  }
  if (route.query?.task_status) {
    taskFilters.status = String(route.query.task_status)
  }
  if (route.query?.source_type) {
    taskFilters.source_type = String(route.query.source_type)
  }
  if (route.query?.batch_status) {
    batchFilters.status = String(route.query.batch_status)
  }
}

const focusOcrTask = async (taskId) => {
  try {
    const response = await getOcrTask(taskId)
    tasks.value = [response.data]
    taskFilters.project = null
    taskFilters.status = ''
    taskFilters.source_type = ''
    taskFilters.search = response.data.name || String(taskId)
  } catch (error) {
    ElMessage.warning('OCR source task is not accessible')
  }
}

const openTaskDetail = async (task) => {
  selectedTask.value = task
  taskPages.value = []
  editingPageId.value = null
  pageRevisionText.value = ''
  showTaskDetailDialog.value = true
  if (task.status !== 'succeeded') {
    return
  }
  loadingTaskPages.value = true
  try {
    const response = await getOcrTaskPages(task.id)
    taskPages.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    ElMessage.error('Failed to load OCR pages')
  } finally {
    loadingTaskPages.value = false
  }
}

const startPageRevision = (page) => {
  editingPageId.value = page.id
  pageRevisionText.value = page.text || ''
}

const cancelPageRevision = () => {
  editingPageId.value = null
  pageRevisionText.value = ''
}

const savePageRevision = async (page) => {
  if (!selectedTask.value || !pageRevisionText.value.trim()) {
    ElMessage.warning('Enter revised text')
    return
  }
  revisionSaving.value = true
  try {
    const response = await reviseOcrTaskPage(selectedTask.value.id, {
      page_id: page.id,
      page_number: page.page_number,
      text: pageRevisionText.value
    })
    const nextTask = response.data?.task
    const nextPage = response.data?.page
    if (nextTask) {
      selectedTask.value = nextTask
      updateTaskInLists(nextTask)
    }
    if (nextPage) {
      taskPages.value = taskPages.value.map(item => item.id === nextPage.id ? nextPage : item)
    }
    cancelPageRevision()
    ElMessage.success('OCR page revised')
  } catch (error) {
    ElMessage.error('Failed to revise OCR page')
  } finally {
    revisionSaving.value = false
  }
}

const openBatchDetail = async (batch) => {
  selectedBatch.value = batch
  batchTasks.value = []
  showBatchDetailDialog.value = true
  loadingBatchTasks.value = true
  try {
    const response = await getOcrTasks({
      batch: batch.id,
      page: 1,
      page_size: 200
    })
    batchTasks.value = normalizeListResponse(response.data)
  } catch (error) {
    ElMessage.error('Failed to load batch tasks')
  } finally {
    loadingBatchTasks.value = false
  }
}

const openImportDialog = (type, target) => {
  importTargetType.value = type
  importTarget.value = target
  importForm.knowledge_base = knowledgeBases.value[0]?.id || null
  importForm.text_version = 'revised'
  showImportDialog.value = true
}

const submitImport = async () => {
  if (!importForm.knowledge_base || !importTarget.value) {
    ElMessage.warning('Select a knowledge base')
    return
  }
  importing.value = true
  try {
    const payload = {
      knowledge_base: importForm.knowledge_base,
      text_version: importForm.text_version
    }
    if (importTargetType.value === 'batch') {
      payload.ocr_batch = importTarget.value.id
    } else if (importTargetType.value === 'tasks') {
      payload.ocr_tasks = importTarget.value.map(task => task.id)
    } else {
      payload.ocr_task = importTarget.value.id
    }
    await importOcrKnowledgeDocument(payload)
    const targetName = knowledgeBases.value.find(base => base.id === importForm.knowledge_base)?.name || 'knowledge base'
    ElMessage.success(`OCR result imported to ${targetName}`)
    showImportDialog.value = false
    await fetchKnowledgeBases()
  } catch (error) {
    ElMessage.error('Failed to import OCR result')
  } finally {
    importing.value = false
  }
}

const openEngineDialog = () => {
  Object.assign(engineForm, {
    name: '',
    engine_type: 'tesseract',
    base_url: '',
    model_name: '',
    credential_ref: '',
    is_default: false,
    is_active: true,
    options: {}
  })
  engineFormRef.value?.clearValidate()
  showEngineDialog.value = true
}

const resetBatchItems = () => {
  batchItems.value = [
    {
      key: Date.now(),
      name: '',
      input_text: ''
    }
  ]
}

const openBatchDialog = () => {
  batchMode.value = 'text'
  Object.assign(batchForm, {
    project: null,
    engine: engines.value.find(engine => engine.is_default)?.id || null,
    name: '',
    run_immediately: false
  })
  resetBatchItems()
  batchFiles.value = []
  batchFileList.value = []
  batchFormRef.value?.clearValidate()
  showBatchDialog.value = true
}

const addBatchItem = () => {
  batchItems.value = [
    ...batchItems.value,
    {
      key: Date.now() + batchItems.value.length,
      name: '',
      input_text: ''
    }
  ]
}

const removeBatchItem = (index) => {
  if (batchItems.value.length <= 1) {
    return
  }
  batchItems.value = batchItems.value.filter((item, itemIndex) => itemIndex !== index)
}

const openTaskDialog = () => {
  taskMode.value = 'text'
  Object.assign(taskForm, {
    project: null,
    engine: engines.value.find(engine => engine.is_default)?.id || null,
    name: '',
    source_type: 'text',
    input_url: '',
    input_text: '',
    original_filename: ''
  })
  taskFile.value = null
  taskFileList.value = []
  taskFormRef.value?.clearValidate()
  showTaskDialog.value = true
}

const handleTaskFileChange = (uploadFile, uploadFiles) => {
  taskFile.value = uploadFile.raw
  taskFileList.value = uploadFiles.slice(-1)
  if (!taskForm.name && uploadFile.name) {
    taskForm.name = uploadFile.name
  }
  return false
}

const handleTaskFileRemove = () => {
  taskFile.value = null
  taskFileList.value = []
}

const handleBatchFileChange = (uploadFile, uploadFiles) => {
  batchFiles.value = uploadFiles.map(file => file.raw).filter(Boolean)
  batchFileList.value = uploadFiles
  if (!batchForm.name && uploadFile.name) {
    batchForm.name = `OCR Batch - ${uploadFile.name}`
  }
  return false
}

const handleBatchFileRemove = (uploadFile, uploadFiles) => {
  batchFiles.value = uploadFiles.map(file => file.raw).filter(Boolean)
  batchFileList.value = uploadFiles
}

const submitEngine = async () => {
  if (!engineFormRef.value) {
    return
  }
  try {
    await engineFormRef.value.validate()
  } catch (error) {
    return
  }

  submitting.value = true
  try {
    await createOcrEngine({ ...engineForm })
    ElMessage.success('OCR engine created')
    showEngineDialog.value = false
    await Promise.all([fetchSummary(), fetchEngines()])
  } catch (error) {
    ElMessage.error('Failed to create OCR engine')
  } finally {
    submitting.value = false
  }
}

const submitBatch = async () => {
  if (!batchFormRef.value) {
    return
  }
  try {
    await batchFormRef.value.validate()
  } catch (error) {
    return
  }

  submitting.value = true
  try {
    if (batchMode.value === 'file') {
      if (!batchFiles.value.length) {
        ElMessage.warning('Add at least one OCR file')
        return
      }
      const formData = new FormData()
      if (batchForm.project) {
        formData.append('project', batchForm.project)
      }
      if (batchForm.engine) {
        formData.append('engine', batchForm.engine)
      }
      formData.append('name', batchForm.name)
      formData.append('run_immediately', batchForm.run_immediately ? 'true' : 'false')
      batchFiles.value.forEach(file => {
        formData.append('files', file)
      })
      await uploadOcrBatch(formData)
    } else {
      const items = batchItems.value
        .filter(item => item.input_text.trim())
        .map((item, index) => ({
          name: item.name || `${batchForm.name} #${index + 1}`,
          source_type: 'text',
          input_text: item.input_text
        }))
      if (!items.length) {
        ElMessage.warning('Add at least one OCR item')
        return
      }
      await createOcrBatch({
        ...batchForm,
        items
      })
    }
    ElMessage.success('OCR batch created')
    showBatchDialog.value = false
    activeTab.value = 'batches'
    await Promise.all([fetchSummary(), fetchBatches(), fetchTasks()])
  } catch (error) {
    ElMessage.error('Failed to create OCR batch')
  } finally {
    submitting.value = false
  }
}

const submitTask = async () => {
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
    if (taskMode.value === 'file') {
      if (!taskFile.value) {
        ElMessage.warning('Select a file')
        return
      }
      const formData = new FormData()
      if (taskForm.project) {
        formData.append('project', taskForm.project)
      }
      if (taskForm.engine) {
        formData.append('engine', taskForm.engine)
      }
      formData.append('name', taskForm.name)
      formData.append('file', taskFile.value)
      await uploadOcrTask(formData)
    } else {
      await createOcrTask({ ...taskForm })
    }
    ElMessage.success('OCR task created')
    showTaskDialog.value = false
    await Promise.all([fetchSummary(), fetchBatches(), fetchTasks()])
  } catch (error) {
    ElMessage.error('Failed to create OCR task')
  } finally {
    submitting.value = false
  }
}

const handleRunTask = async (task) => {
  runningTasks.value = {
    ...runningTasks.value,
    [task.id]: true
  }
  try {
    const response = await runOcrTask(task.id)
    const nextTask = response.data
    tasks.value = tasks.value.map(item => item.id === nextTask.id ? nextTask : item)
    batchTasks.value = batchTasks.value.map(item => item.id === nextTask.id ? nextTask : item)
    if (nextTask.status === 'succeeded') {
      ElMessage.success('OCR task completed')
    } else {
      ElMessage.warning(nextTask.error_message || 'OCR task finished with warnings')
    }
    await Promise.all([fetchSummary(), fetchBatches()])
  } catch (error) {
    ElMessage.error('Failed to run OCR task')
  } finally {
    runningTasks.value = {
      ...runningTasks.value,
      [task.id]: false
    }
  }
}

const updateTaskInLists = (nextTask) => {
  tasks.value = tasks.value.map(item => item.id === nextTask.id ? nextTask : item)
  batchTasks.value = batchTasks.value.map(item => item.id === nextTask.id ? nextTask : item)
  selectedTasks.value = selectedTasks.value.map(item => item.id === nextTask.id ? nextTask : item)
}

const handleTaskSelectionChange = (selection) => {
  selectedTasks.value = selection
}

const handleBulkRunTasks = async () => {
  const runnable = selectedTasks.value.filter(task => task.status !== 'cancelled')
  if (!runnable.length) {
    ElMessage.warning('No runnable task selected')
    return
  }
  bulkRunning.value = true
  let succeeded = 0
  try {
    for (const task of runnable) {
      const response = await runOcrTask(task.id)
      updateTaskInLists(response.data)
      if (response.data.status === 'succeeded') {
        succeeded += 1
      }
    }
    ElMessage.success(`Ran ${runnable.length} tasks, ${succeeded} succeeded`)
    await Promise.all([fetchSummary(), fetchBatches()])
  } catch (error) {
    ElMessage.error('Failed to run selected OCR tasks')
  } finally {
    bulkRunning.value = false
  }
}

const handleBulkRetryTasks = async () => {
  const failed = selectedTasks.value.filter(task => task.status === 'failed')
  if (!failed.length) {
    ElMessage.warning('No failed task selected')
    return
  }
  bulkRetrying.value = true
  try {
    for (const task of failed) {
      const response = await retryOcrTask(task.id)
      updateTaskInLists(response.data)
    }
    ElMessage.success(`Retried ${failed.length} failed tasks`)
    await Promise.all([fetchSummary(), fetchBatches()])
  } catch (error) {
    ElMessage.error('Failed to retry selected OCR tasks')
  } finally {
    bulkRetrying.value = false
  }
}

const handleBulkCancelTasks = async () => {
  const cancellable = selectedTasks.value.filter(task => ['pending', 'running'].includes(task.status))
  if (!cancellable.length) {
    ElMessage.warning('No cancellable task selected')
    return
  }
  bulkCancelling.value = true
  try {
    for (const task of cancellable) {
      const response = await cancelOcrTask(task.id)
      updateTaskInLists(response.data)
    }
    ElMessage.success(`Cancelled ${cancellable.length} tasks`)
    await Promise.all([fetchSummary(), fetchBatches()])
  } catch (error) {
    ElMessage.error('Failed to cancel selected OCR tasks')
  } finally {
    bulkCancelling.value = false
  }
}

const handleRunBatch = async (batch) => {
  runningBatches.value = {
    ...runningBatches.value,
    [batch.id]: true
  }
  try {
    const response = await runOcrBatch(batch.id)
    const nextBatch = response.data
    batches.value = batches.value.map(item => item.id === nextBatch.id ? nextBatch : item)
    ElMessage.success('OCR batch completed')
    await Promise.all([fetchSummary(), fetchTasks()])
  } catch (error) {
    ElMessage.error('Failed to run OCR batch')
  } finally {
    runningBatches.value = {
      ...runningBatches.value,
      [batch.id]: false
    }
  }
}

const handleCancelBatch = async (batch) => {
  try {
    const response = await cancelOcrBatch(batch.id)
    const nextBatch = response.data
    batches.value = batches.value.map(item => item.id === nextBatch.id ? nextBatch : item)
    ElMessage.success('OCR batch cancelled')
    await Promise.all([fetchSummary(), fetchTasks()])
  } catch (error) {
    ElMessage.error('Failed to cancel OCR batch')
  }
}

const handleRunPending = async () => {
  runningPending.value = true
  try {
    const response = await runPendingOcrTasks()
    ElMessage.success(`OCR completed: ${response.data.succeeded || 0} succeeded, ${response.data.failed || 0} failed`)
    await Promise.all([fetchSummary(), fetchBatches(), fetchTasks()])
  } catch (error) {
    ElMessage.error('Failed to run pending OCR tasks')
  } finally {
    runningPending.value = false
  }
}

const handleSetDefault = async (engine) => {
  try {
    await setDefaultOcrEngine(engine.id)
    ElMessage.success('Default engine updated')
    await fetchEngines()
  } catch (error) {
    ElMessage.error('Failed to update default engine')
  }
}

const handlePreflight = async (engine) => {
  preflightingEngines.value = {
    ...preflightingEngines.value,
    [engine.id]: true
  }
  try {
    const response = await preflightOcrEngine(engine.id)
    lastPreflight.value = response.data
    if (response.data.ready) {
      ElMessage.success('OCR engine is ready')
    } else {
      ElMessage.warning('OCR engine needs attention')
    }
  } catch (error) {
    ElMessage.error('Failed to check OCR engine')
  } finally {
    preflightingEngines.value = {
      ...preflightingEngines.value,
      [engine.id]: false
    }
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
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
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

.text-preview {
  display: block;
  color: var(--el-text-color-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-detail {
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

.result-section {
  display: grid;
  gap: 8px;
}

.quality-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.quality-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);

  span {
    display: block;
    margin-bottom: 6px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 18px;
  }
}

.source-preview {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  min-height: 260px;
  overflow: hidden;
  background: var(--el-fill-color-lighter);

  img,
  iframe {
    display: block;
    width: 100%;
    height: 360px;
    border: 0;
    object-fit: contain;
    background: var(--el-bg-color);
  }
}

.section-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.result-text,
.page-result-item pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.55;
}

.result-text {
  max-height: 260px;
  overflow: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
}

.page-result-list {
  display: grid;
  gap: 10px;
}

.page-result-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}

.page-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.page-title-line,
.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.page-quality-note {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.revision-note {
  margin-top: 8px;
  color: var(--el-color-success);
  font-size: 12px;
}

.batch-detail {
  display: grid;
  gap: 16px;
}

.batch-progress {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.batch-progress-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);

  span {
    display: block;
    margin-bottom: 6px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 20px;
    line-height: 1;
  }
}

.upload-control {
  width: 100%;
}

.preflight-alert {
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

.task-toolbar {
  grid-template-columns: minmax(150px, 1fr) minmax(120px, 160px) minmax(120px, 160px) minmax(180px, 1.4fr) auto;
}

.batch-filter-toolbar {
  grid-template-columns: minmax(150px, 1fr) minmax(120px, 180px) minmax(180px, 1.4fr) auto;
}

.batch-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.batch-items {
  display: grid;
  gap: 12px;
  max-height: 360px;
  overflow: auto;
  padding-right: 4px;
}

.batch-item {
  display: grid;
  gap: 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}

.batch-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .task-toolbar,
  .batch-filter-toolbar {
    grid-template-columns: 1fr;
  }

  .quality-panel {
    grid-template-columns: 1fr;
  }
}
</style>
