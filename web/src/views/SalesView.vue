<script setup lang="ts">
import { ChevronLeft, ChevronRight, ReceiptText, RotateCcw, Search } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Sale, SaleSummary } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import ReceiptModal from '@/components/sell/ReceiptModal.vue'
import { addDays, dateTime, isoDate, khr, time, usd } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const auth = useAuth()
const shift = useShift()
const ui = useUi()

const day = ref(isoDate(new Date()))
const query = ref('')
const sales = ref<SaleSummary[]>([])
const selected = ref<Sale | null>(null)
const showReceipt = ref(false)
const refunding = ref(false)
const refundQty = ref<Record<number, number>>({})
const refundReason = ref('')
const loading = ref(false)

const isToday = computed(() => day.value === isoDate(new Date()))
const filtered = computed(() => sales.value.filter((s) => !query.value || s.receipt_no.includes(query.value.trim())))
const dayTotal = computed(() => filtered.value.reduce((sum, s) => sum + s.total - s.refunded_total, 0))
const statusClass = { completed: 'bg-ok-soft text-ok', partially_refunded: 'bg-warn-soft text-warn', refunded: 'bg-rose-50 text-price' }

async function load() {
  loading.value = true
  try {
    sales.value = await api.get<SaleSummary[]>('/sales', { date_from: day.value, date_to: day.value, limit: 1000 })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

async function open(id: number) {
  try {
    selected.value = await api.get<Sale>(`/sales/${id}`)
  } catch (e) {
    ui.error(e)
  }
}

function moveDay(days: number) {
  day.value = isoDate(addDays(new Date(`${day.value}T12:00:00`), days))
}

function startRefund() {
  if (!selected.value) return
  refundQty.value = Object.fromEntries(selected.value.items.map((i) => [i.id, i.qty - i.refunded_qty]))
  refundReason.value = ''
  refunding.value = true
}

async function refund() {
  const sale = selected.value
  if (!sale) return
  const items = Object.entries(refundQty.value)
    .filter(([, qty]) => qty > 0)
    .map(([id, qty]) => ({ sale_item_id: Number(id), qty }))
  if (!items.length || !refundReason.value.trim()) {
    ui.toast('Choose at least one item and enter a reason', 'error')
    return
  }
  const pin = auth.isManager ? null : await ui.managerPin('Approve refund')
  if (!auth.isManager && !pin) return
  try {
    const result = await api.post<{ amount: number; sale: Sale }>(`/sales/${sale.id}/refund`, { items, reason: refundReason.value.trim(), manager_pin: pin })
    selected.value = result.sale
    refunding.value = false
    ui.toast(t('Refunded {amount}. Give this amount back to the customer.', { amount: usd(result.amount) }), 'success')
    load()
    shift.refresh().catch(() => {})
  } catch (e) {
    ui.error(e)
  }
}

watch(day, () => {
  selected.value = null
  load()
})
onMounted(load)
</script>

<template>
  <div class="flex h-full flex-col lg:flex-row">
    <!-- list -->
    <section :class="['flex min-h-0 flex-col border-line bg-white lg:w-[440px] lg:border-r', selected ? 'hidden lg:flex' : 'flex flex-1 lg:flex-none']">
      <div class="space-y-3 border-b border-line p-4">
        <div class="flex items-center gap-2">
          <button class="btn-outline p-2.5" :title="t('Previous day')" @click="moveDay(-1)"><ChevronLeft :size="18" /></button>
          <input v-model="day" type="date" class="input text-center" :max="isoDate(new Date())" />
          <button class="btn-outline p-2.5" :title="t('Next day')" :disabled="isToday" @click="moveDay(1)"><ChevronRight :size="18" /></button>
        </div>
        <div class="relative">
          <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
          <input v-model="query" class="input pl-10" :placeholder="t('Receipt number')" />
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-muted">{{ filtered.length }} sale(s){{ auth.isManager ? '' : ' by you' }}</span>
          <span class="font-bold">{{ usd(dayTotal) }}</span>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto">
        <p v-if="loading" class="p-8 text-center text-muted">{{ t('Loading...') }}</p>
        <p v-else-if="!filtered.length" class="p-8 text-center text-muted">{{ t('No sales on this day') }}</p>
        <button
          v-for="s in filtered"
          :key="s.id"
          :class="['flex w-full items-center gap-3 border-b border-line px-4 py-3 text-left hover:bg-page', selected?.id === s.id && 'bg-primary-soft']"
          @click="open(s.id)"
        >
          <span class="flex-1">
            <span class="block font-semibold">{{ s.receipt_no }}</span>
            <span class="text-sm text-muted">{{ time(s.created_at) }} · {{ s.cashier_name }}{{ s.customer_name ? ` · ${s.customer_name}` : '' }}</span>
          </span>
          <span class="text-right">
            <span class="block font-bold">{{ usd(s.total) }}</span>
            <span v-if="s.status !== 'completed'" :class="['pill mt-1', statusClass[s.status]]">{{ t(s.status.replace('_', ' ')) }}</span>
          </span>
        </button>
      </div>
    </section>

    <!-- details -->
    <section :class="['min-h-0 flex-1 overflow-y-auto p-4 lg:p-6', selected ? 'block' : 'hidden lg:block']">
      <div v-if="!selected" class="flex h-full flex-col items-center justify-center text-muted">
        <ReceiptText :size="44" class="mb-2 text-line" />
        {{ t('Select a sale to see its details') }}
      </div>
      <div v-else class="mx-auto max-w-2xl space-y-4">
        <button class="btn-ghost -ml-3 lg:hidden" @click="selected = null"><ChevronLeft :size="18" /> {{ t('All sales') }}</button>
        <div class="card p-5">
          <div class="flex flex-wrap items-start gap-3">
            <div class="flex-1">
              <h2 class="text-xl font-extrabold">{{ selected.receipt_no }}</h2>
              <p class="text-muted">{{ dateTime(selected.created_at) }} · {{ selected.cashier_name }}{{ selected.customer_name ? ` · ${selected.customer_name}` : '' }}</p>
            </div>
            <span :class="['pill', statusClass[selected.status]]">{{ t(selected.status.replace('_', ' ')) }}</span>
          </div>
        </div>
        <div class="card overflow-x-auto">
          <table class="table">
            <thead>
              <tr><th>{{ t('Item') }}</th><th class="text-right">{{ t('Qty') }}</th><th class="text-right">{{ t('Price') }}</th><th class="text-right">{{ t('Total') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="i in selected.items" :key="i.id">
                <td>
                  <p class="font-semibold">{{ i.product_name }}</p>
                  <p v-if="i.discount" class="text-xs text-price">discount -{{ usd(i.discount) }}</p>
                  <p v-if="i.refunded_qty" class="text-xs text-warn">{{ i.refunded_qty }} refunded</p>
                </td>
                <td class="text-right">{{ i.qty }}</td>
                <td class="text-right">{{ usd(i.unit_price) }}</td>
                <td class="text-right font-semibold">{{ usd(i.line_total) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="card space-y-1.5 p-5">
          <div class="flex justify-between"><span class="text-muted">{{ t('Subtotal') }}</span><span>{{ usd(selected.subtotal) }}</span></div>
          <div v-if="selected.discount_total" class="flex justify-between text-price"><span>{{ t('Discount') }}</span><span>-{{ usd(selected.discount_total) }}</span></div>
          <div v-if="selected.tax_total" class="flex justify-between"><span class="text-muted">{{ t('VAT') }}</span><span>{{ usd(selected.tax_total) }}</span></div>
          <div class="flex justify-between border-t border-line pt-2 text-lg font-extrabold"><span>{{ t('Total') }}</span><span>{{ usd(selected.total) }}</span></div>
          <div v-for="(p, n) in selected.payments" :key="n" class="flex justify-between text-sm">
            <span class="text-muted uppercase">{{ p.method }} {{ p.currency }}</span>
            <span>{{ p.currency === 'USD' ? usd(p.amount) : khr(p.amount) }}</span>
          </div>
          <div v-if="selected.change_due" class="flex justify-between text-sm"><span class="text-muted">{{ t('Change') }}</span><span>{{ usd(selected.change_due) }}</span></div>
          <div v-if="selected.refunded_total" class="flex justify-between font-semibold text-price"><span>{{ t('Refunded') }}</span><span>-{{ usd(selected.refunded_total) }}</span></div>
        </div>
        <div class="flex gap-2">
          <button class="btn-outline flex-1" @click="showReceipt = true"><ReceiptText :size="18" /> {{ t('Receipt / reprint') }}</button>
          <button class="btn-danger flex-1" :disabled="selected.items.every((i) => i.qty === i.refunded_qty)" @click="startRefund">
            <RotateCcw :size="18" /> {{ t('Refund') }}
          </button>
        </div>
      </div>
    </section>

    <ReceiptModal v-if="showReceipt && selected" :sale="selected" @close="showReceipt = false" />

    <AppModal v-if="refunding && selected" :title="t('Refund {receipt}', { receipt: selected.receipt_no })" @close="refunding = false">
      <p class="mb-3 text-muted">{{ t('Set how many of each item the customer brings back.') }}</p>
      <div class="divide-y divide-line rounded-xl border border-line">
        <div v-for="i in selected.items.filter((x) => x.qty > x.refunded_qty)" :key="i.id" class="flex items-center gap-3 px-4 py-3">
          <span class="flex-1 font-semibold">{{ i.product_name }}</span>
          <span class="text-sm text-muted">max {{ i.qty - i.refunded_qty }}</span>
          <input v-model.number="refundQty[i.id]" type="number" min="0" :max="i.qty - i.refunded_qty" class="input w-20 text-center" />
        </div>
      </div>
      <label class="label mt-4">{{ t('Reason') }}</label>
      <input v-model="refundReason" class="input" :placeholder="t('e.g. Damaged, expired, wrong item')" />
      <template #footer>
        <button class="btn-outline" @click="refunding = false">{{ t('Cancel') }}</button>
        <button class="btn bg-price text-white hover:bg-rose-700" @click="refund"><RotateCcw :size="18" /> {{ t('Refund') }}</button>
      </template>
    </AppModal>
  </div>
</template>
