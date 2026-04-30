import request from '@/utils/api'

export function getKnowledgeBaseSummary() {
  return request({
    url: '/knowledge-base/summary/',
    method: 'get'
  })
}

export function getKnowledgeBases(params) {
  return request({
    url: '/knowledge-base/bases/',
    method: 'get',
    params
  })
}

export function createKnowledgeBase(data) {
  return request({
    url: '/knowledge-base/bases/',
    method: 'post',
    data
  })
}

export function updateKnowledgeBase(id, data) {
  return request({
    url: `/knowledge-base/bases/${id}/`,
    method: 'patch',
    data
  })
}

export function deleteKnowledgeBase(id) {
  return request({
    url: `/knowledge-base/bases/${id}/`,
    method: 'delete'
  })
}

export function getKnowledgeDocuments(params) {
  return request({
    url: '/knowledge-base/documents/',
    method: 'get',
    params
  })
}

export function getKnowledgeChunks(params) {
  return request({
    url: '/knowledge-base/chunks/',
    method: 'get',
    params
  })
}

export function createKnowledgeDocument(data) {
  return request({
    url: '/knowledge-base/documents/',
    method: 'post',
    data
  })
}

export function uploadKnowledgeDocument(data) {
  return request({
    url: '/knowledge-base/documents/upload/',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export function importOcrKnowledgeDocument(data) {
  return request({
    url: '/knowledge-base/documents/import_ocr/',
    method: 'post',
    data
  })
}

export function importOcrBatchKnowledgeDocuments(data) {
  return request({
    url: '/knowledge-base/documents/import_ocr/',
    method: 'post',
    data
  })
}

export function indexKnowledgeDocument(id) {
  return request({
    url: `/knowledge-base/documents/${id}/index/`,
    method: 'post'
  })
}

export function archiveKnowledgeDocumentGovernance(id, data) {
  return request({
    url: `/knowledge-base/documents/${id}/archive-governance/`,
    method: 'post',
    data
  })
}

export function restoreKnowledgeDocumentGovernance(id, data) {
  return request({
    url: `/knowledge-base/documents/${id}/restore-governance/`,
    method: 'post',
    data
  })
}

export function cleanKnowledgeDocumentChunks(id, data) {
  return request({
    url: `/knowledge-base/documents/${id}/clean-chunks/`,
    method: 'post',
    data
  })
}

export function markKnowledgeDocumentDuplicate(id, data) {
  return request({
    url: `/knowledge-base/documents/${id}/mark-duplicate/`,
    method: 'post',
    data
  })
}

export function reindexKnowledgeBase(id) {
  return request({
    url: `/knowledge-base/bases/${id}/reindex/`,
    method: 'post'
  })
}

export function indexPendingKnowledgeDocuments(data) {
  return request({
    url: '/knowledge-base/maintenance/index-pending/',
    method: 'post',
    data
  })
}

export function getKnowledgeQueries(params) {
  return request({
    url: '/knowledge-base/queries/',
    method: 'get',
    params
  })
}

export function askKnowledgeBase(data) {
  return request({
    url: '/knowledge-base/queries/ask/',
    method: 'post',
    data
  })
}
