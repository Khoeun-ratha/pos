import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { ShiftReport } from '@/api/types'

/** The logged-in user's open shift (cash drawer), shown in the top bar. */
export const useShift = defineStore('shift', () => {
  const current = ref<ShiftReport | null>(null)
  const loaded = ref(false)

  async function refresh() {
    try {
      current.value = await api.get<ShiftReport | null>('/shifts/current')
    } finally {
      loaded.value = true
    }
  }

  return { current, loaded, refresh }
})
