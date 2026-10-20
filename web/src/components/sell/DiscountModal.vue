<script setup lang="ts">
import { ref } from 'vue'

import type { DiscountType } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { parseHundredths, toDollars } from '@/lib/money'

const props = defineProps<{ title: string; type: DiscountType | null; value: number }>()
const emit = defineEmits<{ close: []; apply: [type: DiscountType | null, value: number] }>()

const kind = ref<DiscountType>(props.type ?? 'percent')
const text = ref(props.type ? toDollars(props.value) : '')

function apply() {
  const value = parseHundredths(text.value)
  if (value) emit('apply', kind.value, value) // 12.5% -> 1250 basis points; $1.50 -> 150 cents
}
</script>

<template>
  <AppModal :title="t(title)" width="max-w-sm" @close="emit('close')">
    <form id="discount-form" @submit.prevent="apply">
      <div class="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-page p-1">
        <button type="button" :class="['rounded-lg py-2 font-semibold', kind === 'percent' ? 'bg-white shadow-sm' : 'text-muted']" @click="kind = 'percent'">{{ t('Percent %') }}</button>
        <button type="button" :class="['rounded-lg py-2 font-semibold', kind === 'amount' ? 'bg-white shadow-sm' : 'text-muted']" @click="kind = 'amount'">{{ t('Amount $') }}</button>
      </div>
      <input v-model="text" class="input text-lg" inputmode="decimal" :placeholder="kind === 'percent' ? t('e.g. 10') : t('e.g. 1.50')" autofocus />
    </form>
    <template #footer>
      <button v-if="type" class="btn-danger mr-auto" @click="emit('apply', null, 0)">{{ t('Remove') }}</button>
      <button class="btn-outline" @click="emit('close')">{{ t('Cancel') }}</button>
      <button class="btn-primary" type="submit" form="discount-form">{{ t('Apply') }}</button>
    </template>
  </AppModal>
</template>
