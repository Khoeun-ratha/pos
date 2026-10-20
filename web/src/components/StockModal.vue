<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { Location, Product, Supplier, WriteOffReason } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { parseHundredths, parseWhole, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'

/** Receive goods (quantity, price paid, supplier) or write off damaged / expired / lost stock, in the main shop
 *  or at a branch / warehouse (`location`; `onHand` is the quantity there). */
const props = defineProps<{ product: Product; mode: 'receive' | 'write_off'; suppliers: Supplier[]; location?: Location | null; onHand?: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const ui = useUi()

const qty = ref('')
const cost = ref(props.mode === 'receive' ? (props.product.cost / 100).toFixed(2) : '')
const supplierId = ref<number | ''>('')
const note = ref('')
const reason = ref<WriteOffReason>('damaged')
const busy = ref(false)

const reasons: { value: WriteOffReason; label: string }[] = [
  { value: 'damaged', label: 'Damaged' },
  { value: 'expired', label: 'Expired' },
  { value: 'lost', label: 'Lost' },
  { value: 'own_use', label: 'Own use' },
]
const activeSuppliers = computed(() => props.suppliers.filter((s) => s.is_active))
const have = computed(() => props.onHand ?? props.product.stock_qty)
const at = computed(() => (props.location ? ` · ${props.location.name}` : ''))
const amount = computed(() => parseWhole(qty.value))
const unitCost = computed(() => (cost.value.trim() ? parseHundredths(cost.value) : null))
/** What the product's average cost becomes after this delivery (same formula as the service). */
const newCost = computed(() => {
  const q = amount.value
  const c = unitCost.value
  if (!q || c === null || props.location) return null // with other places the service averages over all of them
  const onHand = Math.max(props.product.stock_qty, 0)
  return Math.round((onHand * props.product.cost + q * c) / (onHand + q))
})

async function save() {
  const q = amount.value
  if (!q) return ui.toast(t('Enter a quantity'), 'error')
  if (props.mode === 'write_off' && q > have.value) return ui.toast(t('Only {n} in stock', { n: Math.max(have.value, 0) }), 'error')
  if (props.mode === 'receive' && cost.value.trim() && unitCost.value === null) return ui.toast(t('Check the cost price'), 'error')
  busy.value = true
  try {
    if (props.mode === 'receive') {
      await api.post('/inventory/stock-in', {
        product_id: props.product.id,
        qty: q,
        unit_cost: unitCost.value,
        supplier_id: supplierId.value === '' ? null : supplierId.value,
        note: note.value.trim() || null,
        location_id: props.location?.id ?? null,
      })
      ui.toast(t('Received {n} × {name}', { n: q, name: props.product.name }), 'success')
    } else {
      await api.post('/inventory/write-off', {
        product_id: props.product.id,
        qty: q,
        reason: reason.value,
        note: note.value.trim() || null,
        location_id: props.location?.id ?? null,
      })
      ui.toast(t('Wrote off {n} × {name}', { n: q, name: props.product.name }), 'success')
    }
    emit('saved')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="(mode === 'receive' ? t('Receive stock: {name}', { name: product.name }) : t('Write off stock: {name}', { name: product.name })) + at" @close="emit('close')">
    <form id="stock-form" class="space-y-4" @submit.prevent="save">
      <p class="text-sm text-muted">{{ t('In stock now: {n}', { n: have }) }} · {{ t('Cost') }} {{ usd(product.cost) }}</p>

      <div v-if="mode === 'write_off'">
        <label class="label">{{ t('Reason') }}</label>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button
            v-for="r in reasons"
            :key="r.value"
            type="button"
            :class="['rounded-xl border px-3 py-2.5 font-semibold transition', reason === r.value ? 'border-primary bg-primary-soft text-primary' : 'border-line hover:bg-page']"
            @click="reason = r.value"
          >
            {{ t(r.label) }}
          </button>
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="label">{{ mode === 'receive' ? t('Quantity received') : t('Quantity') }}</label>
          <input v-model="qty" class="input" inputmode="numeric" autofocus />
        </div>
        <div v-if="mode === 'receive'">
          <label class="label">{{ t('Cost price per unit ($)') }}</label>
          <input v-model="cost" class="input" inputmode="decimal" :placeholder="t('Leave empty to keep the cost')" />
        </div>
      </div>

      <p v-if="mode === 'receive' && newCost !== null && newCost !== product.cost" class="rounded-xl bg-primary-soft px-3 py-2 text-sm text-primary">
        {{ t('Average cost changes from {old} to {new}', { old: usd(product.cost), new: usd(newCost) }) }}
      </p>
      <p v-if="mode === 'write_off' && amount" class="rounded-xl bg-rose-50 px-3 py-2 text-sm text-price">
        {{ t('Loss at cost: {amount}', { amount: usd(amount * product.cost) }) }}
      </p>

      <div v-if="mode === 'receive'">
        <label class="label">{{ t('Supplier') }}</label>
        <select v-model="supplierId" class="input">
          <option value="">{{ t('No supplier') }}</option>
          <option v-for="s in activeSuppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div>
        <label class="label">{{ mode === 'receive' ? t('Invoice no. / note') : t('Note') }}</label>
        <input v-model="note" class="input" maxlength="150" />
      </div>
    </form>
    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Cancel') }}</button>
      <button form="stock-form" :class="mode === 'receive' ? 'btn-primary' : 'btn-danger'" :disabled="busy">
        {{ mode === 'receive' ? t('Receive') : t('Write off') }}
      </button>
    </template>
  </AppModal>
</template>
