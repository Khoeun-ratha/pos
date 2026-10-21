<script setup lang="ts">
// Branches and warehouses (the main shop is the store itself and is not listed here). A branch sells from its own
// registers and stock; a warehouse only keeps stock.
import { Building2, Pencil, Plus, Store, Warehouse } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/client'
import type { Location, Register } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const locations = ref<Location[]>([])
const registers = ref<Register[]>([])
/** Registers in use per outlet ('main' = the main shop). */
const tills = computed(() => {
  const count = new Map<number | 'main', number>()
  for (const r of registers.value) if (r.is_active) count.set(r.location_id ?? 'main', (count.get(r.location_id ?? 'main') ?? 0) + 1)
  return count
})
const tillText = (n = 0) => (n === 1 ? t('1 register') : t('{n} registers', { n }))
const editing = ref<Location | 'new' | null>(null)
const form = reactive({ name: '', kind: 'warehouse' as Location['kind'], address: '', is_active: true })

async function load() {
  try {
    ;[locations.value, registers.value] = await Promise.all([api.get<Location[]>('/locations'), api.get<Register[]>('/registers')])
  } catch (e) {
    ui.error(e)
  }
}

function edit(l: Location | 'new') {
  Object.assign(form, l === 'new' ? { name: '', kind: 'warehouse', address: '', is_active: true } : { ...l, address: l.address ?? '' })
  editing.value = l
}

async function save() {
  if (!form.name.trim()) return ui.toast(t('Enter a name'), 'error')
  const body = { ...form, name: form.name.trim(), address: form.address.trim() || null }
  try {
    if (editing.value === 'new') await api.post('/locations', body)
    else if (editing.value) await api.patch(`/locations/${editing.value.id}`, body)
    editing.value = null
    ui.toast(t('Saved'), 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

/** "Stock" opens the Inventory page on this place. */
function localStorageSet(id: number) {
  try {
    localStorage.setItem('pos.inventory.place', String(id))
  } catch {
    // private window: Inventory opens on the main shop
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-sm text-muted">{{ t('A branch sells from its own registers and stock; a warehouse only keeps stock. Put registers in a branch in Store settings.') }}</p>
      <button class="btn-primary" @click="edit('new')"><Plus :size="18" /> {{ t('Add a branch or warehouse') }}</button>
    </div>

    <div class="card divide-y divide-line">
      <div class="flex items-center gap-3 p-4">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white"><Store :size="21" /></div>
        <div class="min-w-0 flex-1">
          <p class="font-semibold">{{ auth.settings.store_name }}</p>
          <p class="text-sm text-muted">{{ t('main shop') }} · {{ tillText(tills.get('main')) }}</p>
        </div>
      </div>
      <div v-for="l in locations" :key="l.id" :class="['flex items-center gap-3 p-4', !l.is_active && 'opacity-50']">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
          <component :is="l.kind === 'branch' ? Building2 : Warehouse" :size="21" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="font-semibold">{{ l.name }}</p>
          <p class="truncate text-sm text-muted">
            {{ t(l.kind) }}{{ l.kind === 'branch' ? ` · ${tillText(tills.get(l.id))}` : '' }}{{ l.address ? ` · ${l.address}` : '' }}{{ l.is_active ? '' : ` · ${t('closed')}` }}
          </p>
        </div>
        <RouterLink v-if="l.is_active" to="/inventory" class="btn-ghost px-3 py-2 text-sm" @click="localStorageSet(l.id)">{{ t('Stock') }}</RouterLink>
        <button class="btn-ghost p-2" :title="t('Edit')" @click="edit(l)"><Pencil :size="17" /></button>
      </div>
    </div>

    <AppModal v-if="editing" :title="editing === 'new' ? t('Add a branch or warehouse') : t('Edit {name}', { name: editing.name })" width="max-w-md" @close="editing = null">
      <form id="location-form" class="space-y-3" @submit.prevent="save">
        <div><label class="label">{{ t('Name') }}</label><input v-model="form.name" class="input" maxlength="100" autofocus /></div>
        <div>
          <label class="label">{{ t('Type') }}</label>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="k in ['warehouse', 'branch'] as const"
              :key="k"
              type="button"
              :class="['rounded-xl border px-3 py-2.5 font-semibold capitalize transition', form.kind === k ? 'border-primary bg-primary-soft text-primary' : 'border-line hover:bg-page']"
              @click="form.kind = k"
            >
              {{ t(k) }}
            </button>
          </div>
          <p class="mt-1 text-sm text-muted">{{ form.kind === 'branch' ? t('Sells: give it registers and staff.') : t('Keeps stock only: nothing is sold here.') }}</p>
        </div>
        <div><label class="label">{{ t('Address (optional)') }}</label><input v-model="form.address" class="input" maxlength="200" /></div>
        <label v-if="editing !== 'new'" class="flex items-center gap-2"><input v-model="form.is_active" type="checkbox" class="size-4 accent-primary" /> {{ t('Open (uncheck when it closes)') }}</label>
      </form>
      <template #footer>
        <button class="btn-outline" @click="editing = null">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="location-form">{{ t('Save') }}</button>
      </template>
    </AppModal>
  </div>
</template>
