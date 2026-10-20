<script setup lang="ts">
import { Copy, Printer } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Sale } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { khr, usd } from '@/lib/money'
import { printReceipt } from '@/lib/print'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const props = defineProps<{ sale: Sale; justSold?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const ui = useUi()
const auth = useAuth()
const text = ref('')
const autoPrint = ref(localStorage.getItem('pos.autoPrint') === 'yes')

function toggleAutoPrint() {
  autoPrint.value = !autoPrint.value
  localStorage.setItem('pos.autoPrint', autoPrint.value ? 'yes' : 'no')
}

async function copy() {
  await navigator.clipboard?.writeText(text.value)
  ui.toast('Receipt copied', 'success')
}

onMounted(async () => {
  try {
    text.value = await api.text(`/sales/${props.sale.id}/receipt`, { width: 42, reprint: !props.justSold })
    if (props.justSold && autoPrint.value) printReceipt(text.value, props.sale.receipt_no, auth.settings.logo_url)
  } catch (e) {
    ui.error(e)
  }
})
</script>

<template>
  <AppModal :title="justSold ? t('Sale complete') : t('Receipt {receipt}', { receipt: sale.receipt_no })" width="max-w-md" @close="emit('close')">
    <div v-if="justSold && sale.change_due > 0" class="mb-4 rounded-2xl bg-ok-soft p-5 text-center">
      <p class="text-sm font-semibold tracking-widest text-ok uppercase">{{ t('Change to give') }}</p>
      <p class="text-4xl font-extrabold text-ink">{{ usd(sale.change_due) }}</p>
      <p class="font-semibold text-ok">{{ khr(sale.change_due_khr) }}</p>
    </div>
    <pre class="overflow-x-auto rounded-xl border border-line bg-white p-4 font-mono text-[12.5px] leading-snug">{{ text || t('Loading...') }}</pre>
    <label v-if="justSold" class="mt-3 flex cursor-pointer items-center gap-2 text-sm text-muted">
      <input type="checkbox" :checked="autoPrint" class="size-4 accent-primary" @change="toggleAutoPrint" />
      {{ t('Print the receipt automatically after each sale') }}
    </label>
    <template #footer>
      <button class="btn-outline" :disabled="!text" @click="copy"><Copy :size="17" /> {{ t('Copy') }}</button>
      <button class="btn-outline" :disabled="!text" @click="printReceipt(text, sale.receipt_no, auth.settings.logo_url)"><Printer :size="17" /> {{ t('Print') }}</button>
      <button class="btn-primary min-w-32" @click="emit('close')">{{ justSold ? t('New sale') : t('Close') }}</button>
    </template>
  </AppModal>
</template>
