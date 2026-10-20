<script setup lang="ts">
import { Banknote, Check, CreditCard, QrCode, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Currency, PaymentIn, PaymentMethod, Sale } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { khr, khrToUsdCents, parseHundredths, parseWhole, usd, usdCentsToKhr } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useCart } from '@/stores/cart'
import { useUi } from '@/stores/ui'

const emit = defineEmits<{ close: []; paid: [sale: Sale] }>()
const cart = useCart()
const auth = useAuth()
const ui = useUi()

const rate = computed(() => auth.settings.exchange_rate)
const total = computed(() => cart.totals.total)
const payments = ref<PaymentIn[]>([])
const method = ref<PaymentMethod>('cash')
const currency = ref<Currency>('USD')
const amountText = ref('')
const reference = ref('')
const amountInput = ref<HTMLInputElement>()
const busy = ref(false)

const methods = [
  { value: 'cash', label: 'Cash', icon: Banknote },
  { value: 'card', label: 'Card', icon: CreditCard },
  { value: 'khqr', label: 'KHQR', icon: QrCode },
] as const

const usdOf = (p: PaymentIn) => (p.currency === 'USD' ? p.amount : khrToUsdCents(p.amount, rate.value))
const paid = computed(() => payments.value.reduce((sum, p) => sum + usdOf(p), 0))
const due = computed(() => total.value - paid.value)
// Riel cash is rounded to the 100-riel note; a card or KHQR payment in riel is exact, so it never comes to a cent
// more than is due (which would be refused).
const dueInCurrency = computed(() =>
  currency.value === 'USD' ? due.value : usdCentsToKhr(due.value, rate.value, method.value === 'cash' ? 100 : 1),
)
/** Riel cash is rounded to the 100-riel note, so less than 100 riel short is fine (same rule as the service). */
const canComplete = computed(() => payments.value.length > 0 && (due.value <= 0 || (payments.value.some((p) => p.currency === 'KHR') && due.value * rate.value < 100 * 100)))
const quickAmounts = computed(() =>
  currency.value === 'USD'
    ? [100, 500, 1000, 2000, 5000, 10000].filter((v) => v >= due.value).slice(0, 4)
    : [10000, 20000, 50000, 100000].filter((v) => v >= dueInCurrency.value).slice(0, 3),
)
const fmt = (amount: number, cur: Currency) => (cur === 'USD' ? usd(amount) : khr(amount))
const entered = () => (currency.value === 'USD' ? parseHundredths(amountText.value) : parseWhole(amountText.value))

function add(amount: number | null) {
  if (!amount || amount <= 0) return false
  const amountUsd = currency.value === 'USD' ? amount : khrToUsdCents(amount, rate.value)
  if (method.value !== 'cash' && amountUsd > due.value) {
    ui.toast('Card / QR payment cannot be more than the amount due', 'error')
    return false
  }
  payments.value.push({ method: method.value, currency: currency.value, amount, reference: method.value === 'cash' ? null : reference.value.trim() || null })
  amountText.value = ''
  reference.value = ''
  amountInput.value?.focus()
  return true
}

async function complete() {
  if (amountText.value && !add(entered())) return
  if (!canComplete.value) {
    ui.toast(t('Still {amount} to pay', { amount: usd(due.value) }), 'error')
    return
  }
  busy.value = true
  try {
    emit('paid', await api.post<Sale>('/sales', cart.saleRequest(payments.value)))
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'F12') {
    e.preventDefault()
    complete()
  }
}
onMounted(async () => {
  window.addEventListener('keydown', onKey)
  await nextTick()
  amountInput.value?.focus()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <AppModal :title="t('Payment')" width="max-w-4xl" @close="emit('close')">
    <div class="grid gap-6 md:grid-cols-2">
      <!-- left: what is owed -->
      <div class="space-y-4">
        <div class="rounded-2xl bg-primary p-6 text-center text-white">
          <p class="text-sm font-semibold tracking-widest text-white/70 uppercase">{{ t('Total') }}</p>
          <p class="text-5xl font-extrabold">{{ usd(total) }}</p>
          <p class="mt-1 text-lg font-semibold">{{ khr(usdCentsToKhr(total, rate)) }}</p>
          <p class="mt-1 text-sm text-white/70">1 USD = {{ khr(rate) }}</p>
        </div>

        <ul v-if="payments.length" class="divide-y divide-line rounded-xl border border-line">
          <li v-for="(p, i) in payments" :key="i" class="flex items-center gap-3 px-4 py-2.5">
            <component :is="methods.find((m) => m.value === p.method)!.icon" :size="18" class="text-muted" />
            <span class="flex-1 font-semibold">{{ t(methods.find((m) => m.value === p.method)!.label) }} {{ p.currency }}</span>
            <span v-if="p.reference" class="text-xs text-muted">{{ t('Ref') }} {{ p.reference }}</span>
            <span class="font-semibold">{{ fmt(p.amount, p.currency) }}</span>
            <button class="btn-ghost p-1.5" :title="t('Remove')" @click="payments.splice(i, 1)"><X :size="16" /></button>
          </li>
        </ul>

        <div class="space-y-1 px-1">
          <div class="flex justify-between"><span class="text-muted">{{ t('Paid') }}</span><span class="font-semibold">{{ usd(paid) }}</span></div>
          <template v-if="due > 0">
            <div class="flex justify-between text-lg font-bold text-price"><span>{{ t('Still due') }}</span><span>{{ usd(due) }}</span></div>
            <div class="flex justify-between text-muted"><span>{{ t('Still due (KHR)') }}</span><span>{{ khr(usdCentsToKhr(due, rate)) }}</span></div>
          </template>
          <template v-else>
            <div class="flex justify-between text-2xl font-extrabold text-ok"><span>{{ t('Change to give') }}</span><span>{{ usd(-due) }}</span></div>
            <div class="flex justify-between font-semibold text-ok"><span>{{ t('Change (KHR)') }}</span><span>{{ khr(usdCentsToKhr(-due, rate)) }}</span></div>
          </template>
        </div>
      </div>

      <!-- right: how they pay -->
      <div class="space-y-4">
        <div>
          <p class="label">{{ t('How is the customer paying?') }}</p>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="m in methods"
              :key="m.value"
              :class="['btn border py-3', method === m.value ? 'border-primary bg-primary-soft text-primary' : 'border-line bg-white']"
              @click="method = m.value"
            >
              <component :is="m.icon" :size="18" /> {{ t(m.label) }}
            </button>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-1 rounded-xl bg-page p-1">
          <button
            v-for="c in ['USD', 'KHR'] as const"
            :key="c"
            :class="['rounded-lg py-2 font-semibold', currency === c ? 'bg-white shadow-sm' : 'text-muted']"
            @click="((currency = c), (amountText = ''))"
          >
            {{ c === 'USD' ? 'USD $' : 'KHR ៛' }}
          </button>
        </div>
        <form class="flex gap-2" @submit.prevent="add(entered())">
          <input
            ref="amountInput"
            v-model="amountText"
            class="input text-xl"
            :inputmode="currency === 'USD' ? 'decimal' : 'numeric'"
            :placeholder="currency === 'USD' ? t('Amount received (USD)') : t('Amount received (riel)')"
          />
          <button class="btn-outline px-5">{{ t('Add') }}</button>
        </form>
        <input
          v-if="method !== 'cash'"
          v-model="reference"
          class="input"
          maxlength="50"
          :placeholder="method === 'card' ? t('Card approval code (optional)') : t('KHQR transaction ID (optional)')"
        />
        <div v-if="due > 0" class="flex flex-wrap gap-2">
          <button class="btn-outline border-primary text-primary" @click="add(dueInCurrency)"><Check :size="16" /> {{ t('Exact') }} {{ fmt(dueInCurrency, currency) }}</button>
          <template v-if="method === 'cash'">
            <button v-for="v in quickAmounts" :key="v" class="btn-outline" @click="add(v)">{{ fmt(v, currency) }}</button>
          </template>
        </div>
        <p v-if="!canComplete && !amountText" class="text-sm text-muted">{{ t('Add the customer\'s payment first: tap "Exact", a quick amount, or type the amount received.') }}</p>
      </div>
    </div>

    <template #footer>
      <button class="btn-outline" @click="emit('close')">{{ t('Back') }}</button>
      <button class="btn-primary min-w-56 py-3 text-lg" :disabled="busy || (!canComplete && !amountText)" @click="complete">
        <Check :size="20" /> {{ busy ? t('Saving...') : t('Complete sale (F12)') }}
      </button>
    </template>
  </AppModal>
</template>
