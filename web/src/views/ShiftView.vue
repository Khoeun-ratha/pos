<script setup lang="ts">
import { LockKeyhole, LockKeyholeOpen, Minus, Plus, Printer } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { ParkedOrder, ShiftReport } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { dateTime, parseHundredths, parseWhole, usd } from '@/lib/money'
import { printReceipt } from '@/lib/print'
import { useAuth } from '@/stores/auth'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const auth = useAuth()
const shift = useShift()
const ui = useUi()

const openingCash = ref('0')
const history = ref<ShiftReport[]>([])
const closing = ref(false)
const countedUsd = ref('')
const countedKhr = ref('')
const closed = ref<ShiftReport | null>(null)

function rows(r: ShiftReport): [string, string, string?][] {
  const list: [string, string, string?][] = [
    ['Sales', String(r.sales_count)],
    ['Opening cash', usd(r.opening_cash)],
    ['Cash sales', usd(r.cash_sales)],
    ['Cash in', usd(r.cash_in)],
    ['Cash out', `-${usd(r.cash_out)}`],
    ['Cash refunds', `-${usd(r.cash_refunds)}`],
    ['Expected in drawer', usd(r.expected_cash), 'font-bold'],
  ]
  if (r.counted_cash !== null) list.push(['Counted', usd(r.counted_cash), 'font-bold'])
  if (r.variance !== null) {
    list.push([r.variance === 0 ? 'Balanced' : r.variance > 0 ? 'Over' : 'Short', usd(Math.abs(r.variance)), r.variance === 0 ? 'font-bold text-ok' : 'font-bold text-price'])
  }
  list.push(['Card sales', usd(r.card_sales)], ['KHQR sales', usd(r.khqr_sales)])
  return list
}

function reportText(r: ShiftReport) {
  const lines = [auth.settings.store_name, 'SHIFT REPORT', r.cashier_name, `Opened ${dateTime(r.opened_at)}`]
  if (r.closed_at) lines.push(`Closed ${dateTime(r.closed_at)}`)
  lines.push('-'.repeat(42), ...rows(r).map(([label, value]) => label.padEnd(26) + value.padStart(16)))
  return lines.join('\n')
}

async function loadHistory() {
  if (auth.isManager) history.value = await api.get<ShiftReport[]>('/shifts', { limit: 30 })
}

async function run(action: () => Promise<unknown>) {
  try {
    await action()
    await Promise.all([shift.refresh(), loadHistory()])
  } catch (e) {
    ui.error(e)
  }
}

function open() {
  const cents = parseHundredths(openingCash.value)
  if (cents === null) return ui.toast('Enter the opening cash, e.g. 20.00', 'error')
  run(() => api.post('/shifts/open', { opening_cash: cents }))
}

async function cashMovement(cashIn: boolean) {
  const amount = parseHundredths(await ui.prompt({ title: cashIn ? 'Cash in' : 'Cash out', label: 'Amount (USD)', inputmode: 'decimal' }))
  if (!amount) return
  const reason = await ui.prompt({ title: 'Reason', label: 'Reason', placeholder: cashIn ? 'e.g. Add small change' : 'e.g. Buy ice' })
  if (!reason?.trim()) return
  run(() => api.post('/shifts/current/cash', { amount: cashIn ? amount : -amount, reason: reason.trim() }))
}

/** Held orders are unfinished sales: warn before the drawer is closed with some still waiting. */
async function startClose() {
  const mine = (await api.get<ParkedOrder[]>('/parked').catch(() => [])).filter((o) => o.user_id === auth.user?.id)
  if (mine.length && !(await ui.confirm('Held orders', t('You still have {n} held order(s). Finish or discard them before closing. Close the shift anyway?', { n: mine.length }), 'Close shift'))) return
  countedUsd.value = ''
  countedKhr.value = ''
  closing.value = true
}

function close() {
  run(async () => {
    closed.value = await api.post<ShiftReport>('/shifts/current/close', {
      counted_usd: parseHundredths(countedUsd.value) ?? 0,
      counted_khr: parseWhole(countedKhr.value) ?? 0,
    })
    closing.value = false
  })
}

onMounted(() => run(async () => {}))
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-5 p-4 lg:grid-cols-[minmax(0,420px)_1fr] lg:p-6">
    <div class="space-y-4">
      <div v-if="shift.loaded && !shift.current" class="card p-6">
        <div class="mb-4 flex items-center gap-3">
          <div class="flex size-11 items-center justify-center rounded-xl bg-warn-soft text-warn"><LockKeyhole :size="22" /></div>
          <div>
            <h2 class="text-lg font-bold">{{ t('No open shift') }}</h2>
            <p class="text-sm text-muted">{{ t('Count the cash in the drawer to start.') }}</p>
          </div>
        </div>
        <label class="label">{{ t('Opening cash (USD)') }}</label>
        <input v-model="openingCash" class="input mb-4 text-lg" inputmode="decimal" @keydown.enter="open" />
        <button class="btn-primary w-full py-3" @click="open">{{ t('Open shift') }}</button>
      </div>

      <div v-if="shift.current" class="card p-6">
        <div class="mb-4 flex items-center gap-3">
          <div class="flex size-11 items-center justify-center rounded-xl bg-ok-soft text-ok"><LockKeyholeOpen :size="22" /></div>
          <div>
            <h2 class="text-lg font-bold">{{ t('Shift open') }}</h2>
            <p class="text-sm text-muted">{{ shift.current.cashier_name }} · since {{ dateTime(shift.current.opened_at) }}</p>
          </div>
        </div>
        <dl class="space-y-1.5">
          <div v-for="[label, value, cls] in rows(shift.current)" :key="label" :class="['flex justify-between', cls]">
            <dt :class="cls ? '' : 'text-muted'">{{ t(label) }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <div class="mt-5 grid grid-cols-2 gap-2">
          <button class="btn-outline" @click="cashMovement(true)"><Plus :size="17" /> {{ t('Cash in') }}</button>
          <button class="btn-outline" @click="cashMovement(false)"><Minus :size="17" /> {{ t('Cash out') }}</button>
        </div>
        <button class="btn-primary mt-2 w-full py-3" @click="startClose">{{ t('Close shift') }}</button>
      </div>
    </div>

    <div v-if="auth.isManager" class="card min-w-0 overflow-x-auto">
      <h2 class="border-b border-line px-5 py-4 font-bold">{{ t('Recent shifts (all cashiers)') }}</h2>
      <table class="table">
        <thead>
          <tr><th>{{ t('Cashier') }}</th><th>{{ t('Opened') }}</th><th class="text-right">{{ t('Sales') }}</th><th class="text-right">{{ t('Expected') }}</th><th class="text-right">{{ t('Counted') }}</th><th class="text-right">{{ t('Over / short') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in history" :key="s.id">
            <td class="font-semibold">{{ s.cashier_name }}</td>
            <td class="whitespace-nowrap text-muted">{{ dateTime(s.opened_at) }}</td>
            <td class="text-right">{{ s.sales_count }}</td>
            <td class="text-right">{{ usd(s.expected_cash) }}</td>
            <td class="text-right">{{ s.counted_cash === null ? '—' : usd(s.counted_cash) }}</td>
            <td :class="['text-right font-semibold', s.variance ? 'text-price' : 'text-ok']">
              {{ s.is_open ? 'open' : s.variance === null ? '—' : s.variance === 0 ? 'balanced' : (s.variance > 0 ? '+' : '-') + usd(Math.abs(s.variance)) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="closing" :title="t('Count the drawer')" width="max-w-sm" @close="closing = false">
      <form id="close-form" class="space-y-3" @submit.prevent="close">
        <div>
          <label class="label">{{ t('US dollars counted') }}</label>
          <input v-model="countedUsd" class="input text-lg" inputmode="decimal" placeholder="0.00" autofocus />
        </div>
        <div>
          <label class="label">{{ t('Riel counted') }}</label>
          <input v-model="countedKhr" class="input text-lg" inputmode="numeric" placeholder="0" />
        </div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="closing = false">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="close-form">{{ t('Close shift') }}</button>
      </template>
    </AppModal>

    <AppModal v-if="closed" :title="t('Shift closed')" width="max-w-sm" @close="closed = null">
      <dl class="space-y-1.5">
        <div v-for="[label, value, cls] in rows(closed)" :key="label" :class="['flex justify-between', cls]">
          <dt :class="cls ? '' : 'text-muted'">{{ t(label) }}</dt>
          <dd>{{ value }}</dd>
        </div>
      </dl>
      <template #footer>
        <button class="btn-outline" @click="printReceipt(reportText(closed!), 'Shift report', auth.settings.logo_url)"><Printer :size="17" /> {{ t('Print') }}</button>
        <button class="btn-primary" @click="closed = null">{{ t('Done') }}</button>
      </template>
    </AppModal>
  </div>
</template>
