<script setup lang="ts">
// Barcode / QR labels: tick the products (or scan them), then print. LabelModal does the layout and printing.
import { Barcode, QrCode, ScanLine, Search } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Category, Product } from '@/api/types'
import LabelModal from '@/components/LabelModal.vue'
import ProductArt from '@/components/ProductArt.vue'
import { labelCode } from '@/lib/barcode'
import { t } from '@/lib/i18n'
import { usd } from '@/lib/money'
import { beep, findByCode, useBarcodeScanner } from '@/lib/scanner'
import { useUi } from '@/stores/ui'

const ui = useUi()
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const query = ref('')
const categoryId = ref<number | ''>('')
const selected = ref<Set<number>>(new Set())
const labelsFor = ref<Product[] | null>(null)

const active = computed(() => products.value.filter((p) => p.is_active))
const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return active.value.filter(
    (p) =>
      (categoryId.value === '' || p.category_id === categoryId.value) &&
      (!q || p.name.toLowerCase().includes(q) || (p.barcode ?? '').includes(q) || (p.sku ?? '').toLowerCase().includes(q)),
  )
})
const chosen = computed(() => active.value.filter((p) => selected.value.has(p.id)))
const allTicked = computed(() => visible.value.length > 0 && visible.value.every((p) => selected.value.has(p.id)))

function toggle(p: Product) {
  const next = new Set(selected.value)
  if (next.has(p.id)) next.delete(p.id)
  else next.add(p.id)
  selected.value = next
}

function toggleAll() {
  const next = new Set(selected.value)
  for (const p of visible.value) {
    if (allTicked.value) next.delete(p.id)
    else next.add(p.id)
  }
  selected.value = next
}

async function load() {
  try {
    ;[products.value, categories.value] = await Promise.all([
      api.get<Product[]>('/products', { limit: 5000 }),
      api.get<Category[]>('/categories'),
    ])
  } catch (e) {
    ui.error(e)
  }
}

// scanning a product ticks it
useBarcodeScanner(
  (code) => {
    const product = findByCode(active.value, code)
    if (!product) {
      beep('error')
      return ui.toast(t('No product with barcode {code}', { code }), 'error')
    }
    beep('ok')
    selected.value = new Set(selected.value).add(product.id)
    ui.toast(t('{name} added', { name: product.name }), 'success')
  },
  () => !labelsFor.value,
)

onMounted(load)
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
      <button class="btn-outline" :disabled="!selected.size" @click="selected = new Set()">{{ t('Clear') }}</button>
      <button class="btn-primary" :disabled="!chosen.length" @click="labelsFor = chosen">
        <Barcode :size="17" /><QrCode :size="17" /> {{ chosen.length ? t('Print {n} product(s)', { n: chosen.length }) : t('Print labels') }}
      </button>
    </div>
    <p class="flex items-center gap-2 px-1 text-sm text-muted">
      <ScanLine :size="16" class="shrink-0" /> {{ t('Tick products or scan them, then print barcode or QR labels.') }}
    </p>

    <div class="card overflow-x-auto">
      <table class="table min-w-[720px]">
        <thead>
          <tr>
            <th class="w-10"><input type="checkbox" class="size-4 accent-primary" :checked="allTicked" :aria-label="t('Select all')" @change="toggleAll" /></th>
            <th>{{ t('Product') }}</th><th>{{ t('Category') }}</th><th>{{ t('Barcode') }}</th><th class="text-right">{{ t('Price') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in visible" :key="p.id" class="cursor-pointer" @click="toggle(p)">
            <td><input type="checkbox" class="size-4 accent-primary" :checked="selected.has(p.id)" @click.stop="toggle(p)" /></td>
            <td>
              <div class="flex items-center gap-3">
                <ProductArt :category="p.category_name" :image="p.image_url" :alt="p.name" :size="18" class="size-10 shrink-0 rounded-xl" />
                <p class="font-semibold">{{ p.name }}</p>
              </div>
            </td>
            <td class="text-muted">{{ p.category_name ?? '—' }}</td>
            <td class="font-mono text-xs">
              <span v-if="labelCode(p)" class="text-muted">{{ labelCode(p) }}</span>
              <span v-else class="pill bg-warn-soft text-warn">{{ t('No barcode') }}</span>
            </td>
            <td class="text-right font-semibold">{{ usd(p.price) }}</td>
          </tr>
          <tr v-if="!visible.length">
            <td colspan="5" class="py-10 text-center text-muted">{{ t('No products found') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <LabelModal v-if="labelsFor" :products="labelsFor" @close="labelsFor = null" @saved="load" />
  </div>
</template>
