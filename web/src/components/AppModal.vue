<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { t } from '@/lib/i18n'

const props = withDefaults(defineProps<{ title?: string; width?: string; closable?: boolean }>(), { width: 'max-w-lg', closable: true })
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.closable) emit('close')
}
const panel = ref<HTMLElement>()
onMounted(async () => {
  window.addEventListener('keydown', onKey)
  // the browser honours `autofocus` only once per page load, so a window opened later puts the cursor there itself
  await nextTick()
  const field = panel.value?.querySelector<HTMLInputElement>('[autofocus]')
  field?.focus()
  field?.select?.()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div data-modal class="fixed inset-0 z-40 flex items-end justify-center bg-slate-900/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" @mousedown.self="closable && emit('close')">
      <div ref="panel" :class="['flex max-h-[94vh] w-full flex-col rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl', width]">
        <div v-if="title" class="flex items-center gap-3 border-b border-line px-5 py-4">
          <h2 class="flex-1 text-lg font-bold">{{ title }}</h2>
          <button v-if="closable" class="btn-ghost -mr-2 p-2" :aria-label="t('Close')" @click="emit('close')"><X :size="20" /></button>
        </div>
        <div class="flex-1 overflow-y-auto p-5"><slot /></div>
        <div v-if="$slots.footer" class="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4"><slot name="footer" /></div>
      </div>
    </div>
  </Teleport>
</template>
