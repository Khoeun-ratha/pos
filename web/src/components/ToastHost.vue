<script setup lang="ts">
import { CircleAlert, CircleCheck, Info } from 'lucide-vue-next'

import { t } from '@/lib/i18n'
import { useUi } from '@/stores/ui'

const ui = useUi()
const icons = { info: Info, error: CircleAlert, success: CircleCheck }
const colors = { info: 'text-primary', error: 'text-price', success: 'text-ok' }
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
    <TransitionGroup name="toast">
      <div
        v-for="toast in ui.toasts"
        :key="toast.id"
        class="pointer-events-auto flex max-w-md items-start gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-lg"
        role="status"
      >
        <component :is="icons[toast.kind]" :size="20" :class="['mt-0.5 shrink-0', colors[toast.kind]]" />
        <p class="whitespace-pre-line">{{ toast.text.split('\n').map((line) => t(line)).join('\n') }}</p>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
