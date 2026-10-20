<script setup lang="ts">
import { Barcode, Download, Pencil, Plus, Search, Upload } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { Category, ImportResult, Product } from '@/api/types'
import LabelModal from '@/components/LabelModal.vue'
import ProductArt from '@/components/ProductArt.vue'
import ProductForm from '@/components/ProductForm.vue'
import { saveBlob } from '@/lib/download'
import { t } from '@/lib/i18n'
import { isoDate, usd } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const route = useRoute()
const router = useRouter()
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const query = ref('')
const categoryId = ref<number | ''>('')
const showInactive = ref(false)
const editing = ref<Product | 'new' | null>(null)
const newBarcode = ref('')
/** Products whose barcode / QR labels are being printed. */
const labelsFor = ref<Product[] | null>(null)
const fileInput = ref<HTMLInputElement>()

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
    ;[products.value, categories.value] = await Promise.all([
      api.get<Product[]>('/products', { include_inactive: true, limit: 5000 }),
      api.get<Category[]>('/categories'),
    ])
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
              <component
                :is="auth.can('inventory') ? 'RouterLink' : 'span'"
                v-else
                :to="{ path: '/inventory', query: { q: p.name } }"
                :title="auth.can('inventory') ? t('Open in inventory') : undefined"
                :class="['pill', p.stock_qty <= 0 ? 'bg-rose-50 text-price' : p.stock_qty <= p.low_stock_threshold ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok']">
                {{ p.stock_qty }}
              </component>
            </td>
            <td class="text-right whitespace-nowrap">
              <button class="btn-ghost p-2" :title="t('Edit')" @click="editing = p"><Pencil :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Barcode / QR label')" @click="labelsFor = [p]"><Barcode :size="17" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ProductForm v-if="editing" :key="editing === 'new' ? 'new' : editing.id" :product="editing === 'new' ? null : editing" :barcode="newBarcode" :categories="categories" @close="((editing = null), (newBarcode = ''))" @saved="saved" @category-added="load" />
    <LabelModal v-if="labelsFor" :products="labelsFor" @close="labelsFor = null" @saved="load" />
  </div>
</template>
