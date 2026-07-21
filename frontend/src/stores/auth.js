import { reactive } from 'vue'
import { api } from '@/services/api'

export const authState = reactive({ user: null, managerUrl: '', ssoEnabled: false, loaded: false })

export async function loadCurrentUser(force = false) {
  if (authState.loaded && !force) return authState.user
  try {
    const result = await api.me()
    authState.user = result.user
    authState.managerUrl = result.managerUrl || ''
    authState.ssoEnabled = Boolean(result.ssoEnabled)
  } catch {
    authState.user = null
  } finally {
    authState.loaded = true
  }
  return authState.user
}

export async function clearCurrentUser() {
  try { await api.logout() } finally {
    authState.user = null
    authState.loaded = true
  }
}
