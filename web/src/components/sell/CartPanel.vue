<script setup lang="ts">
import { Minus, PauseCircle, Plus, ShoppingBag, Trash2, X } from 'lucide-vue-next'
import { nextTick, ref, watch } from 'vue'

import type { Customer, DiscountType, ParkedOrder } from '@/api/types'
import ProductArt from '@/components/ProductArt.vue'
import CustomerPicker from '@/components/sell/CustomerPicker.vue'
import DiscountModal from '@/components/sell/DiscountModal.vue'
import { t } from '@/lib/i18n'
import { khr, parseHundredths, parseWhole, time, toDollars, usd, usdCentsToKhr } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { type CartLine, useCart } from '@/stores/cart'
import { useUi } from '@/stores/ui'

const emit = defineEmits<{ pay: []; resume: [order: ParkedOrder] }>()
const cart = useCart()
const auth = useAuth()
const ui = useUi()

const picking = ref(false)
const discountLine = ref<CartLine | null>(null)

// order discount: "$" or "%" and a value, applied when the cashier presses Enter or leaves the field
const discountKind = ref<DiscountType>(cart.discountType ?? 'amount')
const discountText = ref(cart.discountValue ? toDollars(cart.discountValue) : '')
watch(
  () => cart.discountValue,
  (value) => {
    if (!value) discountText.value = ''
  },
)

async function applyDiscount() {
  const value = parseHundredths(discountText.value) ?? 0 // $1.50 -> 150 cents; 10% -> 1000 basis points
  if (value === cart.discountValue && (value === 0 || discountKind.value === cart.discountType)) return
  if (!(await cart.setOrderDiscount(discountKind.value, value))) discountText.value = ''
}

function setKind(kind: DiscountType) {
  discountKind.value = kind
  if (discountText.value) applyDiscount()
}

function pickCustomer(customer: Customer) {
  cart.customer = customer
  picking.value = false
}

// show the line the last tap or scan went to: scroll to it and flash it
const list = ref<HTMLElement>()
const flashing = ref<CartLine | null>(null)
watch(
  () => cart.addCount,
  async () => {
    flashing.value = null
    await nextTick()
    const row = list.value?.children[cart.lines.findIndex((l) => l === cart.lastAdded)] as HTMLElement | undefined
    void row?.offsetWidth // restarts the animation when the same line is added again
    flashing.value = cart.lastAdded
    row?.scrollIntoView({ block: 'nearest' })
  },
)

/** Tap the quantity to type it (e.g. 24 for a whole box). */
async function typeQty(line: CartLine) {
  const text = await ui.prompt({ title: line.product.name, label: t('Quantity'), initial: String(line.qty), inputmode: 'numeric' })
  const qty = parseWhole(text)
  if (qty !== null && qty > 0 && qty <= 9999) cart.setQty(line, qty)
}

function lineAmount(index: number) {
  const r = cart.totals.lines[index]
  return r ? r.gross - r.discount : 0
}
</script>

<template>
  <div class="flex min-h-0 flex-col">
    <!-- customer -->
    <div class="flex items-center gap-2 border-b border-line px-4 py-3">
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <span class="truncate font-bold">{{ cart.customer?.name ?? t('Walk-in Customer') }}</span>
        <span class="pill shrink-0 bg-page text-muted">{{ cart.customer ? t('{n} pts', { n: cart.customer.points }) : t('Walk-in') }}</span>
      </div>
      <button v-if="cart.customer" class="btn-ghost p-1.5" :title="t('Remove customer')" @click="cart.customer = null"><X :size="16" /></button>
      <button class="shrink-0 font-semibold text-primary hover:underline" @click="picking = true">
        {{ cart.customer ? t('Change') : t('Change customer') }}
      </button>
    </div>

    <!-- held orders (all tills) -->
    <div v-if="cart.held.length" class="flex gap-2 overflow-x-auto border-b border-line px-4 py-2">
      <span v-for="h in cart.held" :key="h.id" class="pill shrink-0 gap-0 bg-primary-soft p-0 text-primary">
        <button
          class="flex items-center gap-1.5 rounded-l-full py-1 pr-1 pl-2.5 hover:bg-blue-100"
          :title="t('Resume order held at {time} by {name}', { time: time(h.created_at), name: h.cashier_name })"
          @click="emit('resume', h)"
        >
          <PauseCircle :size="14" />
          {{ h.label || h.customer_name || time(h.created_at) }} · {{ usd(h.total) }}
        </button>
        <button class="rounded-r-full py-1 pr-2 pl-1 hover:bg-blue-100" :title="t('Discard held order')" @click="cart.discardHeld(h)"><X :size="13" /></button>
      </span>
    </div>

    <!-- lines -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="cart.isEmpty" class="flex h-full flex-col items-center justify-center py-16 text-muted">
        <ShoppingBag :size="44" class="mb-2 text-line" />
        {{ t('Tap a product to add') }}
      </div>
      <ul v-else ref="list" class="divide-y divide-line">
        <li v-for="(line, i) in cart.lines" :key="line.product.id + '-' + i" :class="['flex items-center gap-3 px-4 py-2.5', line === flashing && 'line-flash']">
          <ProductArt :category="line.product.category_name" :image="line.product.image_url" :size="18" class="size-10 shrink-0 rounded-xl" />
          <button class="min-w-0 flex-1 text-left" :title="t('Tap for a discount on this item')" @click="discountLine = line">
            <p class="truncate font-semibold">{{ line.product.name }}</p>
            <p :class="['text-xs', line.discountType ? 'text-price' : 'text-muted']">
              {{ usd(line.product.price) }}
              <template v-if="cart.totals.lines[i]?.discount"> · {{ t('discount') }} -{{ usd(cart.totals.lines[i]!.discount) }}</template>
            </p>
          </button>
          <div class="flex items-center rounded-xl border border-line">
            <button class="p-1.5 hover:bg-page" :title="line.qty === 1 ? t('Remove') : t('Less')" @click="line.qty === 1 ? cart.remove(line) : cart.setQty(line, line.qty - 1)">
              <Trash2 v-if="line.qty === 1" :size="15" />
              <Minus v-else :size="15" />
            </button>
            <button class="min-w-7 rounded px-1 text-center font-bold hover:bg-page" :title="t('Type the quantity')" @click="typeQty(line)">{{ line.qty }}</button>
            <button class="p-1.5 hover:bg-page" :title="t('More')" @click="cart.setQty(line, line.qty + 1)"><Plus :size="15" /></button>
          </div>
          <span class="w-[72px] text-right font-bold">{{ usd(lineAmount(i)) }}</span>
        </li>
      </ul>
    </div>

    <!-- totals -->
    <div class="space-y-1.5 border-t border-line bg-slate-50/60 px-4 py-4">
      <div class="flex items-center gap-2">
        <span class="flex-1 text-muted">{{ t('Discount') }}</span>
        <div class="flex rounded-lg bg-page p-0.5">
          <button
            v-for="k in ['amount', 'percent'] as const"
            :key="k"
            :class="['size-8 rounded-md font-bold', discountKind === k ? 'bg-primary text-white' : 'text-muted']"
            :disabled="cart.isEmpty"
            @click="setKind(k)"
          >
            {{ k === 'amount' ? '$' : '%' }}
          </button>
        </div>
        <input
          v-model="discountText"
          class="w-28 rounded-lg bg-page px-3 py-1.5 text-right outline-none focus:ring-2 focus:ring-primary/30"
          inputmode="decimal"
          placeholder="0.00"
          :disabled="cart.isEmpty"
          @keydown.enter="applyDiscount"
          @blur="applyDiscount"
        />
      </div>
      <div class="flex justify-between"><span class="text-muted">{{ t('Subtotal') }}</span><span class="font-semibold">{{ usd(cart.totals.subtotal) }}</span></div>
      <div v-if="cart.totals.discountTotal" class="flex justify-between text-price">
        <span>{{ t('Discount') }}</span><span class="font-semibold">-{{ usd(cart.totals.discountTotal) }}</span>
      </div>
      <div v-if="cart.totals.taxTotal" class="flex justify-between">
        <span class="text-muted">{{ t('VAT') }} {{ auth.settings.tax_rate_bp / 100 }}%</span><span class="font-semibold">{{ usd(cart.totals.taxTotal) }}</span>
      </div>
      <div class="!mt-3 flex items-start justify-between border-t border-line pt-3">
        <span class="mt-1.5 font-bold">{{ t('Grand Total') }}</span>
        <div class="text-right">
          <p class="text-3xl font-extrabold">{{ usd(cart.totals.total) }}</p>
          <p class="font-semibold text-primary">{{ khr(usdCentsToKhr(cart.totals.total, auth.settings.exchange_rate)) }}</p>
        </div>
      </div>
      <div class="!mt-4 grid grid-cols-[1fr_auto_2fr] gap-2">
        <button class="btn-outline text-muted" :disabled="cart.isEmpty" @click="cart.clear()">{{ t('Clear') }}</button>
        <button class="btn-outline px-3" :disabled="cart.isEmpty" :title="t('Hold this sale and serve another customer')" @click="cart.hold()">
          <PauseCircle :size="18" />
        </button>
        <button class="btn-primary py-3 text-lg" :disabled="cart.isEmpty" @click="emit('pay')">{{ t('Pay') }} · {{ usd(cart.totals.total) }}</button>
      </div>
    </div>

    <CustomerPicker v-if="picking" @close="picking = false" @pick="pickCustomer" />
    <DiscountModal
      v-if="discountLine"
      :title="t('Discount: {name}', { name: discountLine.product.name })"
      :type="discountLine.discountType"
      :value="discountLine.discountValue"
      @close="discountLine = null"
      @apply="(type, value) => cart.setLineDiscount(discountLine!, type, value).then(() => (discountLine = null))"
    />
  </div>
</template>
