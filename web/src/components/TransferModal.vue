<script setup lang="ts">
// New stock transfer: from / to (main shop or a branch / warehouse), products by search or scan, quantities.
// Sending takes the stock off the source at once; the destination receives it later on the Transfers page.
import { ArrowRight, Plus, ScanLine, Trash2 } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Location, Product, Transfer } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { parseWhole, usd } from '@/lib/money'
import { beep, findByCode, useBarcodeScanner } from '@/lib/scanner'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const props = defineProps<{ locations: Location[] }>()
const emit = defineEmits<{ close: []; sent: [transfer: Transfer] }>()
const auth = useAuth()
const ui = useUi()

const products = ref<Product[]>([])
/** '' = main shop */
const from = ref<number | ''>('')
const to = ref<number | ''>(props.locations[0]?.id ?? '')
/** product id -> quantity at the source */
const sourceStock = ref(new Map<number, number>())
const lines = ref<{ product: Product; qty: string }[]>([])
const query = ref('')
const note = ref('')
const busy = ref(false)

const places = computed(() => [{ id: '' as const, name: `${auth.settings.store_name} (${t('main shop')})` }, ...props.locations.map((l) => ({ id: l.id, name: l.name }))])
const available = (p: Product) => (from.value === '' ? p.stock_qty : (sourceStock.value.get(p.id) ?? 0))
const matches = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  return products.value
    .filter((p) => p.is_active && p.track_stock && (p.name.toLowerCase().includes(q) || (p.barcode ?? '').includes(q) || (p.sku ?? '').toLowerCase().includes(q)))
    .slice(0, 8)
})
const totalQty = computed(() => lines.value.reduce((n, l) => n + (parseWhole(l.qty) ?? 0), 0))
const totalCost = computed(() => lines.value.reduce((n, l) => n + (parseWhole(l.qty) ?? 0) * l.product.cost, 0))

async function loadSource() {
  if (from.value === '') return (sourceStock.value = new Map())
  const rows = await api.get<{ product_id: number; qty: number }[]>(`/locations/${from.value}/stock`)
  sourceStock.value = new Map(rows.map((r) => [r.product_id, r.qty]))
}

function add(p: Product) {
  const line = lines.value.find((l) => l.product.id === p.id)
  if (line) line.qty = String((parseWhole(line.qty) ?? 0) + 1)
  else lines.value.push({ product: p, qty: '1' })
  query.value = ''
}

async function send() {
  if (from.value === to.value) return ui.toast(t('Choose two different places'), 'error')
  const items = lines.value.map((l) => ({ product_id: l.product.id, qty: parseWhole(l.qty) ?? 0 }))
  if (!items.length) return ui.toast(t('Add the products to send'), 'error')
  const bad = lines.value.find((l) => !parseWhole(l.qty) || parseWhole(l.qty)! > available(l.product))
  if (bad) return ui.toast(t('Check the quantity of {name} (available {n})', { name: bad.product.name, n: available(bad.product) }), 'error')
  busy.value = true
  try {
    const transfer = await api.post<Transfer>('/transfers', {
      from_location_id: from.value === '' ? null : from.value,
      to_location_id: to.value === '' ? null : to.value,
      items,
      note: note.value.trim() || null,
    })
    emit('sent', transfer)
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

useBarcodeScanner(
  (code) => {
    const p = findByCode(products.value, code)
    if (!p || !p.track_stock) {
      beep('error')
      return ui.toast(t('No product with barcode {code}', { code }), 'error')
    }
    beep('ok')
    add(p)
  },
  () => true,
)

watch(from, () => loadSource().catch(ui.error))
onMounted(async () => {
  try {
    products.value = await api.get<Product[]>('/products', { limit: 5000 })
  } catch (e) {
    ui.error(e)
  }
})
</script>

<template>
  <AppModal :title="t('New stock transfer')" width="max-w-3xl" @close="emit('close')">
    <div class="space-y-4">
      <div class="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <div>
          <label class="label">{{ t('From') }}</label>
          <select v-model="from" class="input">
            <option v-for="p in places" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <ArrowRight :size="20" class="mb-3 hidden text-muted sm:block" />
        <div>
          <label class="label">{{ t('To') }}</label>
          <select v-model="to" class="input">
            <option v-for="p in places" :key="p.id" :value="p.id" :disabled="p.id === from">{{ p.name }}</option>
          </select>
        </div>
      </div>

      <div class="relative">
        <label class="label">{{ t('Add products') }}</label>
        <input v-model="query" class="input" :placeholder="t('Search name, SKU or barcode')" @keydown.enter.prevent="matches[0] && add(matches[0])" />
        <p class="mt-1 flex items-center gap-1.5 text-xs text-muted"><ScanLine :size="14" /> {{ t('Or scan each product: every scan adds one.') }}</p>
        <div v-if="matches.length" class="absolute inset-x-0 top-[4.6rem] z-10 overflow-hidden rounded-xl border border-line bg-white shadow-lg">
          <button v-for="p in matches" :key="p.id" type="button" class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-page" @click="add(p)">
            <span class="truncate font-medium">{{ p.name }}</span>
            <span class="shrink-0 text-sm text-muted">{{ t('available {n}', { n: available(p) }) }} <Plus :size="14" class="inline" /></span>
          </button>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-line">
        <table class="table min-w-[520px]">
          <thead>
            <tr><th>{{ t('Product') }}</th><th class="text-right">{{ t('Available') }}</th><th class="w-32 text-right">{{ t('Quantity') }}</th><th class="text-right">{{ t('Cost') }}</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="(l, i) in lines" :key="l.product.id">
              <td class="font-semibold">{{ l.product.name }}</td>
              <td :class="['text-right', (parseWhole(l.qty) ?? 0) > available(l.product) ? 'font-bold text-price' : 'text-muted']">{{ available(l.product) }}</td>
              <td class="text-right"><input v-model="l.qty" class="input py-1.5 text-right" inputmode="numeric" /></td>
              <td class="text-right text-muted">{{ usd((parseWhole(l.qty) ?? 0) * l.product.cost) }}</td>
              <td class="text-right"><button class="btn-ghost p-1.5" :title="t('Remove')" @click="lines.splice(i, 1)"><Trash2 :size="16" /></button></td>
            </tr>
            <tr v-if="!lines.length"><td colspan="5" class="py-6 text-center text-muted">{{ t('No products yet') }}</td></tr>
          </tbody>
          <tfoot v-if="lines.length">
            <tr class="font-bold"><td>{{ t('Total') }}</td><td /><td class="text-right">{{ totalQty }}</td><td class="text-right">{{ usd(totalCost) }}</td><td /></tr>
          </tfoot>
        </table>
      </div>

      <div>
        <label class="label">{{ t('Note (driver, reason...)') }}</label>
        <input v-model="note" class="input" maxlength="200" />
      </div>
    </div>
    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Cancel') }}</button>
      <button class="btn-primary" :disabled="busy || !lines.length" @click="send">{{ t('Send {n} item(s)', { n: totalQty }) }}</button>
    </template>
  </AppModal>
</template>
