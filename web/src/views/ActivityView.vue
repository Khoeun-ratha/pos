<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { AuditEntry } from '@/api/types'
import { dateTime } from '@/lib/money'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const ui = useUi()
const entries = ref<AuditEntry[]>([])
const action = ref('')
const actions = ['login', 'refund', 'discount', 'manager_approval', 'shift_open', 'shift_close', 'cash_in', 'cash_out', 'product_update', 'stock_in', 'stock_adjust', 'stock_count', 'settings_update', 'user_create', 'user_update']

async function load() {
  try {
    entries.value = await api.get<AuditEntry[]>('/audit', { action: action.value, limit: 500 })
  } catch (e) {
    ui.error(e)
  }
}

watch(action, load)
onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
    <div class="card flex items-center gap-3 p-3">
      <span class="pl-2 text-sm text-muted">{{ t('Who did what and when: voids, refunds, discounts, price and stock changes, logins.') }}</span>
      <select v-model="action" class="input ml-auto w-auto">
        <option value="">{{ t('All actions') }}</option>
        <option v-for="a in actions" :key="a" :value="a">{{ a.replace('_', ' ') }}</option>
      </select>
    </div>
    <div class="card overflow-x-auto">
      <table class="table min-w-[640px]">
        <thead>
          <tr><th>{{ t('When') }}</th><th>{{ t('User') }}</th><th>{{ t('Action') }}</th><th>{{ t('Detail') }}</th></tr>
        </thead>
        <tbody>
          <tr v-if="!entries.length"><td colspan="4" class="py-10 text-center text-muted">{{ t('Nothing recorded yet') }}</td></tr>
          <tr v-for="e in entries" :key="e.id">
            <td class="whitespace-nowrap text-muted">{{ dateTime(e.created_at) }}</td>
            <td class="font-semibold">{{ e.username ?? '—' }}</td>
            <td><span class="pill bg-page text-muted">{{ e.action.replace('_', ' ') }}</span></td>
            <td>{{ e.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
