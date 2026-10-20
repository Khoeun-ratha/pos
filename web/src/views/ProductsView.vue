<script setup lang="ts">
import { Barcode, ClipboardCheck, Download, History, PackageMinus, PackagePlus, Pencil, Plus, Search, Upload } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { Category, ImportResult, Product, StockMovement, Supplier } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import LabelModal from '@/components/LabelModal.vue'
import ProductArt from '@/components/ProductArt.vue'
import ProductForm from '@/components/ProductForm.vue'
import StockModal from '@/components/StockModal.vue'
import { saveBlob } from '@/lib/download'
import { t } from '@/lib/i18n'
import { dateTime, isoDate, parseWhole, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'

const ui = useUi()
const route = useRoute()
const router = useRouter()
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const suppliers = ref<Supplier[]>([])
const query = ref('')
const categoryId = ref<number | ''>('')
const showInactive = ref(false)
const editing = ref<Product | 'new' | null>(null)
const newBarcode = ref('')
/** Products whose barcode / QR labels are being printed. */
const labelsFor = ref<Product[] | null>(null)
const stockFor = ref<{ product: Product; mode: 'receive' | 'write_off' } | null>(null)
const historyOf = ref<Product | null>(null)
const movements = ref<StockMovement[]>([])
const fileInput = ref<HTMLInputElement>()

const KINDS: Record<string, string> = {
  sale: 'Sale',
  refund: 'Refund',
  stock_in: 'Received',
  adjustment: 'Adjustment',
  count: 'Stock count',
  write_off: 'Write-off',
}

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return products.value.filter(
    (p) =>
      (showInactive.value || p.is_active) &&
      (categoryId.value === '' || p.category_id === categoryId.value) &&
      (!q || p.name.toLowerCase().includes(q) || (p.barcode ?? '').includes(q) || (p.sku ?? '').toLowerCase().includes(q)),
  )
})
const lowCount = computed(() => products.value.filter((p) => p.is_active && p.track_stock && p.stock_qty <= p.low_stock_threshold).length)

async function load() {
  try {
    ;[products.value, categories.value, suppliers.value] = await Promise.all([
      api.get<Product[]>('/products', { include_inactive: true, limit: 5000 }),
      api.get<Category[]>('/categories'),
      api.get<Supplier[]>('/suppliers'),
    ])
  } catch (e) {
    ui.error(e)
  }
}

async function count(p: Product) {
  const text = await ui.prompt({
    title: t('Stock count: {name}', { name: p.name }),
    label: t('Quantity on the shelf (system says {n})', { n: p.stock_qty }),
    inputmode: 'numeric',
  })
  const qty = parseWhole(text)
  if (qty === null) return
  try {
    await api.post('/inventory/count', { product_id: p.id, counted_qty: qty })
    ui.toast(t('Stock updated'), 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

async function showHistory(p: Product) {
  historyOf.value = p
  movements.value = []
  try {
    movements.value = await api.get<StockMovement[]>('/inventory/movements', { product_id: p.id, limit: 100 })
  } catch (e) {
    ui.error(e)
  }
}

async function exportCsv() {
  try {
    saveBlob(await api.blob('/products/export'), `products-${isoDate(new Date())}.csv`)
  } catch (e) {
    ui.error(e)
  }
}

async function importCsv(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const result = await api.upload<ImportResult>('/products/import', file)
    const summary = t('Created {created}, updated {updated}.', { created: result.created, updated: result.updated })
    ui.toast(`${summary}${result.errors.length ? `\n${result.errors.slice(0, 5).join('\n')}` : ''}`, result.errors.length ? 'error' : 'success')
    load()
  } catch (e) {
    ui.error(e)
  } finally {
    fileInput.value!.value = ''
  }
}

function saved() {
  editing.value = null
  newBarcode.value = ''
  stockFor.value = null
  load()
}

onMounted(() => {
  load()
  // from the till: "unknown barcode, add it as a new product"
  if (typeof route.query.barcode === 'string') {
    newBarcode.value = route.query.barcode
    editing.value = 'new'
    router.replace({ query: {} })
  }
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
    <div class="card flex flex-wrap items-center gap-2 p-3">
      <div class="relative min-w-56 flex-1">
        <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-10" :placeholder="t('Search name, SKU or barcode')" />
      </div>
      <select v-model="categoryId" class="input w-auto">
        <option value="">{{ t('All categories') }}</option>
        <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <label class="flex items-center gap-2 px-2 text-sm"><input v-model="showInactive" type="checkbox" class="size-4 accent-primary" /> {{ t('Show inactive') }}</label>
      <button class="btn-outline" @click="fileInput?.click()"><Upload :size="17" /> {{ t('Import CSV') }}</button>
      <button class="btn-outline" @click="exportCsv"><Download :size="17" /> {{ t('Export CSV') }}</button>
      <button class="btn-outline" :disabled="!visible.length" :title="t('Barcode / QR labels for the products listed')" @click="labelsFor = visible.filter((p) => p.is_active)">
        <Barcode :size="17" /> {{ t('Print labels') }}
      </button>
      <button class="btn-primary" @click="editing = 'new'"><Plus :size="18" /> {{ t('New product') }}</button>
      <input ref="fileInput" type="file" accept=".csv" class="hidden" @change="importCsv" />
    </div>
    <p class="px-1 text-sm text-muted">{{ t('{n} product(s) · {low} low on stock', { n: visible.length, low: lowCount }) }}</p>

    <div class="card overflow-x-auto">
      <table class="table min-w-[900px]">
        <thead>
          <tr>
            <th>{{ t('Product') }}</th><th>{{ t('Category') }}</th><th>{{ t('Barcode') }}</th>
            <th class="text-right">{{ t('Price') }}</th><th class="text-right">{{ t('Cost') }}</th><th class="text-right">{{ t('Stock') }}</th>
            <th class="text-right">{{ t('Actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in visible" :key="p.id" :class="!p.is_active && 'opacity-50'">
            <td>
              <div class="flex items-center gap-3">
                <ProductArt :category="p.category_name" :image="p.image_url" :alt="p.name" :size="18" class="size-10 shrink-0 rounded-xl" />
                <div>
                  <p class="font-semibold">{{ p.name }}</p>
                  <p class="text-xs text-muted">{{ p.sku }}{{ p.is_active ? '' : ` · ${t('inactive')}` }}</p>
                </div>
              </div>
            </td>
            <td class="text-muted">{{ p.category_name ?? '—' }}</td>
            <td class="font-mono text-xs text-muted">{{ p.barcode ?? '—' }}</td>
            <td class="text-right font-semibold">{{ usd(p.price) }}</td>
            <td class="text-right text-muted">{{ usd(p.cost) }}</td>
            <td class="text-right">
              <span v-if="!p.track_stock" class="text-muted">—</span>
              <span v-else :class="['pill', p.stock_qty <= 0 ? 'bg-rose-50 text-price' : p.stock_qty <= p.low_stock_threshold ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok']">
                {{ p.stock_qty }}
              </span>
            </td>
            <td class="text-right whitespace-nowrap">
              <button class="btn-ghost p-2" :title="t('Edit')" @click="editing = p"><Pencil :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Barcode / QR label')" @click="labelsFor = [p]"><Barcode :size="17" /></button>
              <template v-if="p.track_stock">
                <button class="btn-ghost p-2" :title="t('Receive stock')" @click="stockFor = { product: p, mode: 'receive' }"><PackagePlus :size="17" /></button>
                <button class="btn-ghost p-2" :title="t('Damaged / expired / lost')" @click="stockFor = { product: p, mode: 'write_off' }"><PackageMinus :size="17" /></button>
                <button class="btn-ghost p-2" :title="t('Stock count')" @click="count(p)"><ClipboardCheck :size="17" /></button>
                <button class="btn-ghost p-2" :title="t('Stock history')" @click="showHistory(p)"><History :size="17" /></button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ProductForm v-if="editing" :key="editing === 'new' ? 'new' : editing.id" :product="editing === 'new' ? null : editing" :barcode="newBarcode" :categories="categories" @close="((editing = null), (newBarcode = ''))" @saved="saved" @category-added="load" />
    <LabelModal v-if="labelsFor" :products="labelsFor" @close="labelsFor = null" @saved="load" />
    <StockModal v-if="stockFor" :product="stockFor.product" :mode="stockFor.mode" :suppliers="suppliers" @close="stockFor = null" @saved="saved" />

    <AppModal v-if="historyOf" :title="t('Stock history: {name}', { name: historyOf.name })" width="max-w-3xl" @close="historyOf = null">
      <div class="overflow-x-auto">
        <table class="table min-w-[640px]">
          <thead>
            <tr>
              <th>{{ t('When') }}</th><th>{{ t('Type') }}</th><th class="text-right">{{ t('Change') }}</th><th class="text-right">{{ t('Balance') }}</th>
              <th class="text-right">{{ t('Unit cost') }}</th><th>{{ t('Details') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in movements" :key="m.id">
              <td class="whitespace-nowrap text-muted">{{ dateTime(m.created_at) }}</td>
              <td>{{ t(KINDS[m.kind] ?? m.kind) }}</td>
              <td :class="['text-right font-semibold', m.change > 0 ? 'text-ok' : 'text-price']">{{ m.change > 0 ? '+' : '' }}{{ m.change }}</td>
              <td class="text-right">{{ m.balance }}</td>
              <td class="text-right text-muted">{{ m.unit_cost === null ? '' : usd(m.unit_cost) }}</td>
              <td class="text-muted">{{ [m.supplier_name, m.reference, m.note].filter(Boolean).join(' · ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppModal>
  </div>
</template>
