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
    // after the key press that opened the dialog is over: an Enter that opened it must not also submit it
    setTimeout(() => {
      input.value?.focus()
      input.value?.select()
    })
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
      <template v-if="ui.dialog.kind === 'prompt' && !ui.dialog.noInput">
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
      <div v-if="ui.dialog.choices" :class="ui.dialog.noInput ? '' : 'mt-3'">
        <label v-if="ui.dialog.choiceLabel" class="label" for="dialog-choice">{{ t(ui.dialog.choiceLabel) }}</label>
        <select id="dialog-choice" v-model="ui.choice" class="input">
          <option v-for="c in ui.dialog.choices" :key="c.value" :value="c.value">{{ t(c.label) }}</option>
        </select>
      </div>
    </form>
    <template #footer>
      <button class="btn-outline" type="button" @click="ui.close(null)">{{ t('Cancel') }}</button>
      <button :class="ui.dialog.danger ? 'btn bg-price text-white hover:bg-rose-700' : 'btn-primary'" type="submit" form="dialog-form">
        {{ t(ui.dialog.confirmText ?? 'OK') }}
      </button>
    </template>
  </AppModal>
</template>
