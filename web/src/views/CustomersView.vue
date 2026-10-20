<script setup lang="ts">
import { Pencil, Search, UserPlus } from 'lucide-vue-next'
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Customer, SaleSummary } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { dateTime, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const ui = useUi()
const query = ref('')
const customers = ref<Customer[]>([])
const editing = ref<{ id: number | null; name: string; phone: string; email: string } | null>(null)
const historyOf = ref<Customer | null>(null)
const history = ref<SaleSummary[]>([])
let timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  try {
    customers.value = await api.get<Customer[]>('/customers', { q: query.value.trim(), limit: 500 })
  } catch (e) {
    ui.error(e)
  }
}

async function save() {
  const c = editing.value
  if (!c?.name.trim()) return ui.toast('Enter a name', 'error')
  const body = { name: c.name.trim(), phone: c.phone.trim() || null, email: c.email.trim() || null }
  try {
    if (c.id) await api.put(`/customers/${c.id}`, body)
    else await api.post('/customers', body)
    editing.value = null
    ui.toast('Customer saved', 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

async function showHistory(c: Customer) {
  historyOf.value = c
  history.value = []
  try {
    history.value = await api.get<SaleSummary[]>(`/customers/${c.id}/sales`)
  } catch (e) {
    ui.error(e)
  }
}

watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
    <div class="card flex flex-wrap gap-2 p-3">
      <div class="relative min-w-56 flex-1">
        <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-10" :placeholder="t('Search name or phone')" />
      </div>
      <button class="btn-primary" @click="editing = { id: null, name: '', phone: '', email: '' }"><UserPlus :size="18" /> {{ t('New customer') }}</button>
    </div>

    <div class="card overflow-x-auto">
      <table class="table min-w-[600px]">
        <thead>
          <tr><th>{{ t('Customer') }}</th><th>{{ t('Phone') }}</th><th class="text-right">{{ t('Points') }}</th><th>{{ t('Since') }}</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="!customers.length"><td colspan="5" class="py-10 text-center text-muted">{{ t('No customers found') }}</td></tr>
          <tr v-for="c in customers" :key="c.id" class="cursor-pointer hover:bg-page" @click="showHistory(c)">
            <td>
              <div class="flex items-center gap-3">
                <span class="flex size-9 items-center justify-center rounded-full bg-primary-soft font-bold text-primary">{{ c.name.charAt(0) }}</span>
                <span class="font-semibold">{{ c.name }}</span>
              </div>
            </td>
            <td class="text-muted">{{ c.phone ?? '—' }}</td>
            <td class="text-right"><span class="pill bg-primary-soft text-primary">{{ c.points }} pts</span></td>
            <td class="text-muted">{{ dateTime(c.created_at) }}</td>
            <td class="text-right">
              <button class="btn-ghost p-2" :title="t('Edit')" @click.stop="editing = { id: c.id, name: c.name, phone: c.phone ?? '', email: c.email ?? '' }">
                <Pencil :size="17" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="editing" :title="editing.id ? 'Edit customer' : 'New customer'" width="max-w-md" @close="editing = null">
      <form id="customer-form" class="space-y-3" @submit.prevent="save">
        <div><label class="label">{{ t('Name') }}</label><input v-model="editing.name" class="input" autofocus /></div>
        <div><label class="label">{{ t('Phone') }}</label><input v-model="editing.phone" class="input" inputmode="tel" /></div>
        <div><label class="label">{{ t('Email') }}</label><input v-model="editing.email" class="input" type="email" /></div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="editing = null">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="customer-form">{{ t('Save') }}</button>
      </template>
    </AppModal>

    <AppModal v-if="historyOf" :title="`${historyOf.name} · ${t('{n} points', { n: historyOf.points })}`" @close="historyOf = null">
      <p v-if="!history.length" class="py-6 text-center text-muted">{{ t('No purchases yet') }}</p>
      <ul class="divide-y divide-line">
        <li v-for="s in history" :key="s.id" class="flex justify-between py-2.5">
          <span>
            <span class="block font-semibold">{{ s.receipt_no }}</span>
            <span class="text-sm text-muted">{{ dateTime(s.created_at) }}</span>
          </span>
          <span class="font-bold">{{ usd(s.total) }}</span>
        </li>
      </ul>
    </AppModal>
  </div>
</template>
