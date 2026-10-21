<script setup lang="ts">
// Store settings > Registers: the shop's tills / counters, each with its own cash drawer. A shift opens on one.
// Each stands in the main shop or a branch, and sells from that outlet's stock.
import { MonitorSmartphone, Pencil, Plus, RotateCcw, Archive } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Location, Register } from '@/api/types'
import { t } from '@/lib/i18n'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const registers = ref<Register[]>([])
const name = ref('')
/** Branches that sell (open, kind branch); a register stands in one of these or in the main shop ('') */
const branches = ref<Location[]>([])
const outlet = ref<number | ''>('')
const inUse = computed(() => registers.value.filter((r) => r.is_active))
const retired = computed(() => registers.value.filter((r) => !r.is_active))

async function load() {
  registers.value = await api.get<Register[]>('/registers')
}

async function loadBranches() {
  try {
    branches.value = (await api.get<Location[]>('/locations')).filter((l) => l.kind === 'branch' && l.is_active)
  } catch {
    branches.value = [] // no stock permission: everything stays in the main shop
  }
}

async function run(action: () => Promise<unknown>, done?: string) {
  try {
    await action()
    if (done) ui.toast(done, 'success')
    await load()
  } catch (e) {
    ui.error(e)
  }
}

function add() {
  if (!name.value.trim()) return ui.toast(t('Type a name, e.g. Counter 2'), 'error')
  run(async () => {
    await api.post('/registers', { name: name.value.trim(), location_id: outlet.value === '' ? null : outlet.value })
    name.value = ''
  }, t('Register added'))
}

async function rename(r: Register) {
  const answer = await ui.prompt({ title: 'Rename register', label: 'Name', initial: r.name, confirmText: 'Save' })
  if (answer?.trim() && answer.trim() !== r.name) run(() => api.patch(`/registers/${r.id}`, { name: answer.trim() }))
}

async function retire(r: Register) {
  if (!(await ui.confirm(t('Retire register'), t('{name} will no longer be offered when opening a shift. Its past shifts stay in the reports.', { name: r.name }), t('Retire'), true))) return
  run(() => api.patch(`/registers/${r.id}`, { is_active: false }))
}

const useAgain = (r: Register) => run(() => api.patch(`/registers/${r.id}`, { is_active: true }))

function move(r: Register, to: string) {
  const location_id = to === '' ? null : Number(to)
  if (location_id !== r.location_id) run(() => api.patch(`/registers/${r.id}`, { location_id }), t('Register moved'))
}

onMounted(() => {
  load().catch(ui.error)
  if (auth.isAdmin) loadBranches()
})
</script>

<template>
  <div class="card space-y-3 p-5">
    <div>
      <h2 class="font-bold">{{ t('Registers') }}</h2>
      <p class="text-sm text-muted">{{ t('Each till or counter with its own cash drawer. A shift opens on one register, and only one shift at a time.') }}</p>
    </div>

    <ul class="divide-y divide-line rounded-xl border border-line">
      <li v-for="r in [...inUse, ...retired]" :key="r.id" :class="['flex items-center gap-3 px-4 py-3', !r.is_active && 'opacity-60']">
        <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><MonitorSmartphone :size="18" /></div>
        <div class="min-w-0 flex-1">
          <p class="truncate font-semibold">{{ r.name }}</p>
          <p class="truncate text-xs text-muted">{{ r.location_name ?? auth.settings.store_name }}</p>
          <p class="text-sm">
            <span v-if="!r.is_active" class="text-muted">{{ t('Retired') }}</span>
            <span v-else-if="r.open_by" class="text-ok">{{ t('Open · {name}', { name: r.open_by }) }}</span>
            <span v-else class="text-muted">{{ t('Free') }}</span>
          </p>
        </div>
        <template v-if="auth.isAdmin">
          <select
            v-if="branches.length && r.is_active"
            class="input w-auto max-w-36 py-1.5 text-sm"
            :value="r.location_id ?? ''"
            :disabled="!!r.open_by"
            :title="r.open_by ? t('Close its shift to move it') : t('Where it stands')"
            @change="move(r, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ auth.settings.store_name }}</option>
            <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
          </select>
          <button class="btn-ghost p-2" :title="t('Rename')" @click="rename(r)"><Pencil :size="16" /></button>
          <button v-if="r.is_active" class="btn-ghost p-2 text-price" :title="t('Retire')" :disabled="!!r.open_by || inUse.length <= 1" @click="retire(r)"><Archive :size="16" /></button>
          <button v-else class="btn-ghost p-2" :title="t('Use again')" @click="useAgain(r)"><RotateCcw :size="16" /></button>
        </template>
      </li>
    </ul>

    <form v-if="auth.isAdmin" class="flex flex-wrap gap-2 sm:flex-nowrap" @submit.prevent="add">
      <input v-model="name" class="input min-w-0 flex-1" maxlength="50" :placeholder="t('New register, e.g. Counter 2')" />
      <select v-if="branches.length" v-model="outlet" class="input w-auto max-w-44" :aria-label="t('Where it stands')">
        <option value="">{{ auth.settings.store_name }}</option>
        <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
      </select>
      <button class="btn-outline shrink-0"><Plus :size="17" /> {{ t('Add') }}</button>
    </form>
  </div>
</template>
