import request from '@/utils/api'

export function getOcrServiceSummary() {
  return request({
    url: '/ocr-service/summary/',
    method: 'get'
  })
}

export function getOcrEngines(params) {
  return request({
    url: '/ocr-service/engines/',
    method: 'get',
    params
  })
}

export function createOcrEngine(data) {
  return request({
    url: '/ocr-service/engines/',
    method: 'post',
    data
  })
}

export function setDefaultOcrEngine(id) {
  return request({
    url: `/ocr-service/engines/${id}/set_default/`,
    method: 'post'
  })
}

export function preflightOcrEngine(id) {
  return request({
    url: `/ocr-service/engines/${id}/preflight/`,
    method: 'get'
  })
}

export function getOcrTasks(params) {
  return request({
    url: '/ocr-service/tasks/',
    method: 'get',
    params
  })
}

export function getOcrTask(id) {
  return request({
    url: `/ocr-service/tasks/${id}/`,
    method: 'get'
  })
}

export function getOcrTaskPages(id) {
  return request({
    url: `/ocr-service/tasks/${id}/pages/`,
    method: 'get'
  })
}

export function reviseOcrTaskPage(id, data) {
  return request({
    url: `/ocr-service/tasks/${id}/revise-page/`,
    method: 'post',
    data
  })
}

export function getOcrPages(params) {
  return request({
    url: '/ocr-service/pages/',
    method: 'get',
    params
  })
}

export function getOcrBatches(params) {
  return request({
    url: '/ocr-service/batches/',
    method: 'get',
    params
  })
}

export function createOcrBatch(data) {
  return request({
    url: '/ocr-service/tasks/batch/',
    method: 'post',
    data
  })
}

export function uploadOcrBatch(data) {
  return request({
    url: '/ocr-service/tasks/batch_upload/',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export function runOcrBatch(id) {
  return request({
    url: `/ocr-service/batches/${id}/run/`,
    method: 'post'
  })
}

export function cancelOcrBatch(id) {
  return request({
    url: `/ocr-service/batches/${id}/cancel/`,
    method: 'post'
  })
}

export function createOcrTask(data) {
  return request({
    url: '/ocr-service/tasks/',
    method: 'post',
    data
  })
}

export function uploadOcrTask(data) {
  return request({
    url: '/ocr-service/tasks/upload/',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export function retryOcrTask(id) {
  return request({
    url: `/ocr-service/tasks/${id}/retry/`,
    method: 'post'
  })
}

export function runOcrTask(id) {
  return request({
    url: `/ocr-service/tasks/${id}/run/`,
    method: 'post'
  })
}

export function runPendingOcrTasks(data) {
  return request({
    url: '/ocr-service/tasks/run_pending/',
    method: 'post',
    data
  })
}

export function cancelOcrTask(id) {
  return request({
    url: `/ocr-service/tasks/${id}/cancel/`,
    method: 'post'
  })
}
