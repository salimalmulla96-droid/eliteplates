const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// Global error notification callback
let errorNotificationCallback = null

export function setErrorNotification(callback) {
  errorNotificationCallback = callback
}

async function request(path, options = {}) {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options
    })
    if (!response.ok) {
      const text = await response.text()
      let message = text || `Request failed: ${response.status}`
      try {
        const parsed = JSON.parse(text)
        message = parsed.message || parsed.error || parsed.detail?.message || parsed.detail || message
      } catch {
        // Keep raw text when the backend does not return JSON.
      }
      if (typeof message !== 'string') message = JSON.stringify(message)
      const error = new Error(message)
      error.status = response.status
      throw error
    }
    return response.json()
  } catch (error) {
    // Network errors (CORS, connection refused, etc.)
    if (error instanceof TypeError && error.message.includes('fetch')) {
      const connectionError = new Error('Backend connection failed. Make sure FastAPI is running on http://127.0.0.1:8000.')
      connectionError.isConnectionError = true
      if (errorNotificationCallback) {
        errorNotificationCallback(connectionError.message)
      }
      throw connectionError
    }
    throw error
  }
}

export const api = {
  options: () => request('/api/options'),
  getOptions: () => request('/api/options'),
  search: (body) => request('/api/search', { method: 'POST', body: JSON.stringify(body) }),
  startSearch: (body) => request('/api/search/start', { method: 'POST', body: JSON.stringify(body) }),
  searchProgress: (jobId) => request(`/api/search/progress/${jobId}`),
  searchResult: (jobId) => request(`/api/search/result/${jobId}`),
  sellerPlates: (body) => request('/api/seller/plates', { method: 'POST', body: JSON.stringify(body) }),
  history: () => request('/api/history'),
  runHistory: (id) => request('/api/history/run', { method: 'POST', body: JSON.stringify({ id }) }),
  deleteHistory: (id) => request(`/api/history/${id}`, { method: 'DELETE' }),
  clearHistory: () => request('/api/history', { method: 'DELETE' }),
  favorites: () => request('/api/favorites'),
  addFavorite: (listing) => request('/api/favorites', { method: 'POST', body: JSON.stringify({ listing }) }),
  deleteFavorite: (id) => request(`/api/favorites/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearFavorites: () => request('/api/favorites', { method: 'DELETE' }),
  sellers: () => request('/api/sellers'),
  exportCsv: (rows, filename_prefix = 'xplate_results') => request('/api/export/csv', { method: 'POST', body: JSON.stringify({ rows, filename_prefix }) }),
  exportExcel: (rows, filename_prefix = 'xplate_results') => request('/api/export/excel', { method: 'POST', body: JSON.stringify({ rows, filename_prefix }) }),
  settings: () => request('/api/settings'),
  saveSettings: (settings) => request('/api/settings', { method: 'POST', body: JSON.stringify({ settings }) }),
  verifyTelegram: (body) => request('/api/telegram/verify', { method: 'POST', body: JSON.stringify(body) }),
  testTelegramChannel: (body) => request('/api/telegram/test-channel', { method: 'POST', body: JSON.stringify(body || {}) }),
  getInstagramSettings: () => request('/api/instagram/settings'),
  saveInstagramSettings: (settings) => request('/api/instagram/settings', { method: 'POST', body: JSON.stringify({ settings }) }),
  verifyInstagramProvider: (settings) => request('/api/instagram/verify-provider', { method: 'POST', body: JSON.stringify({ settings }) }),
  runInstagramNow: () => request('/api/instagram/run-now', { method: 'POST' }),
  resetInstagramBaseline: () => request('/api/instagram/reset-baseline', { method: 'POST' }),
  sendLatestInstagram: () => request('/api/instagram/send-latest', { method: 'POST' }),
  debugInstagramOcr: () => request('/api/instagram/debug-ocr', { method: 'POST' }),
  debug: () => request('/api/debug'),
  dashboardSummary: () => request('/api/dashboard/summary'),
  backupSummary: () => request('/api/backup/summary'),
  health: () => request('/api/health'),
}

export async function getSellerPlates(payload) {
  const response = await fetch(`${API_BASE_URL}/api/seller/plates`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || 'Failed to load seller plates')
  }

  return response.json()
}

// Alerts API
export async function getAlerts() {
  return request('/api/alerts')
}

export async function createAlert(payload) {
  return request('/api/alerts', { method: 'POST', body: JSON.stringify(payload) })
}

export async function updateAlert(alertId, payload) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export async function deleteAlert(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}`, { method: 'DELETE' })
}

export async function toggleAlert(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/toggle`, { method: 'POST' })
}

export async function disableOtherAlerts(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/disable-others`, { method: 'POST' })
}

export async function testTelegram(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/test-telegram`, { method: 'POST' })
}

export async function testTelegramChannel(payload = {}) {
  return request('/api/telegram/test-channel', { method: 'POST', body: JSON.stringify(payload) })
}

export async function previewAlertTelegram(payload) {
  return request('/api/alerts/preview', { method: 'POST', body: JSON.stringify(payload) })
}

export async function runAlertNow(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/run-now`, { method: 'POST' })
}

export async function debugAlertScan(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/debug-scan`, { method: 'POST' })
}

export async function forceSendTestListing(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/force-test-listing`, { method: 'POST' })
}

export async function resetAlertBaseline(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/reset-baseline`, { method: 'POST' })
}

export async function sendDailyRuleReport(alertId, date) {
  const query = new URLSearchParams({ date }).toString()
  return request(`/api/alerts/rules/${encodeURIComponent(alertId)}/send-daily-report?${query}`, { method: 'POST' })
}

export async function downloadDailyRuleReport(alertId, date) {
  const query = new URLSearchParams({ date }).toString()
  try {
    const response = await fetch(`${API_BASE_URL}/api/alerts/rules/${encodeURIComponent(alertId)}/daily-report?${query}`)
    if (!response.ok) {
      const text = await response.text()
      let message = text || 'Report generation failed.'
      try {
        const parsed = JSON.parse(text)
        message = parsed.message || parsed.error || parsed.detail || message
      } catch {
        // Keep the backend response as-is when it is not JSON.
      }
      const error = new Error(typeof message === 'string' ? message : JSON.stringify(message))
      error.status = response.status
      throw error
    }
    const blob = await response.blob()
    const disposition = response.headers.get('content-disposition') || ''
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i)
    const filename = filenameMatch?.[1] || `XPLATE REPORT ${date}.xlsx`
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(objectUrl)
    return { ok: true, filename }
  } catch (error) {
    if (error instanceof TypeError) {
      const connectionError = new Error('Backend server is not reachable.')
      connectionError.isConnectionError = true
      throw connectionError
    }
    throw error
  }
}

export async function getAlertLogs() {
  return request('/api/alerts/logs')
}

export async function clearAlertLogs() {
  return request('/api/alerts/logs', { method: 'DELETE' })
}

export async function stopAllAlerts() {
  return request('/api/alerts/stop-all', { method: 'POST' })
}

export async function clearAllAlerts() {
  return request('/api/alerts/clear-all', { method: 'DELETE' })
}
