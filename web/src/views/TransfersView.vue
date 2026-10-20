<script setup lang="ts">
// Stock transfers between the main shop and branches / warehouses: on the road, received, cancelled.
import { ArrowRight, Check, ChevronDown, Plus, Printer, Truck, X } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Location, Transfer } from '@/api/types'
import TransferModal from '@/components/TransferModal.vue'
import { t } from '@/lib/i18n'
import { dateTime, usd } from '@/lib/money'
import { printReceipt } from '@/lib/print'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const transfers = ref<Transfer[]>([])
const locations = ref<Location[]>([])
const status = ref<'in_transit' | 'received' | 'cancelled' | ''>('in_transit')
const creating = ref(false)
const open = ref<number | null>(null)
const busy = ref(false)

const TABS = [
  { value: 'in_transit', label: 'On the road' },
  { value: 'received', label: 'Received' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: '', label: 'All' },
] as const
const STATUS: Record<Transfer['status'], [string, string]> = {
  in_transit: ['On the road', 'bg-warn-soft text-warn'],
  received: ['Received', 'bg-ok-soft text-ok'],
  cancelled: ['Cancelled', 'bg-page text-muted'],
}
const activeLocations = computed(() => locations.value.filter((l) => l.is_active))

async function load() {
  try {
    ;[transfers.value, locations.value] = await Promise.all([
      api.get<Transfer[]>('/transfers', { status: status.value, limit: 300 }),
      api.get<Location[]>('/locations'),
    ])
  } catch (e) {
    ui.error(e)
  }
}

async function receive(tr: Transfer) {
  if (!(await ui.confirm(t('Receive {no}', { no: tr.transfer_no }), t('{n} item(s) arrived at {place}? They are added to its stock.', { n: tr.total_qty, place: tr.to_name }), 'Receive'))) return
  await act(tr, 'receive', t('Received at {place}', { place: tr.to_name }))
}

async function cancel(tr: Transfer) {
  if (!(await ui.confirm(t('Cancel {no}', { no: tr.transfer_no }), t('The {n} item(s) go back to {place}.', { n: tr.total_qty, place: tr.from_name }), 'Cancel transfer', true))) return
  await act(tr, 'cancel', t('Transfer cancelled'))
}

async function act(tr: Transfer, action: 'receive' | 'cancel', done: string) {
  busy.value = true
  try {
    await api.post(`/transfers/${tr.id}/${action}`)
    ui.toast(done, 'success')
    load()
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

/** A delivery note for the driver / the receiving shop, on the receipt printer. */
function print(tr: Transfer) {
  const w = 42
  const row = (left: string, right: string) => left.slice(0, w - right.length - 1).padEnd(w - right.length) + right
  const lines = [
    auth.settings.store_name,
    'STOCK TRANSFER',
    tr.transfer_no,
    dateTime(tr.created_at),
    '-'.repeat(w),
    `From: ${tr.from_name}`,
    `To:   ${tr.to_name}`,
    `Sent by: ${tr.created_by}`,
    '-'.repeat(w),
    ...tr.items.map((i) => row(i.product_name, `x ${i.qty}`)),
    '-'.repeat(w),
    row('Items', String(tr.total_qty)),
    row('Value at cost', usd(tr.total_cost)),
  ]
  if (tr.note) lines.push('', tr.note)
  if (tr.closed_at) lines.push('', `${STATUS[tr.status][0]} ${dateTime(tr.closed_at)} by ${tr.closed_by}`)
  else lines.push('', '', 'Received by: ______________________', '', 'Date: _____________________________')
  printReceipt(lines.join('\n'), tr.transfer_no, auth.settings.logo_url)
}

function sent(tr: Transfer) {
  creating.value = false
  ui.toast(t('{no} sent to {place}', { no: tr.transfer_no, place: tr.to_name }), 'success')
  status.value = 'in_transit'
  load()
  open.value = tr.id
}

watch(status, load)
onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
    <div class="card flex flex-wrap items-center gap-2 p-3">
      <div class="flex flex-wrap gap-1 rounded-xl bg-page p-1">
        <button
          v-for="tab in TABS"
          :key="tab.value"
          :class="['rounded-lg px-3 py-1.5 text-sm font-semibold transition', status === tab.value ? 'bg-white text-primary shadow-sm' : 'text-muted hover:text-ink']"
          @click="status = tab.value"
        >
          {{ t(tab.label) }}
        </button>
      </div>
      <div class="flex-1" />
      <RouterLink to="/inventory/locations" class="btn-outline">{{ t('Branches & warehouses') }}</RouterLink>
      <button class="btn-primary" :disabled="!activeLocations.length" @click="creating = true"><Plus :size="18" /> {{ t('New transfer') }}</button>
    </div>

    <div v-if="!activeLocations.length" class="card flex flex-col items-center gap-3 p-10 text-center">
      <Truck :size="36" class="text-muted" />
      <p class="font-semibold">{{ t('Add a branch or warehouse first') }}</p>
      <p class="max-w-md text-sm text-muted">{{ t('Transfers move stock between the main shop and your branches or warehouses.') }}</p>
      <RouterLink to="/inventory/locations" class="btn-primary"><Plus :size="18" /> {{ t('Add a branch or warehouse') }}</RouterLink>
    </div>

    <div v-else class="card overflow-x-auto">
      <table class="table min-w-[860px]">
        <thead>
          <tr>
            <th>{{ t('Transfer') }}</th><th>{{ t('From') }} → {{ t('To') }}</th><th class="text-right">{{ t('Items') }}</th>
            <th class="text-right">{{ t('Value') }}</th><th>{{ t('Status') }}</th><th class="text-right">{{ t('Actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="tr in transfers" :key="tr.id">
            <tr class="cursor-pointer" @click="open = open === tr.id ? null : tr.id">
              <td>
                <p class="flex items-center gap-1 font-mono font-semibold">
                  <ChevronDown :size="15" :class="['text-muted transition', open === tr.id && 'rotate-180']" />{{ tr.transfer_no }}
                </p>
                <p class="text-xs text-muted">{{ dateTime(tr.created_at) }} · {{ tr.created_by }}</p>
              </td>
              <td>
                <span class="inline-flex items-center gap-1.5 font-medium">{{ tr.from_name }} <ArrowRight :size="14" class="text-muted" /> {{ tr.to_name }}</span>
                <p v-if="tr.note" class="text-xs text-muted">{{ tr.note }}</p>
              </td>
              <td class="text-right">{{ tr.total_qty }}</td>
              <td class="text-right">{{ usd(tr.total_cost) }}</td>
              <td>
                <span :class="['pill', STATUS[tr.status][1]]">{{ t(STATUS[tr.status][0]) }}</span>
                <p v-if="tr.closed_at" class="mt-0.5 text-xs text-muted">{{ dateTime(tr.closed_at) }} · {{ tr.closed_by }}</p>
              </td>
              <td class="text-right whitespace-nowrap" @click.stop>
                <template v-if="tr.status === 'in_transit'">
                  <button class="btn-primary px-3 py-1.5 text-sm" :disabled="busy" @click="receive(tr)"><Check :size="16" /> {{ t('Receive') }}</button>
                  <button class="btn-ghost p-2" :title="t('Cancel transfer')" :disabled="busy" @click="cancel(tr)"><X :size="17" /></button>
                </template>
                <button class="btn-ghost p-2" :title="t('Print delivery note')" @click="print(tr)"><Printer :size="17" /></button>
              </td>
            </tr>
            <tr v-if="open === tr.id" class="bg-page/60">
              <td colspan="6" class="py-3">
                <ul class="grid gap-x-8 gap-y-1 sm:grid-cols-2">
                  <li v-for="i in tr.items" :key="i.product_id" class="flex justify-between gap-3 text-sm">
                    <span>{{ i.product_name }}</span><span class="font-semibold">× {{ i.qty }}</span>
                  </li>
                </ul>
              </td>
            </tr>
          </template>
          <tr v-if="!transfers.length">
            <td colspan="6" class="py-10 text-center text-muted">{{ status === 'in_transit' ? t('Nothing on the road') : t('No transfers') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <TransferModal v-if="creating" :locations="activeLocations" @close="creating = false" @sent="sent" />
  </div>
</template>
