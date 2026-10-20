<script setup lang="ts">
import { Camera, Package, ScanBarcode, Search, ShoppingBag, Volume2, VolumeX, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api, ApiError } from '@/api/client'
import type { Category, ParkedOrder, Product, Sale } from '@/api/types'
import ProductArt from '@/components/ProductArt.vue'
import CameraScanner from '@/components/sell/CameraScanner.vue'
import CartPanel from '@/components/sell/CartPanel.vue'
import PaymentModal from '@/components/sell/PaymentModal.vue'
import ReceiptModal from '@/components/sell/ReceiptModal.vue'
import { t } from '@/lib/i18n'
import { usd } from '@/lib/money'
import { beep, cleanCode, findByCode, type ScanOutcome, setSound, soundOn, splitQty, useBarcodeScanner } from '@/lib/scanner'
import { useAuth } from '@/stores/auth'
import { useCart } from '@/stores/cart'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'

const cart = useCart()
const shift = useShift()
const ui = useUi()
const auth = useAuth()
const router = useRouter()

const categories = ref<Category[]>([])
const products = ref<Product[]>([])
const loading = ref(true)
const categoryId = ref<number | null>(null)
const query = ref('')
const search = ref<HTMLInputElement>()
const paying = ref(false)
const receipt = ref<Sale | null>(null)
const cartOpen = ref(false) // phone layout
const camera = ref(false)

/** "3*" typed before a scan or tap: how many to add. */
const typed = computed(() => splitQty(query.value))
const pendingQty = computed(() => (/^\s*\d{1,4}\s*[*xX×]\s*$/.test(cleanCode(query.value)) ? typed.value.qty : null))

const visible = computed(() => {
  const q = typed.value.rest.toLowerCase()
  return products.value.filter(
    (p) =>
      (categoryId.value === null || p.category_id === categoryId.value) &&
      (!q || p.name.toLowerCase().includes(q) || (p.barcode ?? '').includes(q) || (p.sku ?? '').toLowerCase().includes(q)),
  )
})

async function load() {
  try {
    ;[categories.value, products.value] = await Promise.all([api.get<Category[]>('/categories'), api.get<Product[]>('/products', { limit: 5000 })])
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

/** Mouse / keyboard tills keep the cursor in the search box; on touch screens that would pop up the keyboard. */
const finePointer = window.matchMedia?.('(pointer: fine)').matches ?? true
function focusSearch() {
  if (finePointer) nextTick(() => search.value?.focus())
}

const inCart = (product: Product) => cart.lines.filter((l) => l.product.id === product.id).reduce((n, l) => n + l.qty, 0)

/** Adds `qty` of a product (a typed "3*" in front counts too) and clears the search box. Returns a stock warning,
 *  which is also shown unless `quiet`. */
function add(product: Product, qty = typed.value.qty, quiet = false): string | null {
  cart.add(product, qty)
  beep('ok')
  query.value = ''
  const warning = product.track_stock && inCart(product) > product.stock_qty ? t('only {n} in stock', { n: Math.max(0, product.stock_qty) }) : null
  if (warning && !quiet) ui.toast(`${product.name}: ${warning}`)
  if (!quiet) focusSearch()
  return warning
}

/** The product with this barcode / SKU; products added since the screen loaded are asked from the service. */
async function lookup(code: string): Promise<Product | null> {
  const known = findByCode(products.value, code)
  if (known) return known
  try {
    const product = await api.get<Product>(`/products/barcode/${encodeURIComponent(cleanCode(code))}`)
    products.value.push(product)
    return product
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null
    throw e
  }
}

/** A scanned (or typed) barcode / SKU. */
async function addByCode(code: string, qty = typed.value.qty) {
  let product: Product | null
  try {
    product = await lookup(code)
  } catch (e) {
    beep('error')
    ui.error(e)
    return
  }
  if (product) return void add(product, qty)
  beep('error')
  query.value = ''
  if (auth.can('products')) {
    if (await ui.confirm('Unknown barcode', t('No product has barcode {code}. Add it as a new product?', { code }), 'New product')) {
      router.push({ path: '/products', query: { barcode: code } })
    }
  } else {
    ui.toast(t('No product with barcode {code}. Ask a manager to add it.', { code }), 'error')
  }
  focusSearch()
}

/** Enter in the search box: a barcode / SKU, or the only product that matches the words typed. */
function onEnter() {
  const { qty, rest } = typed.value
  if (!rest) return
  const match = findByCode(products.value, rest) ?? (visible.value.length === 1 ? visible.value[0] : undefined)
  if (match) add(match, qty)
  else if (/^[0-9A-Za-z-]{4,}$/.test(cleanCode(rest))) addByCode(cleanCode(rest), qty)
  else if (visible.value.length) ui.toast(t('{n} products match. Tap the one you want.', { n: visible.value.length }))
}

/** Scans are only for the till itself; dialogs (payment, PIN, customer) keep their own input. A scan while the
 *  receipt of the last sale is showing starts the next sale. */
function scannerEnabled() {
  const modals = document.querySelectorAll('[data-modal]').length
  return modals === 0 || (modals === 1 && receipt.value !== null && !paying.value && !ui.dialog)
}

/** Camera window: adds quietly and tells the cashier in the window itself. */
async function cameraScan(code: string): Promise<ScanOutcome> {
  try {
    const product = await lookup(code)
    if (!product) {
      beep('error')
      return { ok: false, message: t('No product with barcode {code}', { code }) }
    }
    const warning = add(product, typed.value.qty, true)
    const message = `${product.name} · ${usd(product.price)} · ${t('{n} in cart', { n: inCart(product) })}`
    return { ok: true, message: warning ? `${message} (${warning})` : message }
  } catch (e) {
    beep('error')
    return { ok: false, message: e instanceof Error ? e.message : String(e) }
  }
}

useBarcodeScanner((code) => {
  receipt.value = null
  addByCode(code)
}, scannerEnabled)

function stock(p: Product) {
  if (!p.track_stock) return { text: t('Made to order'), color: 'text-muted' }
  if (p.stock_qty <= 0) return { text: t('Out of stock'), color: 'text-price' }
  if (p.stock_qty <= p.low_stock_threshold) return { text: t('Only {n} left', { n: p.stock_qty }), color: 'text-warn' }
  return { text: t('{n} in stock', { n: p.stock_qty }), color: 'text-ok' }
}

function onPaid(sale: Sale) {
  paying.value = false
  cartOpen.value = false
  cart.reset()
  receipt.value = sale
  load() // fresh stock levels
  shift.refresh().catch(() => {})
}

function onKey(e: KeyboardEvent) {
  if (document.querySelector('[data-modal]')) return
  if (e.key === 'F2') {
    e.preventDefault()
    search.value?.focus()
    search.value?.select()
  } else if (e.key === 'F4' && !cart.isEmpty) {
    e.preventDefault()
    cart.hold()
  } else if (e.key === 'F12' && !cart.isEmpty) {
    e.preventDefault()
    startPayment()
  } else if (e.key === 'Escape' && query.value) {
    query.value = ''
  }
}

// back to scanning as soon as the receipt or payment window closes
watch([receipt, paying], ([r, p]) => !r && !p && focusSearch())

/** A standard till takes money only into a counted cash drawer, and only at today's prices. */
async function startPayment() {
  if (shift.loaded && !shift.current) {
    if (await ui.confirm('Open a shift first', 'Count the cash in the drawer and open a shift before taking payment.', 'Open shift')) router.push('/shift')
    return
  }
  if (!(await cart.approveDiscounts())) return
  if (await cart.syncPrices()) paying.value = true
}

function resume(order: ParkedOrder) {
  cartOpen.value = false
  cart.resume(order, products.value)
}

// held orders from the other tills (and ones sent to this cashier) show up without a reload
let heldTimer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  load()
  cart.loadHeld().catch(() => {})
  heldTimer = setInterval(() => document.visibilityState === 'visible' && cart.loadHeld().catch(() => {}), 15_000)
  focusSearch()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  clearInterval(heldTimer)
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="flex h-full">
    <section class="flex min-w-0 flex-1 flex-col">
      <div v-if="shift.loaded && !shift.current" class="mx-4 mt-4 flex items-center gap-3 rounded-xl bg-warn-soft px-4 py-2.5 text-amber-900">
        <span class="flex-1">{{ t('No open shift. Open one to count your cash drawer.') }}</span>
        <RouterLink to="/shift" class="font-semibold text-primary">{{ t('Open shift') }}</RouterLink>
      </div>

      <div class="px-4 pt-4">
        <div class="relative">
          <ScanBarcode v-if="pendingQty" :size="20" class="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-primary" />
          <Search v-else :size="20" class="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-muted" />
          <input
            ref="search"
            v-model="query"
            class="input py-3.5 pr-28 pl-12 text-base"
            :placeholder="t('Search or scan a barcode... (F2)')"
            autocomplete="off"
            @keydown.enter.prevent="onEnter"
          />
          <div class="absolute top-1/2 right-3 flex -translate-y-1/2 items-center gap-1">
            <button v-if="query" class="rounded-lg p-1 text-muted hover:bg-page" :aria-label="t('Clear search')" @click="query = ''">
              <X :size="18" />
            </button>
            <button class="rounded-lg p-1 text-primary hover:bg-page" :title="t('Scan with camera')" :aria-label="t('Scan with camera')" @click="camera = true">
              <Camera :size="19" />
            </button>
            <button
              class="rounded-lg p-1 text-muted hover:bg-page"
              :title="soundOn ? t('Scanner sound on') : t('Scanner sound off')"
              :aria-label="soundOn ? t('Scanner sound on') : t('Scanner sound off')"
              @click="setSound(!soundOn)"
            >
              <Volume2 v-if="soundOn" :size="18" />
              <VolumeX v-else :size="18" />
            </button>
          </div>
        </div>
        <p v-if="pendingQty" class="mt-1.5 px-1 text-sm font-semibold text-primary">{{ t('Next scan or tap adds {n}', { n: pendingQty }) }}</p>
        <p v-else-if="finePointer" class="mt-1.5 hidden gap-4 px-1 text-xs text-muted lg:flex">
          <span><kbd class="kbd">F2</kbd> {{ t('search') }}</span>
          <span><kbd class="kbd">3*</kbd> {{ t('quantity, then scan') }}</span>
          <span><kbd class="kbd">F4</kbd> {{ t('hold') }}</span>
          <span><kbd class="kbd">F12</kbd> {{ t('pay') }}</span>
        </p>
      </div>

      <div class="flex gap-1.5 overflow-x-auto border-b border-line px-4 py-3">
        <button
          v-for="c in [{ id: null, name: 'All' }, ...categories]"
          :key="c.id ?? 'all'"
          :class="['shrink-0 rounded-full px-4 py-1.5 font-medium transition', categoryId === c.id ? 'bg-primary text-white' : 'text-ink hover:bg-white']"
          @click="categoryId = c.id"
        >
          {{ c.name }}
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-4 pb-24 lg:pb-4">
        <p v-if="loading" class="py-16 text-center text-muted">{{ t('Loading products...') }}</p>
        <div v-else-if="!visible.length" class="flex flex-col items-center py-16 text-muted">
          <Package :size="40" class="mb-2 text-line" />
          {{ t('No products found') }}
        </div>
        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3.5 sm:grid-cols-[repeat(auto-fill,minmax(176px,1fr))]">
          <button
            v-for="p in visible"
            :key="p.id"
            class="group flex flex-col rounded-2xl bg-white p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            @click="add(p)"
          >
            <ProductArt :category="p.category_name" :image="p.image_url" :alt="p.name" :size="38" class="mb-2.5 aspect-[4/3] w-full rounded-xl" />
            <span class="line-clamp-2 min-h-[2.6em] leading-tight font-bold">{{ p.name }}</span>
            <span class="mt-1 text-xl font-extrabold text-price">{{ usd(p.price) }}</span>
            <span :class="['flex items-center gap-1 text-xs font-semibold', stock(p).color]">
              <Package :size="12" />
              {{ stock(p).text }}
            </span>
          </button>
        </div>
      </div>
    </section>

    <!-- cart: side panel on wide screens, bottom sheet on phones -->
    <aside id="cart" class="hidden w-[360px] shrink-0 border-l border-line bg-white lg:flex xl:w-[420px]">
      <CartPanel class="flex-1" @pay="startPayment" @resume="resume" />
    </aside>

    <div class="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-white p-3 lg:hidden">
      <button class="btn-primary w-full py-3.5" :disabled="cart.isEmpty" @click="cartOpen = true">
        <ShoppingBag :size="20" />
        <span class="flex-1 text-left">{{ cart.isEmpty ? t('Tap a product to add') : `View cart · ${cart.itemCount} item(s)` }}</span>
        <span class="font-bold">Pay · {{ usd(cart.totals.total) }}</span>
      </button>
    </div>
    <Teleport to="body">
      <div v-if="cartOpen" class="fixed inset-0 z-30 flex flex-col bg-slate-900/40 lg:hidden" @click.self="cartOpen = false">
        <div class="mt-auto flex h-[88vh] flex-col overflow-hidden rounded-t-2xl bg-white">
          <div class="flex items-center justify-between border-b border-line px-4 py-3">
            <span class="font-bold">{{ t('Cart') }}</span>
            <button class="btn-ghost p-2" :aria-label="t('Close cart')" @click="cartOpen = false"><X :size="20" /></button>
          </div>
          <CartPanel class="min-h-0 flex-1" @pay="startPayment" @resume="resume" />
        </div>
      </div>
    </Teleport>

    <CameraScanner v-if="camera" :on-scan="cameraScan" @close="((camera = false), focusSearch())" />
    <PaymentModal v-if="paying" @close="paying = false" @paid="onPaid" />
    <ReceiptModal v-if="receipt" :sale="receipt" just-sold @close="receipt = null" />
  </div>
</template>
