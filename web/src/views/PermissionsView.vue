<script setup lang="ts">
// What managers and cashiers may do. The admin always has everything (and alone manages users and settings).
import { RotateCcw, Save, ShieldCheck } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Permission, PermissionsInfo } from '@/api/types'
import { t } from '@/lib/i18n'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const info = ref<PermissionsInfo | null>(null)
const manager = ref<Set<Permission>>(new Set())
const cashier = ref<Set<Permission>>(new Set())
const busy = ref(false)

const ROLES = [
  { key: 'manager', label: 'Manager', set: manager },
  { key: 'cashier', label: 'Cashier', set: cashier },
] as const

const changed = computed(() => {
  if (!info.value) return false
  const same = (a: Set<Permission>, b: Permission[]) => a.size === b.length && b.every((p) => a.has(p))
  return !same(manager.value, info.value.roles.manager) || !same(cashier.value, info.value.roles.cashier)
})

function reset() {
  if (!info.value) return
  manager.value = new Set(info.value.roles.manager)
  cashier.value = new Set(info.value.roles.cashier)
}

function toggle(role: (typeof ROLES)[number], perm: Permission) {
  const next = new Set(role.set.value)
  if (next.has(perm)) next.delete(perm)
  else next.add(perm)
  role.set.value = next
}

async function load() {
  try {
    info.value = await api.get<PermissionsInfo>('/permissions')
    reset()
  } catch (e) {
    ui.error(e)
  }
}

async function save() {
  busy.value = true
  try {
    info.value = await api.put<PermissionsInfo>('/permissions', { manager: [...manager.value], cashier: [...cashier.value] })
    reset()
    auth.refreshPermissions().catch(() => {})
    ui.toast(t('Permissions saved. Staff see the change the next time they open a page.'), 'success')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
    <p class="flex items-start gap-3 rounded-xl bg-primary-soft px-4 py-3 text-sm text-primary">
      <ShieldCheck :size="20" class="mt-0.5 shrink-0" />
      <span>{{ t('Choose what each role may do. Every role can sell, run its own shift and see its own sales. The admin always has everything, and alone manages users, store settings and the activity log.') }}</span>
    </p>

    <div v-if="info" class="card overflow-x-auto">
      <table class="table min-w-[560px]">
        <thead>
          <tr>
            <th>{{ t('Permission') }}</th>
            <th class="w-28 text-center">{{ t('Admin') }}</th>
            <th v-for="r in ROLES" :key="r.key" class="w-28 text-center">{{ t(r.label) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in info.permissions" :key="p.key">
            <td>{{ t(p.label) }}</td>
            <td class="text-center"><input type="checkbox" class="size-5 accent-primary" checked disabled :aria-label="t('Admin')" /></td>
            <td v-for="r in ROLES" :key="r.key" class="text-center">
              <input
                type="checkbox"
                class="size-5 cursor-pointer accent-primary"
                :checked="r.set.value.has(p.key)"
                :aria-label="`${t(r.label)}: ${t(p.label)}`"
                @change="toggle(r, p.key)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex flex-wrap justify-end gap-2">
      <button class="btn-outline" :disabled="!changed || busy" @click="reset"><RotateCcw :size="17" /> {{ t('Undo changes') }}</button>
      <button class="btn-primary px-6" :disabled="!changed || busy" @click="save"><Save :size="18" /> {{ t('Save permissions') }}</button>
    </div>
  </div>
</template>
