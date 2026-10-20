<script setup lang="ts">
// Barcode / QR code labels for one product or many. A product without a barcode can get a new in-store one here.
import { Barcode, Printer, QrCode, Sparkles } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Product, ProductInput } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { codeSvg, type CodeKind, labelCode, newStoreBarcode } from '@/lib/barcode'
import { t } from '@/lib/i18n'
import {
  buildLabels,
  isSheet,
  LABEL_SIZES,
  labelCss,
  labelDims,
  labelHtml,
  type LabelOptions,
  type LabelSize,
  MAX_COLS,
  MAX_ROWS,
  pageCount,
  perPage,
  printLabels,
  SHEET_PRESETS,
  sheetCss,
  sheetPages,
} from '@/lib/labels'
import { parseWhole } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const props = defineProps<{ products: Product[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const auth = useAuth()
const ui = useUi()

function stored<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback
  } catch {
    return fallback
  }
}
function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // private window
  }
}

const items = ref<Product[]>([...props.products])
const kind = ref<CodeKind>(stored('pos.label.kind', 'barcode'))
const size = ref<LabelSize>(stored('pos.label.layout', 'a4'))
const colsText = ref<string>(stored('pos.label.cols', '3'))
const rowsText = ref<string>(stored('pos.label.rows', '8'))
const skipText = ref('0')
const cutLines = ref(stored('pos.label.cut', 'yes') === 'yes')
const showPrice = ref(stored('pos.label.price', 'yes') === 'yes')
const showStore = ref(stored('pos.label.store', 'yes') === 'yes')
const copiesText = ref('1')
const busy = ref(false)
const preview = ref('')
const sheetPreview = ref('')

const single = computed(() => (items.value.length === 1 ? items.value[0]! : null))
const printable = computed(() => items.value.filter((p) => labelCode(p)))
const missing = computed(() => items.value.length - printable.value.length)
const copies = computed(() => Math.min(500, Math.max(1, parseWhole(copiesText.value) ?? 1)))
const clamp = (text: string, min: number, max: number, fallback: number) => Math.min(max, Math.max(min, parseWhole(text) ?? fallback))
const cols = computed(() => clamp(colsText.value, 1, MAX_COLS, 3))
const rows = computed(() => clamp(rowsText.value, 1, MAX_ROWS, 8))
const sheet = computed(() => isSheet({ size: size.value }))
const options = computed<LabelOptions>(() => ({
  kind: kind.value,
  size: size.value,
  showPrice: showPrice.value,
  exchangeRate: auth.settings.exchange_rate,
  storeName: showStore.value ? auth.settings.store_name : '',
  cols: cols.value,
  rows: rows.value,
  skip: Math.min(perPage({ cols: cols.value, rows: rows.value }) - 1, Math.max(0, parseWhole(skipText.value) ?? 0)),
  cutLines: cutLines.value,
}))
const dims = computed(() => labelDims(options.value))
const total = computed(() => printable.value.length * copies.value)
const pages = computed(() => pageCount(total.value, options.value))

function usePreset([c, r]: [number, number]) {
  colsText.value = String(c)
  rowsText.value = String(r)
}

watch(
  [options, copies, printable],
  async () => {
    remember('pos.label.kind', kind.value)
    remember('pos.label.layout', size.value)
    remember('pos.label.price', showPrice.value ? 'yes' : 'no')
    remember('pos.label.store', showStore.value ? 'yes' : 'no')
    remember('pos.label.cols', String(cols.value))
    remember('pos.label.rows', String(rows.value))
    remember('pos.label.cut', cutLines.value ? 'yes' : 'no')
    const first = printable.value[0]
    try {
      preview.value = first ? labelHtml(first, await codeSvg(labelCode(first), kind.value), options.value) : ''
      // the first page as it will print
      sheetPreview.value =
        first && sheet.value ? sheetPages(await buildLabels(printable.value, copies.value, options.value, perPage(options.value)), options.value)[0] ?? '' : ''
    } catch (e) {
      preview.value = sheetPreview.value = ''
      ui.error(e)
    }
  },
  { immediate: true },
)

/** Gives the product a new in-store EAN-13 barcode and saves it. */
async function makeBarcode(p: Product) {
  const body: ProductInput = {
    name: p.name,
    barcode: newStoreBarcode(),
    sku: p.sku,
    category_id: p.category_id,
    price: p.price,
    cost: p.cost,
    track_stock: p.track_stock,
    low_stock_threshold: p.low_stock_threshold,
    is_active: p.is_active,
  }
  busy.value = true
  try {
    const saved = await api.put<Product>(`/products/${p.id}`, body)
    items.value = items.value.map((x) => (x.id === saved.id ? saved : x))
    ui.toast(t('Barcode {code} saved for {name}', { code: saved.barcode ?? '', name: saved.name }), 'success')
    emit('saved')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

async function print() {
  busy.value = true
  try {
    const n = await printLabels(printable.value, copies.value, options.value)
    if (!n) ui.toast(t('No product here has a barcode or SKU to print'), 'error')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="single ? t('Label: {name}', { name: single.name }) : t('Labels for {n} products', { n: items.length })" width="max-w-3xl" @close="emit('close')">
    <div class="grid gap-5 md:grid-cols-[1fr_16rem]">
      <!-- preview, at the printed size -->
      <div class="flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl bg-page p-4">
        <template v-if="preview && sheet">
          <component :is="'style'">{{ labelCss(dims) + sheetCss(options) }}</component>
          <!-- page 1 of the A4 sheet, shrunk to fit -->
          <div class="overflow-hidden shadow-md [zoom:0.42] sm:[zoom:0.5]" data-sheet-preview v-html="sheetPreview" />
          <p class="text-center text-xs text-muted">
            {{ t('{cols} × {rows} = {n} labels a page', { cols, rows, n: perPage(options) }) }} · {{ dims[0] }} × {{ dims[1] }} mm ·
            {{ t('{n} page(s)', { n: pages }) }}
          </p>
        </template>
        <template v-else-if="preview">
          <component :is="'style'">{{ labelCss(dims) }}</component>
          <!-- larger than printed, so it is easy to check -->
          <div class="overflow-hidden rounded shadow-md [zoom:1.3] sm:[zoom:1.6]" v-html="preview" />
          <p class="text-center text-xs text-muted">
            {{ t('Code') }}: <span class="font-mono">{{ labelCode(printable[0]!) }}</span>
            <template v-if="!single && printable.length > 1"> · {{ t('first of {n}', { n: printable.length }) }}</template>
          </p>
        </template>
        <div v-else-if="single" class="text-center">
          <p class="mb-3 text-muted">{{ t('This product has no barcode or SKU yet.') }}</p>
          <button v-if="auth.can('products')" class="btn-primary" :disabled="busy" @click="makeBarcode(single)"><Sparkles :size="17" /> {{ t('Make a barcode') }}</button>
          <p class="mt-2 text-xs text-muted">{{ t('A new EAN-13 number starting with 200 (numbers kept for shops), saved on the product.') }}</p>
        </div>
        <p v-else class="text-muted">{{ t('No product here has a barcode or SKU to print') }}</p>
      </div>

      <!-- options -->
      <div class="space-y-3">
        <div>
          <p class="label">{{ t('Code') }}</p>
          <div class="grid grid-cols-2 gap-1 rounded-xl bg-page p-1">
            <button :class="['flex items-center justify-center gap-1.5 rounded-lg py-2 font-semibold', kind === 'barcode' ? 'bg-white shadow-sm' : 'text-muted']" @click="kind = 'barcode'">
              <Barcode :size="17" /> {{ t('Barcode') }}
            </button>
            <button :class="['flex items-center justify-center gap-1.5 rounded-lg py-2 font-semibold', kind === 'qr' ? 'bg-white shadow-sm' : 'text-muted']" @click="kind = 'qr'">
              <QrCode :size="17" /> {{ t('QR code') }}
            </button>
          </div>
        </div>
        <div>
          <label class="label">{{ t('Label size') }}</label>
          <select v-model="size" class="input">
            <option v-for="s in LABEL_SIZES" :key="s.value" :value="s.value">{{ t(s.label) }}</option>
          </select>
          <div v-if="!sheet" class="mt-2 space-y-1 rounded-lg bg-warn-soft px-3 py-2 text-sm text-amber-900" data-roll-warning>
            <p>{{ t('One label per page: only for a label printer or receipt roll. On a normal printer, use A4 paper.') }}</p>
            <button class="font-semibold text-primary hover:underline" @click="size = 'a4'">{{ t('Use A4 paper: many labels per page') }}</button>
          </div>
        </div>
        <div v-if="sheet" class="space-y-2 rounded-xl bg-page p-3">
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="label">{{ t('Columns') }}</label>
              <input v-model="colsText" class="input" inputmode="numeric" data-cols />
            </div>
            <div>
              <label class="label">{{ t('Rows') }}</label>
              <input v-model="rowsText" class="input" inputmode="numeric" data-rows />
            </div>
          </div>
          <div class="flex flex-wrap gap-1">
            <button
              v-for="p in SHEET_PRESETS"
              :key="p.join('x')"
              :class="['rounded-lg px-2 py-1 text-sm font-semibold', cols === p[0] && rows === p[1] ? 'bg-primary text-white' : 'bg-white text-muted hover:text-ink']"
              @click="usePreset(p)"
            >
              {{ p[0] }} × {{ p[1] }}
            </button>
          </div>
          <div>
            <label class="label">{{ t('Skip places already used') }}</label>
            <input v-model="skipText" class="input" inputmode="numeric" />
          </div>
          <label class="flex items-center gap-2 text-sm"><input v-model="cutLines" type="checkbox" class="size-4 accent-primary" /> {{ t('Cut lines') }}</label>
        </div>
        <div>
          <label class="label">{{ single ? t('How many labels') : t('Labels per product') }}</label>
          <input v-model="copiesText" class="input" inputmode="numeric" />
          <button v-if="single?.track_stock && single.stock_qty > 0" class="mt-1 text-sm font-semibold text-primary hover:underline" @click="copiesText = String(single.stock_qty)">
            {{ t('One for each in stock ({n})', { n: single.stock_qty }) }}
          </button>
          <button v-if="single && sheet" class="mt-1 block text-sm font-semibold text-primary hover:underline" @click="copiesText = String(perPage(options) - options.skip)">
            {{ t('Fill one page ({n})', { n: perPage(options) - options.skip }) }}
          </button>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="showPrice" type="checkbox" class="size-4 accent-primary" /> {{ t('Show price (USD and riel)') }}</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="showStore" type="checkbox" class="size-4 accent-primary" /> {{ t('Show shop name') }}</label>
        <div v-if="!single && missing" class="space-y-1 rounded-lg bg-warn-soft px-3 py-2 text-sm text-amber-900">
          <p>{{ t('{n} product(s) have no barcode or SKU and are left out:', { n: missing }) }}</p>
          <ul class="max-h-28 overflow-y-auto">
            <li v-for="p in items.filter((x) => !labelCode(x))" :key="p.id" class="flex items-center justify-between gap-2">
              <span class="truncate">{{ p.name }}</span>
              <button v-if="auth.can('products')" class="shrink-0 font-semibold text-primary hover:underline" :disabled="busy" @click="makeBarcode(p)">{{ t('Make a barcode') }}</button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Close') }}</button>
      <button class="btn-primary min-w-44" :disabled="busy || !printable.length" @click="print">
        <Printer :size="18" /> {{ t('Print {n} label(s)', { n: total }) }}
      </button>
    </template>
  </AppModal>
</template>
