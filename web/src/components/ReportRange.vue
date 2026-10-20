<script setup lang="ts">
// Period picker on top of every report: quick choices, from / to, and room for the page's download button.
import { computed } from 'vue'

import { t } from '@/lib/i18n'
import { presets, reportFrom, reportTo, today } from '@/lib/reportRange'

const emit = defineEmits<{ load: [] }>()
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
    <button class="btn-primary" @click="emit('load')">{{ t('Show') }}</button>
    <div class="ml-auto flex flex-wrap gap-2"><slot /></div>
  </div>
</template>
