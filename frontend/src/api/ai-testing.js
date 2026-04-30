import request from '@/utils/api'

export function getAiTestingSummary() {
  return request({
    url: '/ai-testing/summary/',
    method: 'get'
  })
}

export function getAiTestingTasks(params) {
  return request({
    url: '/ai-testing/tasks/',
    method: 'get',
    params
  })
}

export function createAiTestingTask(data) {
  return request({
    url: '/ai-testing/tasks/',
    method: 'post',
    data
  })
}

export function updateAiTestingTask(id, data) {
  return request({
    url: `/ai-testing/tasks/${id}/`,
    method: 'patch',
    data
  })
}

export function deleteAiTestingTask(id) {
  return request({
    url: `/ai-testing/tasks/${id}/`,
    method: 'delete'
  })
}

export function runAiTestingTask(id, data) {
  return request({
    url: `/ai-testing/tasks/${id}/run/`,
    method: 'post',
    data
  })
}

export function getAiTestingRuns(params) {
  return request({
    url: '/ai-testing/runs/',
    method: 'get',
    params
  })
}

export function startAiTestingRun(id) {
  return request({
    url: `/ai-testing/runs/${id}/start/`,
    method: 'post'
  })
}

export function runPendingAiTestingRuns(data) {
  return request({
    url: '/ai-testing/runs/run_pending/',
    method: 'post',
    data
  })
}

export function cancelAiTestingRun(id) {
  return request({
    url: `/ai-testing/runs/${id}/cancel/`,
    method: 'post'
  })
}
