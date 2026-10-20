<script setup lang="ts">
import { ImagePlus, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, onBeforeUnmount, reactive, ref } from 'vue'

import { api } from '@/api/client'
import type { Category, Product, ProductInput } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import ProductArt from '@/components/ProductArt.vue'
import { newStoreBarcode } from '@/lib/barcode'
import { parseHundredths, parseWhole, toDollars } from '@/lib/money'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

/** `barcode` fills in a new product's barcode (e.g. one just scanned at the till). */
const props = defineProps<{ product: Product | null; categories: Category[]; barcode?: string }>()
const emit = defineEmits<{ close: []; saved: []; categoryAdded: [] }>()
const ui = useUi()

const p = props.product
const form = reactive({
  name: p?.name ?? '',
  barcode: p?.barcode ?? props.barcode ?? '',
  sku: p?.sku ?? '',
  category_id: (p?.category_id ?? '') as number | '',
  price: p ? toDollars(p.price) : '',
  cost: p ? toDollars(p.cost) : '',
  track_stock: p?.track_stock ?? true,
  low_stock_threshold: String(p?.low_stock_threshold ?? 5),
  stock_qty: '0',
  is_active: p?.is_active ?? true,
})
const categories = ref([...props.categories])
const busy = ref(false)

// photo: chosen here, uploaded when the product is saved
const MAX_PHOTO_BYTES = 8 * 1024 * 1024
const photoInput = ref<HTMLInputElement>()
const newPhoto = ref<File | null>(null)
const newPhotoUrl = ref<string | null>(null)
const removePhoto = ref(false)
const dragging = ref(false)
const shownPhoto = computed(() => newPhotoUrl.value ?? (removePhoto.value ? null : (p?.image_url ?? null)))
const categoryName = computed(() => categories.value.find((c) => c.id === form.category_id)?.name ?? null)

function choosePhoto(file: File | undefined) {
  if (!file) return
  if (!file.type.startsWith('image/')) return ui.toast('Choose a photo (JPG, PNG or WebP)', 'error')
  if (file.size > MAX_PHOTO_BYTES) return ui.toast('Photo is too large (max 8 MB)', 'error')
  if (newPhotoUrl.value) URL.revokeObjectURL(newPhotoUrl.value)
  newPhoto.value = file
  newPhotoUrl.value = URL.createObjectURL(file)
  removePhoto.value = false
}

function clearPhoto() {
  if (newPhotoUrl.value) URL.revokeObjectURL(newPhotoUrl.value)
  newPhoto.value = null
  newPhotoUrl.value = null
  removePhoto.value = true
  if (photoInput.value) photoInput.value.value = ''
}

function onDrop(e: DragEvent) {
  dragging.value = false
  choosePhoto(e.dataTransfer?.files[0])
}

onBeforeUnmount(() => newPhotoUrl.value && URL.revokeObjectURL(newPhotoUrl.value))

async function addCategory() {
  const name = await ui.prompt({ title: 'New category', label: 'Category name' })
  if (!name?.trim()) return
  try {
    const category = await api.post<Category>('/categories', { name: name.trim(), sort_order: categories.value.length })
    categories.value.push(category)
    form.category_id = category.id
    emit('categoryAdded')
  } catch (e) {
    ui.error(e)
  }
}

async function save() {
  const price = parseHundredths(form.price)
  if (!form.name.trim() || price === null) return ui.toast('Enter a name and a price like 1.50', 'error')
  const body: ProductInput = {
    name: form.name.trim(),
    barcode: form.barcode.trim() || null,
    sku: form.sku.trim() || null,
    category_id: form.category_id === '' ? null : form.category_id,
    price,
    cost: parseHundredths(form.cost) ?? 0,
    track_stock: form.track_stock,
    low_stock_threshold: parseWhole(form.low_stock_threshold) ?? 5,
    is_active: form.is_active,
  }
  busy.value = true
  try {
    const saved = p ? await api.put<Product>(`/products/${p.id}`, body) : await api.post<Product>('/products', { ...body, stock_qty: parseWhole(form.stock_qty) ?? 0 })
    if (newPhoto.value) await api.upload(`/products/${saved.id}/image`, newPhoto.value)
    else if (removePhoto.value && p?.image_url) await api.delete(`/products/${saved.id}/image`)
    ui.toast(p ? 'Product saved' : 'Product added', 'success')
    emit('saved')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="p ? `Edit ${p.name}` : 'New product'" @close="emit('close')">
    <form id="product-form" class="grid grid-cols-2 gap-x-3 gap-y-3" @submit.prevent="save">
      <div class="col-span-2 flex items-center gap-4">
        <button
          type="button"
          :class="['relative size-28 shrink-0 overflow-hidden rounded-2xl border-2 border-dashed transition', dragging ? 'border-primary' : 'border-transparent']"
          :title="t('Click or drop a photo')"
          @click="photoInput?.click()"
          @dragover.prevent="dragging = true"
          @dragleave="dragging = false"
          @drop.prevent="onDrop"
        >
          <ProductArt :category="categoryName" :image="shownPhoto" :size="36" class="size-full rounded-xl" />
          <span class="absolute inset-x-0 bottom-0 bg-slate-900/55 py-1 text-xs font-semibold text-white">{{ shownPhoto ? t('Change') : t('Add photo') }}</span>
        </button>
        <div class="min-w-0 flex-1">
          <p class="font-semibold">{{ t('Product photo') }}</p>
          <p class="mb-2 text-sm text-muted">{{ t('JPG, PNG or WebP, up to 8 MB. Click or drag a photo onto the box.') }}</p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-outline py-2" @click="photoInput?.click()"><ImagePlus :size="17" /> {{ shownPhoto ? t('Replace') : t('Upload photo') }}</button>
            <button v-if="shownPhoto" type="button" class="btn-danger py-2" @click="clearPhoto"><Trash2 :size="17" /> {{ t('Remove') }}</button>
          </div>
        </div>
        <input ref="photoInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="choosePhoto(($event.target as HTMLInputElement).files?.[0])" />
      </div>
      <div class="col-span-2">
        <label class="label">{{ t('Name') }}</label>
        <input v-model="form.name" class="input" autofocus />
      </div>
      <div>
        <label class="label">{{ t('Barcode') }}</label>
        <div class="flex gap-1.5">
          <input v-model="form.barcode" class="input" :placeholder="t('Scan or type')" />
          <button
            v-if="!form.barcode.trim()"
            type="button"
            class="btn-outline shrink-0 px-2.5"
            :title="t('Make a new in-store barcode (EAN-13 starting with 200) for a product that has none')"
            @click="form.barcode = newStoreBarcode()"
          >
            <Sparkles :size="17" />
          </button>
        </div>
      </div>
      <div>
        <label class="label">{{ t('SKU (optional)') }}</label>
        <input v-model="form.sku" class="input" />
      </div>
      <div class="col-span-2">
        <label class="label">{{ t('Category') }}</label>
        <div class="flex gap-2">
          <select v-model="form.category_id" class="input">
            <option value="">{{ t('No category') }}</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <button type="button" class="btn-outline shrink-0" @click="addCategory"><Plus :size="17" /> {{ t('New') }}</button>
        </div>
      </div>
      <div>
        <label class="label">{{ t('Price (USD)') }}</label>
        <input v-model="form.price" class="input" inputmode="decimal" placeholder="0.00" />
      </div>
      <div>
        <label class="label">{{ t('Cost (USD)') }}</label>
        <input v-model="form.cost" class="input" inputmode="decimal" placeholder="0.00" />
      </div>
      <label class="col-span-2 flex items-center gap-2"><input v-model="form.track_stock" type="checkbox" class="size-4 accent-primary" /> {{ t('Track stock') }}</label>
      <template v-if="form.track_stock">
        <div>
          <label class="label">{{ t('Low stock warning at') }}</label>
          <input v-model="form.low_stock_threshold" class="input" inputmode="numeric" />
        </div>
        <div v-if="!p">
          <label class="label">{{ t('Opening stock') }}</label>
          <input v-model="form.stock_qty" class="input" inputmode="numeric" />
        </div>
      </template>
      <label class="col-span-2 flex items-center gap-2"><input v-model="form.is_active" type="checkbox" class="size-4 accent-primary" /> {{ t('For sale (active)') }}</label>
    </form>
    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Cancel') }}</button>
      <button class="btn-primary" type="submit" form="product-form" :disabled="busy">{{ t('Save') }}</button>
    </template>
  </AppModal>
</template>
