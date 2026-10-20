<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { useUi } from '@/stores/ui'

const ui = useUi()
const value = ref('')
const input = ref<HTMLInputElement>()

watch(
  () => ui.dialog,
  async (dialog) => {
    value.value = dialog?.initial ?? ''
    await nextTick()
    input.value?.focus()
    input.value?.select()
  },
)

function ok() {
  if (!ui.dialog) return
  ui.close(ui.dialog.kind === 'confirm' ? 'yes' : value.value)
}
</script>

<template>
  <AppModal v-if="ui.dialog" :title="t(ui.dialog.title)" width="max-w-md" @close="ui.close(null)">
    <form id="dialog-form" @submit.prevent="ok">
      <p v-if="ui.dialog.message" class="whitespace-pre-line text-muted">{{ t(ui.dialog.message) }}</p>
      <template v-if="ui.dialog.kind === 'prompt'">
        <label v-if="ui.dialog.label" class="label" for="dialog-input">{{ t(ui.dialog.label) }}</label>
        <input
          id="dialog-input"
          ref="input"
          v-model="value"
          class="input text-lg"
          :type="ui.dialog.password ? 'password' : 'text'"
          :inputmode="ui.dialog.inputmode ?? 'text'"
          :placeholder="ui.dialog.placeholder && t(ui.dialog.placeholder)"
          autocomplete="off"
        />
      </template>
    </form>
    <template #footer>
      <button class="btn-outline" type="button" @click="ui.close(null)">{{ t('Cancel') }}</button>
      <button :class="ui.dialog.danger ? 'btn bg-price text-white hover:bg-rose-700' : 'btn-primary'" type="submit" form="dialog-form">
        {{ t(ui.dialog.confirmText ?? 'OK') }}
      </button>
    </template>
  </AppModal>
</template>
