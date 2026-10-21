<script setup lang="ts">
// Inventory: stock levels (/inventory), low stock (/inventory/low) and every stock movement (/inventory/movements),
// for the main shop or one branch / warehouse (the "Place" list). Scanning a barcode on the stock pages opens
// "Receive stock" for that product.
import { AlertTriangle, Barcode, ClipboardCheck, History, MapPin, Package, PackageMinus, PackagePlus, PackageX, ScanLine, Search, Wallet } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '@/api/client'
import type { Category, Location, Product, StockMovement, Supplier } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import LabelModal from '@/components/LabelModal.vue'
import MovementTable from '@/components/MovementTable.vue'
import ProductArt from '@/components/ProductArt.vue'
import StockModal from '@/components/StockModal.vue'
import { t } from '@/lib/i18n'
import { num, parseWhole, usd } from '@/lib/money'
import { beep, findByCode, useBarcodeScanner } from '@/lib/scanner'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const route = useRoute()

/** Staff of a branch work on its stock only (the service checks too). */
const myBranch = auth.user?.location_id ?? null

function storedPlace(): number | '' {
  if (myBranch !== null) return myBranch
  try {
    const raw = localStorage.getItem('pos.inventory.place')
    return raw ? Number(raw) : ''
  } catch {
    return ''
  }
}

const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const suppliers = ref<Supplier[]>([])
const locations = ref<Location[]>([])
/** '' = main shop, else a branch / warehouse id. */
const place = ref<number | ''>(storedPlace())
/** product id -> quantity at the chosen branch / warehouse */
const placeStock = ref(new Map<number, number>())
const movements = ref<StockMovement[]>([])
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const categoryId = ref<number | ''>('')
const kind = ref('')
/** movements page: '' everywhere, 'main', or a location id */
const movementPlace = ref<string>('')
const loading = ref(false)

const stockFor = ref<{ product: Product; mode: 'receive' | 'write_off' } | null>(null)
const labelsFor = ref<Product[] | null>(null)
const historyOf = ref<Product | null>(null)
const history = ref<StockMovement[]>([])

const page = computed(() => (route.name === 'movements' ? 'movements' : route.name === 'low-stock' ? 'low' : 'stock'))
const activeLocations = computed(() => locations.value.filter((l) => l.is_active))
const location = computed(() => (place.value === '' ? null : (locations.value.find((l) => l.id === place.value) ?? null)))
const placeName = computed(() => location.value?.name ?? auth.settings.store_name)

const tracked = computed(() => products.value.filter((p) => p.is_active && p.track_stock))
/** Quantity at the place shown. */
const qty = (p: Product) => (location.value ? (placeStock.value.get(p.id) ?? 0) : p.stock_qty)
const isLow = (p: Product) => qty(p) <= p.low_stock_threshold
const stats = computed(() => ({
  items: tracked.value.filter((p) => qty(p) > 0).length,
  units: tracked.value.reduce((n, p) => n + Math.max(qty(p), 0), 0),
  cost: tracked.value.reduce((n, p) => n + Math.max(qty(p), 0) * p.cost, 0),
  retail: tracked.value.reduce((n, p) => n + Math.max(qty(p), 0) * p.price, 0),
  low: tracked.value.filter((p) => isLow(p) && qty(p) > 0).length,
  out: tracked.value.filter((p) => qty(p) <= 0).length,
}))

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return tracked.value
    .filter(
      (p) =>
        (page.value !== 'low' || isLow(p)) &&
        (categoryId.value === '' || p.category_id === categoryId.value) &&
        (!q || p.name.toLowerCase().includes(q) || (p.barcode ?? '').includes(q) || (p.sku ?? '').toLowerCase().includes(q)),
    )
    .sort((a, b) => (page.value === 'low' ? qty(a) - qty(b) : a.name.localeCompare(b.name)))
})

const KIND_FILTERS = [
  { value: '', label: 'All types' },
  { value: 'stock_in', label: 'Received' },
  { value: 'sale', label: 'Sale' },
  { value: 'refund', label: 'Refund' },
  { value: 'write_off', label: 'Write-off' },
  { value: 'count', label: 'Stock count' },
  { value: 'adjustment', label: 'Adjustment' },
  { value: 'transfer_out', label: 'Transfer sent' },
  { value: 'transfer_in', label: 'Transfer received' },
]
const visibleMovements = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? movements.value.filter((m) => m.product_name.toLowerCase().includes(q)) : movements.value
})

async function loadPlaceStock() {
  if (place.value === '') return (placeStock.value = new Map())
  const rows = await api.get<{ product_id: number; qty: number }[]>(`/locations/${place.value}/stock`)
  placeStock.value = new Map(rows.map((r) => [r.product_id, r.qty]))
}

async function loadProducts() {
  try {
    ;[products.value, categories.value, suppliers.value, locations.value] = await Promise.all([
      api.get<Product[]>('/products', { include_inactive: true, limit: 5000 }),
      api.get<Category[]>('/categories'),
      api.get<Supplier[]>('/suppliers'),
      api.get<Location[]>('/locations'),
    ])
    if (place.value !== '' && !activeLocations.value.some((l) => l.id === place.value)) place.value = ''
    await loadPlaceStock()
  } catch (e) {
    ui.error(e)
  }
}

async function loadMovements() {
  loading.value = true
  try {
    movements.value = await api.get<StockMovement[]>('/inventory/movements', { kind: kind.value, location: movementPlace.value, limit: 500 })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

async function count(p: Product) {
  const text = await ui.prompt({
    title: t('Stock count: {name}', { name: p.name }),
    label: t('Quantity on the shelf at {place} (system says {n})', { place: placeName.value, n: qty(p) }),
    inputmode: 'numeric',
  })
  const counted = parseWhole(text)
  if (counted === null) return
  try {
    await api.post('/inventory/count', { product_id: p.id, counted_qty: counted, location_id: location.value?.id ?? null })
    ui.toast(t('Stock updated'), 'success')
    loadProducts()
  } catch (e) {
    ui.error(e)
  }
}

async function showHistory(p: Product) {
  historyOf.value = p
  history.value = []
  try {
    history.value = await api.get<StockMovement[]>('/inventory/movements', { product_id: p.id, location: location.value?.id ?? 'main', limit: 100 })
  } catch (e) {
    ui.error(e)
  }
}

function saved() {
  stockFor.value = null
  loadProducts()
  if (page.value === 'movements') loadMovements()
}

// scan a delivery: the product's "Receive stock" opens
useBarcodeScanner(
  (code) => {
    const product = findByCode(products.value, code)
    if (!product) {
      beep('error')
      return ui.toast(t('No product with barcode {code}', { code }), 'error')
    }
    if (!product.track_stock) return ui.toast(t('{name} does not track stock', { name: product.name }), 'error')
    beep('ok')
    stockFor.value = { product, mode: 'receive' }
  },
  () => page.value !== 'movements' && !stockFor.value && !labelsFor.value && !historyOf.value,
)

watch(place, (value) => {
  try {
    localStorage.setItem('pos.inventory.place', String(value))
  } catch {
    // private window
  }
  loadPlaceStock().catch(ui.error)
})
watch([kind, movementPlace], loadMovements)
watch(page, (p) => p === 'movements' && loadMovements())
onMounted(() => {
  loadProducts()
  if (page.value === 'movements') loadMovements()
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
    <!-- which place: main shop or a branch / warehouse -->
    <div v-if="myBranch !== null" class="flex items-center gap-2 text-sm font-semibold">
      <MapPin :size="18" class="text-muted" /> {{ auth.user?.location_name }}
    </div>
    <div v-else-if="page !== 'movements' && activeLocations.length" class="flex flex-wrap items-center gap-2">
      <MapPin :size="18" class="text-muted" />
      <button :class="['pill px-3 py-1.5', place === '' ? 'bg-primary text-white' : 'bg-white text-ink ring-1 ring-line hover:bg-page']" @click="place = ''">
        {{ auth.settings.store_name }} · {{ t('main shop') }}
      </button>
      <button
        v-for="l in activeLocations"
        :key="l.id"
        :class="['pill px-3 py-1.5', place === l.id ? 'bg-primary text-white' : 'bg-white text-ink ring-1 ring-line hover:bg-page']"
        @click="place = l.id"
      >
        {{ l.name }} · {{ t(l.kind) }}
      </button>
    </div>

    <!-- totals -->
    <div v-if="page !== 'movements'" class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div class="card flex items-center gap-3 p-4">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary"><Package :size="21" /></div>
        <div class="min-w-0">
          <p class="text-sm text-muted">{{ t('Products in stock') }}</p>
          <p class="text-xl font-extrabold">{{ num(stats.items) }}</p>
          <p class="truncate text-xs text-muted">{{ t('{n} units', { n: num(stats.units) }) }}</p>
        </div>
      </div>
      <div class="card flex items-center gap-3 p-4">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-ok-soft text-ok"><Wallet :size="21" /></div>
        <div class="min-w-0">
          <p class="text-sm text-muted">{{ t('Stock value (cost)') }}</p>
          <p class="text-xl font-extrabold">{{ usd(stats.cost) }}</p>
          <p class="truncate text-xs text-muted">{{ t('Selling price {amount}', { amount: usd(stats.retail) }) }}</p>
        </div>
      </div>
      <RouterLink to="/inventory/low" class="card flex items-center gap-3 p-4 transition hover:border-warn">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-warn-soft text-warn"><AlertTriangle :size="21" /></div>
        <div>
          <p class="text-sm text-muted">{{ t('Low stock') }}</p>
          <p class="text-xl font-extrabold">{{ num(stats.low) }}</p>
        </div>
      </RouterLink>
      <RouterLink to="/inventory/low" class="card flex items-center gap-3 p-4 transition hover:border-price">
        <div class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-price"><PackageX :size="21" /></div>
        <div>
          <p class="text-sm text-muted">{{ t('Out of stock') }}</p>
          <p class="text-xl font-extrabold">{{ num(stats.out) }}</p>
        </div>
      </RouterLink>
    </div>

    <!-- filters -->
    <div class="card flex flex-wrap items-center gap-2 p-3">
      <div class="relative min-w-56 flex-1">
        <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-10" :placeholder="page === 'movements' ? t('Search product') : t('Search name, SKU or barcode')" />
      </div>
      <template v-if="page === 'movements'">
        <select v-if="locations.length && myBranch === null" v-model="movementPlace" class="input w-auto">
          <option value="">{{ t('Every place') }}</option>
          <option value="main">{{ auth.settings.store_name }}</option>
          <option v-for="l in locations" :key="l.id" :value="String(l.id)">{{ l.name }}</option>
        </select>
        <select v-model="kind" class="input w-auto">
          <option v-for="k in KIND_FILTERS" :key="k.value" :value="k.value">{{ t(k.label) }}</option>
        </select>
      </template>
      <template v-else>
        <select v-model="categoryId" class="input w-auto">
          <option value="">{{ t('All categories') }}</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <button class="btn-outline" :disabled="!visible.length" @click="labelsFor = visible">
          <Barcode :size="17" /> {{ t('Print labels') }}
        </button>
      </template>
    </div>
    <p v-if="page !== 'movements'" class="flex items-center gap-2 px-1 text-sm text-muted">
      <ScanLine :size="16" class="shrink-0" /> {{ t('Scan a product barcode to receive stock for it at {place}.', { place: placeName }) }}
    </p>

    <!-- stock levels / low stock -->
    <div v-if="page !== 'movements'" class="card overflow-x-auto">
      <table class="table min-w-[920px]">
        <thead>
          <tr>
            <th>{{ t('Product') }}</th><th>{{ t('Category') }}</th><th>{{ t('Barcode') }}</th>
            <th class="text-right">{{ t('Cost') }}</th><th class="text-right">{{ t('Stock') }}</th><th class="text-right">{{ t('Low at') }}</th>
            <th class="text-right">{{ t('Value') }}</th><th class="text-right">{{ t('Actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in visible" :key="p.id">
            <td>
              <div class="flex items-center gap-3">
                <ProductArt :category="p.category_name" :image="p.image_url" :alt="p.name" :size="18" class="size-10 shrink-0 rounded-xl" />
                <div>
                  <p class="font-semibold">{{ p.name }}</p>
                  <p class="text-xs text-muted">{{ p.sku }}</p>
                </div>
              </div>
            </td>
            <td class="text-muted">{{ p.category_name ?? '—' }}</td>
            <td class="font-mono text-xs text-muted">{{ p.barcode ?? '—' }}</td>
            <td class="text-right text-muted">{{ usd(p.cost) }}</td>
            <td class="text-right">
              <span :class="['pill', qty(p) <= 0 ? 'bg-rose-50 text-price' : isLow(p) ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok']">{{ qty(p) }}</span>
            </td>
            <td class="text-right text-muted">{{ p.low_stock_threshold }}</td>
            <td class="text-right font-semibold">{{ usd(Math.max(qty(p), 0) * p.cost) }}</td>
            <td class="text-right whitespace-nowrap">
              <button class="btn mr-1 bg-ok-soft px-2.5 py-1.5 text-sm text-ok hover:brightness-95" :title="t('Receive stock')" @click="stockFor = { product: p, mode: 'receive' }">
                <PackagePlus :size="16" /> {{ t('Receive') }}
              </button>
              <button class="btn-ghost p-2 text-price" :title="t('Damaged / expired / lost')" @click="stockFor = { product: p, mode: 'write_off' }"><PackageMinus :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Stock count')" @click="count(p)"><ClipboardCheck :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Stock history')" @click="showHistory(p)"><History :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Barcode / QR label')" @click="labelsFor = [p]"><Barcode :size="17" /></button>
            </td>
          </tr>
          <tr v-if="!visible.length">
            <td colspan="8" class="py-10 text-center text-muted">{{ page === 'low' ? t('Nothing is low on stock') : t('No products found') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- every movement -->
    <div v-else class="card">
      <p v-if="loading" class="p-6 text-center text-muted">{{ t('Loading...') }}</p>
      <MovementTable v-else :movements="visibleMovements" show-product :show-location="locations.length > 0" :main-name="auth.settings.store_name" />
    </div>

    <StockModal
      v-if="stockFor"
      :product="stockFor.product"
      :mode="stockFor.mode"
      :suppliers="suppliers"
      :location="location"
      :on-hand="qty(stockFor.product)"
      @close="stockFor = null"
      @saved="saved"
    />
    <LabelModal v-if="labelsFor" :products="labelsFor" @close="labelsFor = null" @saved="loadProducts" />
    <AppModal v-if="historyOf" :title="t('Stock history: {name}', { name: historyOf.name }) + (location ? ` · ${location.name}` : '')" width="max-w-3xl" @close="historyOf = null">
      <MovementTable :movements="history" />
    </AppModal>
  </div>
</template>
