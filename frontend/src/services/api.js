const API_BASE = import.meta.env.VITE_ANALYSIS_API_BASE_URL || '/analysis-api'

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.status = status
  }
}

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    let payload = null
    try { payload = await response.json() } catch { payload = null }
    if (response.status === 401 && !window.location.hash.includes('/login')) {
      window.location.hash = '#/login'
    }
    throw new ApiError(payload?.message || `请求失败（${response.status}）`, response.status)
  }
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  login: (body) => request('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/auth/me'),
  datasets: (search = '') => request(`/datasets?status=ready&search=${encodeURIComponent(search)}`),
  datasetTree: () => request('/datasets/tree'),
  dataset: (id) => request(`/datasets/${id}`),
  scan: () => request('/datasets/scan', { method: 'POST' }),
  analysisTypes: () => request('/analysis/types'),
  preview: (body) => request('/analysis/preview', { method: 'POST', body: JSON.stringify(body) }),
  startArc: (body) => request('/arc/tasks', { method: 'POST', body: JSON.stringify(body) }),
  arcResult: (id, table = false) => request(`/arc/tasks/${id}/result?include_table=${table}`),
  saveArc: (id) => request(`/arc/tasks/${id}/save`, { method: 'POST' }),
  jobs: () => request('/jobs'),
  users: () => request('/system/users'),
  userStatus: (id, active) => request(`/system/users/${id}/status`, {
    method: 'PUT', body: JSON.stringify({ active }),
  }),
}

export function arcSocketUrl(taskId) {
  const base = new URL(API_BASE, window.location.origin)
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  base.pathname = `${base.pathname.replace(/\/$/, '')}/arc/tasks/${taskId}/stream`
  base.search = ''
  return base.toString()
}

export function downloadUrl(path) {
  return `${API_BASE}${path}`
}
