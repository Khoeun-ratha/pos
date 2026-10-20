import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, setToken } from '@/api/client'
import type { Permission, PermissionsInfo, StoreSettings, TokenResponse, User } from '@/api/types'

const DEFAULT_SETTINGS: StoreSettings = {
  store_name: 'POS',
  store_address: '',
  store_phone: '',
  tax_rate_bp: 0,
  tax_inclusive: false,
  exchange_rate: 4100,
  receipt_footer: '',
  allow_negative_stock: true,
  loyalty_points_per_usd: 1,
  logo_url: '',
}

function stored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export const useAuth = defineStore('auth', () => {
  const user = ref<User | null>(stored('pos.user', null))
  const settings = ref<StoreSettings>(stored('pos.settings', DEFAULT_SETTINGS))
  /** null until loaded from the service; then the role's defaults are assumed. */
  const permissions = ref<Permission[] | null>(stored('pos.perms', null))

  const loggedIn = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const displayName = computed(() => user.value?.full_name || user.value?.username || '')

  /** Whether the logged-in user's role may do this (the service checks it too). */
  function can(perm: Permission) {
    if (user.value?.role === 'admin') return true
    if (permissions.value) return permissions.value.includes(perm)
    return user.value?.role === 'manager' // the defaults, until the service answers
  }

  async function login(username: string, secret: string, usePin: boolean) {
    const body = usePin ? { username, pin: secret } : { username, password: secret }
    const result = await api.post<TokenResponse>(usePin ? '/auth/pin-login' : '/auth/login', body)
    setToken(result.access_token)
    user.value = result.user
    localStorage.setItem('pos.user', JSON.stringify(result.user))
    await Promise.all([refreshSettings(), refreshPermissions()])
  }

  async function refreshPermissions() {
    permissions.value = (await api.get<PermissionsInfo>('/permissions')).mine
    localStorage.setItem('pos.perms', JSON.stringify(permissions.value))
  }

  async function refreshSettings() {
    settings.value = await api.get<StoreSettings>('/settings')
    localStorage.setItem('pos.settings', JSON.stringify(settings.value))
  }

  function logout() {
    setToken(null)
    user.value = null
    permissions.value = null
    localStorage.removeItem('pos.user')
    localStorage.removeItem('pos.perms')
  }

  return { user, settings, permissions, loggedIn, isAdmin, displayName, can, login, refreshSettings, refreshPermissions, logout }
})
