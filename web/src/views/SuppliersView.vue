<script setup lang="ts">
import { Pencil, Plus, Search } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { StockMovement, Supplier } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { dateTime, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'

const ui = useUi()
const query = ref('')
const suppliers = ref<Supplier[]>([])
const editing = ref<{ id: number | null; name: string; phone: string; note: string; is_active: boolean } | null>(null)
const deliveriesOf = ref<Supplier | null>(null)
const deliveries = ref<StockMovement[]>([])

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return suppliers.value.filter((s) => !q || s.name.toLowerCase().includes(q) || (s.phone ?? '').includes(q))
})
const deliveredTotal = computed(() => deliveries.value.reduce((sum, m) => sum + m.change * (m.unit_cost ?? 0), 0))

async function load() {
  try {
    suppliers.value = await api.get<Supplier[]>('/suppliers')
  } catch (e) {
    ui.error(e)
  }
}

async function save() {
  const s = editing.value
  if (!s?.name.trim()) return ui.toast(t('Enter a name'), 'error')
  const body = { name: s.name.trim(), phone: s.phone.trim() || null, note: s.note.trim() || null, is_active: s.is_active }
  try {
    if (s.id) await api.put(`/suppliers/${s.id}`, body)
    else await api.post('/suppliers', body)
    editing.value = null
    ui.toast(t('Supplier saved'), 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

async function showDeliveries(s: Supplier) {
  deliveriesOf.value = s
  deliveries.value = []
  try {
    deliveries.value = await api.get<StockMovement[]>('/inventory/movements', { supplier_id: s.id, limit: 200 })
  } catch (e) {
    ui.error(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
    <div class="card flex flex-wrap gap-2 p-3">
      <div class="relative min-w-56 flex-1">
        <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-10" :placeholder="t('Search name or phone')" />
      </div>
      <button class="btn-primary" @click="editing = { id: null, name: '', phone: '', note: '', is_active: true }"><Plus :size="18" /> {{ t('New supplier') }}</button>
    </div>
    <p class="px-1 text-sm text-muted">{{ t('Choose a supplier when you receive stock on the Products page.') }}</p>

    <div class="card overflow-x-auto">
      <table class="table min-w-[560px]">
        <thead>
          <tr><th>{{ t('Supplier') }}</th><th>{{ t('Phone') }}</th><th>{{ t('Note') }}</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="!visible.length"><td colspan="4" class="py-10 text-center text-muted">{{ t('No suppliers yet') }}</td></tr>
          <tr v-for="s in visible" :key="s.id" :class="['cursor-pointer hover:bg-page', !s.is_active && 'opacity-50']" @click="showDeliveries(s)">
            <td>
              <p class="font-semibold">{{ s.name }}</p>
              <p v-if="!s.is_active" class="text-xs text-muted">{{ t('inactive') }}</p>
            </td>
            <td class="text-muted">{{ s.phone ?? '—' }}</td>
            <td class="text-muted">{{ s.note ?? '' }}</td>
            <td class="text-right">
              <button class="btn-ghost p-2" :title="t('Edit')" @click.stop="editing = { id: s.id, name: s.name, phone: s.phone ?? '', note: s.note ?? '', is_active: s.is_active }">
                <Pencil :size="17" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="editing" :title="editing.id ? t('Edit supplier') : t('New supplier')" width="max-w-md" @close="editing = null">
      <form id="supplier-form" class="space-y-3" @submit.prevent="save">
        <div><label class="label">{{ t('Name') }}</label><input v-model="editing.name" class="input" maxlength="100" autofocus /></div>
        <div><label class="label">{{ t('Phone') }}</label><input v-model="editing.phone" class="input" inputmode="tel" maxlength="30" /></div>
        <div><label class="label">{{ t('Note') }}</label><input v-model="editing.note" class="input" maxlength="200" :placeholder="t('e.g. delivers on Monday')" /></div>
        <label v-if="editing.id" class="flex items-center gap-2"><input v-model="editing.is_active" type="checkbox" class="size-4 accent-primary" /> {{ t('Active') }}</label>
      </form>
      <template #footer>
        <button class="btn-outline" @click="editing = null">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="supplier-form">{{ t('Save') }}</button>
      </template>
    </AppModal>

    <AppModal v-if="deliveriesOf" :title="t('Deliveries from {name}', { name: deliveriesOf.name })" width="max-w-2xl" @close="deliveriesOf = null">
      <p v-if="!deliveries.length" class="py-6 text-center text-muted">{{ t('No deliveries yet') }}</p>
      <div v-else class="overflow-x-auto">
        <table class="table min-w-[520px]">
          <thead>
            <tr><th>{{ t('When') }}</th><th>{{ t('Product') }}</th><th class="text-right">{{ t('Qty') }}</th><th class="text-right">{{ t('Unit cost') }}</th><th>{{ t('Note') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in deliveries" :key="m.id">
              <td class="whitespace-nowrap text-muted">{{ dateTime(m.created_at) }}</td>
              <td class="font-semibold">{{ m.product_name }}</td>
              <td class="text-right">{{ m.change }}</td>
              <td class="text-right">{{ m.unit_cost === null ? '—' : usd(m.unit_cost) }}</td>
              <td class="text-muted">{{ m.note ?? '' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="mt-3 text-right font-bold">{{ t('Total at cost: {amount}', { amount: usd(deliveredTotal) }) }}</p>
      </div>
    </AppModal>
  </div>
</template>
