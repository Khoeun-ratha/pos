// Toasts and promise-based dialogs (prompt / confirm / manager PIN), shown by DialogHost.vue.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, ApiError } from '@/api/client'

export interface Toast {
  id: number
  text: string
  kind: 'info' | 'error' | 'success'
}

export interface PromptOptions {
  title: string
  label?: string
  message?: string
  initial?: string
  placeholder?: string
  inputmode?: 'text' | 'decimal' | 'numeric' | 'tel'
  password?: boolean
  confirmText?: string
  danger?: boolean
}

interface OpenDialog extends PromptOptions {
  kind: 'prompt' | 'confirm'
  resolve: (value: string | null) => void
}

let nextToast = 1

export const useUi = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const dialog = ref<OpenDialog | null>(null)

  function toast(text: string, kind: Toast['kind'] = 'info') {
    const id = nextToast++
    toasts.value.push({ id, text, kind })
    setTimeout(() => (toasts.value = toasts.value.filter((t) => t.id !== id)), kind === 'error' ? 6000 : 3500)
  }

  function error(e: unknown) {
    if (e instanceof ApiError && e.isUnauthorized) return // handled by the session-expired redirect
    toast(e instanceof Error ? e.message : String(e), 'error')
  }

  function prompt(options: PromptOptions): Promise<string | null> {
    return new Promise((resolve) => (dialog.value = { ...options, kind: 'prompt', resolve }))
  }

  async function confirm(title: string, message: string, confirmText = 'Yes', danger = false) {
    const answer = await new Promise<string | null>((resolve) => (dialog.value = { title, message, confirmText, danger, kind: 'confirm', resolve }))
    return answer !== null
  }

  function close(value: string | null) {
    const open = dialog.value
    dialog.value = null
    open?.resolve(value)
  }

  /** Asks for a manager PIN and checks it with the service. Returns the PIN, or null if cancelled / wrong. */
  async function managerPin(reason: string): Promise<string | null> {
    const pin = await prompt({ title: reason, label: 'Manager PIN', inputmode: 'numeric', password: true, confirmText: 'Approve' })
    if (!pin) return null
    try {
      await api.post('/auth/verify-manager-pin', { pin })
      return pin
    } catch (e) {
      error(e)
      return null
    }
  }

  return { toasts, dialog, toast, error, prompt, confirm, close, managerPin }
})
