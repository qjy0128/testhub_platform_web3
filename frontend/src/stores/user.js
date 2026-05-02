import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/api'
import logger from '@/utils/logger'
import { navigateToLogin } from '@/utils/auth-nav'

// 解析 JWT exp（秒级 Unix 时间戳）→ 毫秒级到期时间。
function parseJwtExpiresAt(token) {
  if (!token) return 0
  try {
    const payload = token.split('.')[1]
    if (!payload) return 0
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '==='.slice((normalized.length + 3) % 4)
    const json = JSON.parse(atob(padded))
    return typeof json.exp === 'number' ? json.exp * 1000 : 0
  } catch (e) {
    return 0
  }
}

// 后端 ACCESS_TOKEN_LIFETIME = 60 分钟。仅在 JWT 解析失败时兜底。
const ACCESS_TOKEN_FALLBACK_MS = 60 * 60 * 1000

// 存储策略说明：
// - access token 用 sessionStorage：跨标签页不共享，关闭浏览器即清除，
//   把 XSS 长期持久化窃取窗口缩短到当前会话。
// - refresh token 由后端写入 httpOnly cookie，前端不直接持有，
//   也不再放进 localStorage（兼容期内仍接受 body 返回值，仅用于内存）。
const ACCESS_KEY = 'access_token'
const EXPIRES_KEY = 'token_expires_at'
const USER_KEY = 'th_user'

export const useUserStore = defineStore('user', () => {
  const user = ref(null)
  const accessToken = ref(sessionStorage.getItem(ACCESS_KEY) || '')
  const tokenExpiresAt = ref(parseInt(sessionStorage.getItem(EXPIRES_KEY) || '0'))
  // refresh token 仅保留在内存里作为 cookie 的兜底（兼容旧后端响应）；不再持久化。
  const refreshToken = ref('')

  let refreshTimer = null

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)

  const isTokenExpiringSoon = computed(() => {
    if (!tokenExpiresAt.value) return false
    return tokenExpiresAt.value - Date.now() < 5 * 60 * 1000
  })

  const isTokenExpired = computed(() => {
    if (!tokenExpiresAt.value) return false
    return Date.now() > tokenExpiresAt.value
  })

  function persistAccessToken(token) {
    accessToken.value = token
    const exp = parseJwtExpiresAt(token) || (Date.now() + ACCESS_TOKEN_FALLBACK_MS)
    tokenExpiresAt.value = exp
    sessionStorage.setItem(ACCESS_KEY, token)
    sessionStorage.setItem(EXPIRES_KEY, exp.toString())
    logger.debug('access token persisted, expiresAt=', new Date(exp).toISOString())
  }

  function clearStorage() {
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(EXPIRES_KEY)
    sessionStorage.removeItem(USER_KEY)
    // 兼容历史版本：清除可能遗留的 localStorage
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('token_expires_at')
    localStorage.removeItem('user')
  }

  const startAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
    }
    refreshTimer = setInterval(async () => {
      if (isTokenExpiringSoon.value && accessToken.value) {
        try {
          await refreshAccessToken()
        } catch (error) {
          // refreshAccessToken 内部已 logout
        }
      }
    }, 2 * 60 * 1000)
  }

  const stopAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  const login = async (credentials) => {
    const response = await api.post('/auth/login/', credentials)
    persistAccessToken(response.data.access)
    // refresh token 已被后端写入 httpOnly cookie；body 中的副本仅留在内存兜底
    refreshToken.value = response.data.refresh || ''
    user.value = response.data.user
    sessionStorage.setItem(USER_KEY, JSON.stringify(user.value))
    startAutoRefresh()
    return response.data
  }

  const register = async (userData) => {
    const response = await api.post('/auth/register/', userData)
    return response.data
  }

  let isLoggingOut = false

  const logout = async () => {
    if (isLoggingOut) {
      return
    }
    isLoggingOut = true
    stopAutoRefresh()

    try {
      if (!isTokenExpired.value) {
        try {
          // 不再传 refresh body：后端会从 httpOnly cookie 中取并撤销
          await api.post('/auth/logout/', {})
        } catch (apiError) {
          // logout API 失败不影响本地清理
        }
      }
    } finally {
      accessToken.value = ''
      refreshToken.value = ''
      user.value = null
      tokenExpiresAt.value = 0
      clearStorage()
      isLoggingOut = false
      await navigateToLogin()
    }
  }

  const refreshAccessToken = async () => {
    try {
      // refresh 请求依靠浏览器自动携带 httpOnly cookie；
      // 兼容期 body 中也带上以兜底旧后端。
      const body = refreshToken.value ? { refresh: refreshToken.value } : {}
      const response = await api.post('/auth/token/refresh/', body)
      persistAccessToken(response.data.access)
      if (response.data.refresh) {
        refreshToken.value = response.data.refresh
      }
      return response.data.access
    } catch (error) {
      await logout()
      throw error
    }
  }

  const fetchUser = async () => {
    try {
      const response = await api.get('/users/me/')
      user.value = response.data
      sessionStorage.setItem(USER_KEY, JSON.stringify(user.value))
    } catch (error) {
      await logout()
      throw error
    }
  }

  const fetchProfile = async () => {
    try {
      const response = await api.get('/auth/profile/')
      user.value = response.data
      sessionStorage.setItem(USER_KEY, JSON.stringify(user.value))
      return response.data
    } catch (error) {
      if (error.response?.status === 401) {
        await logout()
      }
      throw error
    }
  }

  const initAuth = async () => {
    if (!user.value) {
      const saved = sessionStorage.getItem(USER_KEY)
      if (saved) {
        try {
          user.value = JSON.parse(saved)
        } catch (e) {
          // 损坏缓存，忽略
        }
      }
    }

    if (accessToken.value) {
      if (isTokenExpired.value) {
        try {
          await refreshAccessToken()
        } catch (error) {
          return
        }
      }

      if (!user.value) {
        try {
          await fetchProfile()
        } catch (error) {
          await logout()
        }
      }

      startAutoRefresh()
    }
  }

  return {
    user,
    accessToken,
    refreshToken,
    tokenExpiresAt,
    isAuthenticated,
    isTokenExpiringSoon,
    isTokenExpired,
    login,
    register,
    logout,
    refreshAccessToken,
    fetchUser,
    fetchProfile,
    initAuth,
    startAutoRefresh,
    stopAutoRefresh,
  }
})
