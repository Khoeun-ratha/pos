<script setup lang="ts">
import { ArrowRightLeft, LockKeyhole, LockKeyholeOpen, Minus, Plus, Printer } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { ParkedOrder, ShiftHandover, ShiftReport, Staff } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { dateTime, day, khr, khrToUsdCents, parseHundredths, parseWhole, time, usd } from '@/lib/money'
import { printReceipt } from '@/lib/print'
import { useAuth } from '@/stores/auth'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const auth = useAuth()
const shift = useShift()
const ui = useUi()
const router = useRouter()

const openingCash = ref('0')
const openingKhr = ref('')
const history = ref<ShiftReport[]>([])
/** Counting the drawer: to close my shift, to hand it to the next cashier, or (manager) to close someone's shift. */
const closing = ref<{ mode: 'close' | 'handover' } | { mode: 'other'; shift: ShiftReport } | null>(null)
const countedUsd = ref('')
const countedKhr = ref('')
const closed = ref<ShiftReport | null>(null)
/** Set after a handover: who takes over (shown with the closed shift). */
const handedTo = ref<ShiftReport | null>(null)
const staff = ref<Staff[]>([])
const nextUserId = ref<number | ''>('')
const nextPin = ref('')
const busy = ref(false)

/** The drawer holds dollars and riel; the service keeps one amount in cents, at today's rate (as when closing). */
const cents = (usdText: string, khrText: string) => {
  const dollars = usdText.trim() ? parseHundredths(usdText) : 0
  const riel = khrText.trim() ? parseWhole(khrText) : 0
  return dollars === null || riel === null ? null : dollars + khrToUsdCents(riel, auth.settings.exchange_rate)
}
const countedTotal = computed(() => cents(countedUsd.value, countedKhr.value))

const seesAll = computed(() => auth.can('reports') || auth.can('all_sales'))
const others = computed(() => staff.value.filter((s) => s.id !== auth.user?.id))

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
    list.push([r.variance === 0 ? 'Balanced' : r.variance > 0 ? 'Over' : 'Short', usd(Math.abs(r.variance)), r.variance === 0 ? 'font-bold text-ok' : r.variance > 0 ? 'font-bold text-warn' : 'font-bold text-price'])
  }
  list.push(['Card sales', usd(r.card_sales)], ['KHQR sales', usd(r.khqr_sales)])
  if (r.handed_from_name) list.unshift(['Taken over from', r.handed_from_name])
  if (r.handed_to_name) list.push(['Handed over to', r.handed_to_name])
  return list
}

function reportText(r: ShiftReport) {
  const lines = [auth.settings.store_name, 'SHIFT REPORT', r.cashier_name, `Opened ${dateTime(r.opened_at)}`]
  if (r.closed_at) lines.push(`Closed ${dateTime(r.closed_at)}`)
  lines.push('-'.repeat(42), ...rows(r).map(([label, value]) => label.padEnd(26) + value.padStart(16)))
  if (r.note) lines.push('', r.note)
  return lines.join('\n')
}

/** Managers see every cashier's shifts; a cashier sees their own (the service decides). */
async function loadHistory() {
  history.value = await api.get<ShiftReport[]>('/shifts', { limit: 30 })
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
  const opening = cents(openingCash.value, openingKhr.value)
  if (opening === null) return ui.toast('Enter the opening cash, e.g. 20.00', 'error')
  run(() => api.post('/shifts/open', { opening_cash: opening }))
}

async function cashMovement(cashIn: boolean) {
  const amount = parseHundredths(await ui.prompt({ title: cashIn ? 'Cash in' : 'Cash out', label: 'Amount (USD)', inputmode: 'decimal' }))
  if (!amount) return
  const reason = await ui.prompt({ title: 'Reason', label: 'Reason', placeholder: cashIn ? 'e.g. Add small change' : 'e.g. Buy ice' })
  if (!reason?.trim()) return
  run(() => api.post('/shifts/current/cash', { amount: cashIn ? amount : -amount, reason: reason.trim() }))
}

/** Held orders are unfinished sales: warn before the drawer is closed with some still waiting. */
async function startClose(mode: 'close' | 'handover') {
  if (mode === 'close') {
    const mine = (await api.get<ParkedOrder[]>('/parked').catch(() => [])).filter((o) => o.user_id === auth.user?.id)
    if (mine.length && !(await ui.confirm('Held orders', t('You still have {n} held order(s). Finish or discard them before closing. Close the shift anyway?', { n: mine.length }), 'Close shift'))) return
  } else {
    staff.value = await api.get<Staff[]>('/users/staff').catch(() => [])
    nextUserId.value = ''
    nextPin.value = ''
  }
  countedUsd.value = ''
  countedKhr.value = ''
  closing.value = { mode }
}

function closeOther(s: ShiftReport) {
  countedUsd.value = ''
  countedKhr.value = ''
  closing.value = { mode: 'other', shift: s }
}

async function close() {
  const target = closing.value
  if (!target || busy.value) return
  const count = { counted_usd: parseHundredths(countedUsd.value) ?? 0, counted_khr: parseWhole(countedKhr.value) ?? 0 }
  if (target.mode === 'handover' && (nextUserId.value === '' || !nextPin.value)) {
    return ui.toast(t('Choose who takes over and let them type their PIN'), 'error')
  }
  busy.value = true
  await run(async () => {
    if (target.mode === 'handover') {
      const result = await api.post<ShiftHandover>('/shifts/current/handover', { ...count, to_user_id: nextUserId.value, pin: nextPin.value })
      closed.value = result.closed
      handedTo.value = result.opened
    } else if (target.mode === 'other') {
      closed.value = await api.post<ShiftReport>(`/shifts/${target.shift.id}/close`, count)
      handedTo.value = null
    } else {
      closed.value = await api.post<ShiftReport>('/shifts/current/close', count)
      handedTo.value = null
    }
    closing.value = null
  })
  busy.value = false
}

/** After a handover: the next cashier signs in on this till. */
function logOutForNext() {
  auth.logout()
  router.push({ name: 'login' })
}

onMounted(() => run(async () => {}))
</script>

<template>
  <div class="mx-auto grid max-w-7xl gap-5 p-4 lg:grid-cols-[minmax(0,360px)_1fr] lg:p-6">
    <div class="space-y-4">
      <div v-if="shift.loaded && !shift.current" class="card p-6">
        <div class="mb-4 flex items-center gap-3">
          <div class="flex size-11 items-center justify-center rounded-xl bg-warn-soft text-warn"><LockKeyhole :size="22" /></div>
          <div>
            <h2 class="text-lg font-bold">{{ t('No open shift') }}</h2>
            <p class="text-sm text-muted">{{ t('Count the cash in the drawer to start.') }}</p>
          </div>
        </div>
        <div class="mb-4 grid grid-cols-2 gap-3">
          <div>
            <label class="label">{{ t('Opening cash (USD)') }}</label>
            <input v-model="openingCash" class="input text-lg" inputmode="decimal" @keydown.enter="open" />
          </div>
          <div>
            <label class="label">{{ t('Riel in the drawer') }}</label>
            <input v-model="openingKhr" class="input text-lg" inputmode="numeric" placeholder="0" @keydown.enter="open" />
          </div>
        </div>
        <p v-if="openingKhr.trim() && cents(openingCash, openingKhr) !== null" class="-mt-2 mb-4 text-sm text-muted">
          {{ t('Opening cash') }}: <b class="text-ink">{{ usd(cents(openingCash, openingKhr)!) }}</b> (1 USD = {{ khr(auth.settings.exchange_rate) }})
        </p>
        <button class="btn-primary w-full py-3" @click="open">{{ t('Open shift') }}</button>
      </div>

      <div v-if="shift.current" class="card p-6">
        <div class="mb-4 flex items-center gap-3">
          <div class="flex size-11 items-center justify-center rounded-xl bg-ok-soft text-ok"><LockKeyholeOpen :size="22" /></div>
          <div>
            <h2 class="text-lg font-bold">{{ t('Shift open') }}</h2>
            <p class="text-sm text-muted">{{ shift.current.cashier_name }} · {{ t('since {time}', { time: dateTime(shift.current.opened_at) }) }}</p>
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
        <button class="btn-outline mt-2 w-full" :title="t('The next cashier keeps the drawer: no need to empty it')" @click="startClose('handover')">
          <ArrowRightLeft :size="17" /> {{ t('Hand over to next cashier') }}
        </button>
        <button class="btn-primary mt-2 w-full py-3" @click="startClose('close')">{{ t('Close shift') }}</button>
      </div>
    </div>

    <div class="@container card min-w-0 overflow-x-auto">
      <h2 class="border-b border-line px-5 py-4 font-bold">{{ seesAll ? t('Recent shifts (all cashiers)') : t('My recent shifts') }}</h2>
      <table class="table min-w-[520px] [&_td]:px-3 [&_th]:px-3">
        <thead>
          <tr>
            <th>{{ t('Cashier') }}</th><th>{{ t('Opened') }}</th><th class="hidden text-right @2xl:table-cell">{{ t('Sales') }}</th><th class="text-right">{{ t('Expected') }}</th>
            <th class="text-right">{{ t('Counted') }}</th><th class="text-right">{{ t('Over / short') }}</th><th class="text-right">{{ t('Actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in history" :key="s.id">
            <td>
              <p class="font-semibold whitespace-nowrap">{{ s.cashier_name }}</p>
              <p v-if="s.handed_to_name" class="text-xs whitespace-nowrap text-muted">→ {{ s.handed_to_name }}</p>
            </td>
            <td class="whitespace-nowrap text-muted">
              <p>{{ day(s.opened_at) }}</p>
              <p class="text-xs">{{ time(s.opened_at) }}{{ s.closed_at ? ` – ${time(s.closed_at)}` : '' }}</p>
            </td>
            <td class="hidden text-right @2xl:table-cell">{{ s.sales_count }}</td>
            <td class="text-right">{{ usd(s.expected_cash) }}</td>
            <td class="text-right">{{ s.counted_cash === null ? '—' : usd(s.counted_cash) }}</td>
            <td :class="['text-right font-semibold whitespace-nowrap', !s.variance ? 'text-ok' : s.variance < 0 ? 'text-price' : 'text-warn']">
              {{ s.is_open ? t('open') : s.variance === null ? '—' : s.variance === 0 ? t('balanced') : (s.variance > 0 ? '+' : '-') + usd(Math.abs(s.variance)) }}
            </td>
            <td class="text-right whitespace-nowrap">
              <button v-if="!s.is_open" class="btn-ghost p-2" :title="t('Print')" @click="printReceipt(reportText(s), 'Shift report', auth.settings.logo_url)"><Printer :size="16" /></button>
              <button
                v-else-if="auth.can('reports') && s.user_id !== auth.user?.id"
                class="btn-outline px-2.5 py-1 text-sm"
                :title="t('Count and close a shift its cashier left open')"
                @click="closeOther(s)"
              >
                {{ t('Close') }}
              </button>
            </td>
          </tr>
          <tr v-if="!history.length"><td colspan="7" class="py-8 text-center text-muted">{{ t('No shifts yet') }}</td></tr>
        </tbody>
      </table>
    </div>

    <AppModal
      v-if="closing"
      :title="closing.mode === 'handover' ? t('Hand over the drawer') : closing.mode === 'other' ? t('Close shift of {name}', { name: closing.shift.cashier_name }) : t('Count the drawer')"
      width="max-w-sm"
      @close="closing = null"
    >
      <form id="close-form" class="space-y-3" @submit.prevent="close">
        <p v-if="closing.mode === 'handover'" class="rounded-xl bg-primary-soft px-3 py-2 text-sm text-primary">
          {{ t('Count the drawer together. Your shift closes with this count and the next cashier starts with it.') }}
        </p>
        <p v-if="closing.mode === 'other'" class="text-sm text-muted">{{ t('Expected in drawer') }}: {{ usd(closing.shift.expected_cash) }}</p>
        <div v-if="closing.mode === 'handover'">
          <label class="label">{{ t('Next cashier') }}</label>
          <select v-model="nextUserId" class="input">
            <option value="" disabled>{{ t('Choose') }}</option>
            <option v-for="s in others" :key="s.id" :value="s.id" :disabled="!s.has_pin">
              {{ s.full_name || s.username }}{{ s.has_pin ? '' : ` (${t('no PIN')})` }}
            </option>
          </select>
        </div>
        <div>
          <label class="label">{{ t('US dollars counted') }}</label>
          <input v-model="countedUsd" class="input text-lg" inputmode="decimal" placeholder="0.00" autofocus />
        </div>
        <div>
          <label class="label">{{ t('Riel counted') }}</label>
          <input v-model="countedKhr" class="input text-lg" inputmode="numeric" placeholder="0" />
        </div>
        <div v-if="countedTotal !== null" class="flex justify-between rounded-xl bg-page px-3 py-2 font-semibold">
          <span class="text-muted">{{ t('Counted') }}</span><span>{{ usd(countedTotal) }}</span>
        </div>
        <div v-if="closing.mode === 'handover'">
          <label class="label">{{ t('PIN of the next cashier (they type it)') }}</label>
          <input v-model="nextPin" class="input text-lg" type="password" inputmode="numeric" autocomplete="off" />
        </div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="closing = null">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="close-form" :disabled="busy">
          {{ closing.mode === 'handover' ? t('Hand over') : t('Close shift') }}
        </button>
      </template>
    </AppModal>

    <AppModal v-if="closed" :title="t('Shift closed')" width="max-w-sm" @close="closed = null">
      <p v-if="handedTo" class="mb-3 rounded-xl bg-ok-soft px-3 py-2 text-sm text-ok">
        {{ t('{name} now has the drawer with {amount}.', { name: handedTo.cashier_name, amount: usd(handedTo.opening_cash) }) }}
      </p>
      <dl class="space-y-1.5">
        <div v-for="[label, value, cls] in rows(closed)" :key="label" :class="['flex justify-between', cls]">
          <dt :class="cls ? '' : 'text-muted'">{{ t(label) }}</dt>
          <dd>{{ value }}</dd>
        </div>
      </dl>
      <template #footer>
        <button class="btn-outline" @click="printReceipt(reportText(closed!), 'Shift report', auth.settings.logo_url)"><Printer :size="17" /> {{ t('Print') }}</button>
        <button v-if="handedTo" class="btn-primary" @click="logOutForNext">{{ t('Log out for {name}', { name: handedTo.cashier_name }) }}</button>
        <button v-else class="btn-primary" @click="closed = null">{{ t('Done') }}</button>
      </template>
    </AppModal>
  </div>
</template>
