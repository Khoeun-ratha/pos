<script setup lang="ts">
// Barcode / QR code labels for one product or many. A product without a barcode can get a new in-store one here.
import { Barcode, Printer, QrCode, Sparkles } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Product, ProductInput } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { codeSvg, type CodeKind, labelCode, newStoreBarcode } from '@/lib/barcode'
import { t } from '@/lib/i18n'
import { LABEL_SIZES, labelCss, labelHtml, type LabelOptions, type LabelSize, printLabels } from '@/lib/labels'
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
const size = ref<LabelSize>(stored('pos.label.size', '50x30'))
const showPrice = ref(stored('pos.label.price', 'yes') === 'yes')
const showStore = ref(stored('pos.label.store', 'yes') === 'yes')
const copiesText = ref('1')
const busy = ref(false)
const preview = ref('')

const single = computed(() => (items.value.length === 1 ? items.value[0]! : null))
const printable = computed(() => items.value.filter((p) => labelCode(p)))
const missing = computed(() => items.value.length - printable.value.length)
const copies = computed(() => Math.min(500, Math.max(1, parseWhole(copiesText.value) ?? 1)))
const options = computed<LabelOptions>(() => ({
  kind: kind.value,
  size: size.value,
  showPrice: showPrice.value,
  exchangeRate: auth.settings.exchange_rate,
  storeName: showStore.value ? auth.settings.store_name : '',
}))

watch(
  [kind, size, showPrice, showStore, () => printable.value[0]],
  async () => {
    remember('pos.label.kind', kind.value)
    remember('pos.label.size', size.value)
    remember('pos.label.price', showPrice.value ? 'yes' : 'no')
    remember('pos.label.store', showStore.value ? 'yes' : 'no')
    const first = printable.value[0]
    try {
      preview.value = first ? labelHtml(first, await codeSvg(labelCode(first), kind.value), options.value) : ''
    } catch (e) {
      preview.value = ''
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
        <template v-if="preview">
          <component :is="'style'">{{ labelCss(size) }}</component>
          <!-- larger than printed, so it is easy to check -->
          <div class="overflow-hidden rounded shadow-md [zoom:1.3] sm:[zoom:1.6]" v-html="preview" />
          <p class="text-center text-xs text-muted">
            {{ t('Code') }}: <span class="font-mono">{{ labelCode(printable[0]!) }}</span>
            <template v-if="!single && printable.length > 1"> · {{ t('first of {n}', { n: printable.length }) }}</template>
          </p>
        </template>
        <div v-else-if="single" class="text-center">
          <p class="mb-3 text-muted">{{ t('This product has no barcode or SKU yet.') }}</p>
          <button class="btn-primary" :disabled="busy" @click="makeBarcode(single)"><Sparkles :size="17" /> {{ t('Make a barcode') }}</button>
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
        </div>
        <div>
          <label class="label">{{ single ? t('How many labels') : t('Labels per product') }}</label>
          <input v-model="copiesText" class="input" inputmode="numeric" />
          <button v-if="single?.track_stock && single.stock_qty > 0" class="mt-1 text-sm font-semibold text-primary hover:underline" @click="copiesText = String(single.stock_qty)">
            {{ t('One for each in stock ({n})', { n: single.stock_qty }) }}
          </button>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="showPrice" type="checkbox" class="size-4 accent-primary" /> {{ t('Show price (USD and riel)') }}</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="showStore" type="checkbox" class="size-4 accent-primary" /> {{ t('Show shop name') }}</label>
        <div v-if="!single && missing" class="space-y-1 rounded-lg bg-warn-soft px-3 py-2 text-sm text-amber-900">
          <p>{{ t('{n} product(s) have no barcode or SKU and are left out:', { n: missing }) }}</p>
          <ul class="max-h-28 overflow-y-auto">
            <li v-for="p in items.filter((x) => !labelCode(x))" :key="p.id" class="flex items-center justify-between gap-2">
              <span class="truncate">{{ p.name }}</span>
              <button class="shrink-0 font-semibold text-primary hover:underline" :disabled="busy" @click="makeBarcode(p)">{{ t('Make a barcode') }}</button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Close') }}</button>
      <button class="btn-primary min-w-44" :disabled="busy || !printable.length" @click="print">
        <Printer :size="18" /> {{ t('Print {n} label(s)', { n: printable.length * copies }) }}
      </button>
    </template>
  </AppModal>
</template>
