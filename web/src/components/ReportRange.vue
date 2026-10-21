<script setup lang="ts">
// Period picker on top of every report: quick choices, from / to, the outlet (when the shop has branches), and room
// for the page's download button.
import { MapPin } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Location } from '@/api/types'
import { t } from '@/lib/i18n'
import { presets, reportFrom, reportOutlet, reportTo, today } from '@/lib/reportRange'
import { useAuth } from '@/stores/auth'

const emit = defineEmits<{ load: [] }>()
const auth = useAuth()
/** Branches, for the outlet choice; staff of a branch see their branch only. */
const branches = ref<Location[]>([])
const myBranch = computed(() => auth.user?.location_name ?? null)

onMounted(async () => {
  if (myBranch.value) return
  try {
    branches.value = (await api.get<Location[]>('/locations')).filter((l) => l.kind === 'branch')
  } catch {
    branches.value = [] // no stock permission: the reports cover the whole business
  }
  // a branch since removed from the list: back to the whole business
  if (reportOutlet.value !== '' && reportOutlet.value !== 'main' && !branches.value.some((b) => String(b.id) === reportOutlet.value)) {
    reportOutlet.value = ''
  }
})
const choices = computed(presets)
const picked = computed(() => choices.value.find(([, f, to]) => f === reportFrom.value && to === reportTo.value)?.[0])

function choose(from: string, to: string) {
  reportFrom.value = from
  reportTo.value = to
  emit('load')
}
</script>

<template>
  <div class="card flex flex-wrap items-end gap-3 p-4">
    <div class="flex flex-wrap gap-1 rounded-xl bg-page p-1">
      <button
        v-for="[label, f, to] in choices"
        :key="label"
        :class="['rounded-lg px-3 py-1.5 font-semibold', picked === label ? 'bg-white text-primary shadow-sm' : 'hover:bg-white']"
        @click="choose(f, to)"
      >
        {{ t(label) }}
      </button>
    </div>
    <div>
      <label class="label">{{ t('From') }}</label>
      <input v-model="reportFrom" type="date" class="input py-2" :max="reportTo" />
    </div>
    <div>
      <label class="label">{{ t('To') }}</label>
      <input v-model="reportTo" type="date" class="input py-2" :min="reportFrom" :max="today()" />
    </div>
    <div v-if="myBranch">
      <label class="label">{{ t('Outlet') }}</label>
      <p class="flex items-center gap-1.5 py-2 font-semibold"><MapPin :size="16" class="text-muted" /> {{ myBranch }}</p>
    </div>
    <div v-else-if="branches.length">
      <label class="label" for="report-outlet">{{ t('Outlet') }}</label>
      <select id="report-outlet" v-model="reportOutlet" class="input py-2" @change="emit('load')">
        <option value="">{{ t('All outlets') }}</option>
        <option value="main">{{ auth.settings.store_name }}</option>
        <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
      </select>
    </div>
    <button class="btn-primary" @click="emit('load')">{{ t('Show') }}</button>
    <div class="ml-auto flex flex-wrap gap-2"><slot /></div>
  </div>
</template>
