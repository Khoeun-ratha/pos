<script setup lang="ts">
import { Award, CalendarClock, Mail, Pencil, Phone, Search, UserPlus, Users } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Customer, SaleSummary } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { dateTime, day, num, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const ui = useUi()
const query = ref('')
const sort = ref<'name' | 'spent' | 'recent' | 'points'>('name')
const customers = ref<Customer[]>([])
const editing = ref<{ id: number | null; name: string; phone: string; email: string } | null>(null)
const selected = ref<Customer | null>(null)
const history = ref<SaleSummary[]>([])
let timer: ReturnType<typeof setTimeout> | undefined

const SORTS = [
  { value: 'name', label: 'Name A–Z' },
  { value: 'spent', label: 'Best customers' },
  { value: 'recent', label: 'Most recent visit' },
  { value: 'points', label: 'Most points' },
] as const
const sorted = computed(() => {
  const list = [...customers.value]
  const by = {
    name: (a: Customer, b: Customer) => a.name.localeCompare(b.name),
    spent: (a: Customer, b: Customer) => b.total_spent - a.total_spent,
    recent: (a: Customer, b: Customer) => (b.last_visit ?? '').localeCompare(a.last_visit ?? ''),
    points: (a: Customer, b: Customer) => b.points - a.points,
  }[sort.value]
  return list.sort(by)
})

const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString()
const totals = computed(() => ({
  count: customers.value.length,
  active: customers.value.filter((c) => c.last_visit && c.last_visit >= monthAgo).length,
  points: customers.value.reduce((n, c) => n + c.points, 0),
}))

// a steady colour per person, so the list is easy to scan
const PALETTE = ['bg-blue-100 text-blue-700', 'bg-emerald-100 text-emerald-700', 'bg-amber-100 text-amber-800', 'bg-rose-100 text-rose-700',
  'bg-violet-100 text-violet-700', 'bg-cyan-100 text-cyan-700', 'bg-orange-100 text-orange-700', 'bg-teal-100 text-teal-700']
const colour = (c: Customer) => PALETTE[[...c.name].reduce((n, ch) => n + ch.charCodeAt(0), 0) % PALETTE.length]
const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map((w) => [...w][0]).join('').toUpperCase()

function lastVisit(iso: string | null) {
  if (!iso) return t('Never')
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86400000)
  return days <= 0 ? t('Today') : days === 1 ? t('Yesterday') : days < 30 ? t('{n} days ago', { n: days }) : day(iso)
}
const average = (c: Customer) => (c.visits ? Math.round(c.total_spent / c.visits) : 0)
const statusClass: Record<string, string> = { partially_refunded: 'bg-warn-soft text-warn', refunded: 'bg-rose-50 text-price' }
const saleLink = (s: SaleSummary) => ({ path: '/sales', query: { sale: String(s.id), day: s.created_at.slice(0, 10) } })

async function load() {
  try {
    customers.value = await api.get<Customer[]>('/customers', { q: query.value.trim(), limit: 1000 })
  } catch (e) {
    ui.error(e)
  }
}

async function save() {
  const c = editing.value
  if (!c?.name.trim()) return ui.toast('Enter a name', 'error')
  const body = { name: c.name.trim(), phone: c.phone.trim() || null, email: c.email.trim() || null }
  try {
    const saved = c.id ? await api.put<Customer>(`/customers/${c.id}`, body) : await api.post<Customer>('/customers', body)
    editing.value = null
    if (selected.value?.id === saved.id) selected.value = saved
    ui.toast('Customer saved', 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

const edit = (c: Customer) => (editing.value = { id: c.id, name: c.name, phone: c.phone ?? '', email: c.email ?? '' })

async function open(c: Customer) {
  selected.value = c
  history.value = []
  try {
    history.value = await api.get<SaleSummary[]>(`/customers/${c.id}/sales`)
  } catch (e) {
    ui.error(e)
  }
}

watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
    <!-- at a glance -->
    <div class="grid grid-cols-3 gap-3">
      <div v-for="tile in [
        { icon: Users, label: 'Customers', value: num(totals.count), cls: 'bg-primary-soft text-primary' },
        { icon: CalendarClock, label: 'Bought in the last 30 days', value: num(totals.active), cls: 'bg-ok-soft text-ok' },
        { icon: Award, label: 'Points held', value: num(totals.points), cls: 'bg-warn-soft text-warn' },
      ]" :key="tile.label" class="card flex items-center gap-3 p-4">
        <div :class="['hidden size-11 shrink-0 items-center justify-center rounded-xl sm:flex', tile.cls]"><component :is="tile.icon" :size="21" /></div>
        <div class="min-w-0">
          <p class="text-xs leading-snug text-muted sm:text-sm">{{ t(tile.label) }}</p>
          <p class="text-xl font-extrabold">{{ tile.value }}</p>
        </div>
      </div>
    </div>

    <div class="card flex flex-wrap gap-2 p-3">
      <div class="relative min-w-56 flex-1">
        <Search :size="18" class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-10" :placeholder="t('Search name or phone')" />
      </div>
      <select v-model="sort" class="input w-auto flex-1 sm:flex-none" :aria-label="t('Sort')">
        <option v-for="s in SORTS" :key="s.value" :value="s.value">{{ t(s.label) }}</option>
      </select>
      <button class="btn-primary flex-1 whitespace-nowrap sm:flex-none" @click="editing = { id: null, name: '', phone: '', email: '' }"><UserPlus :size="18" /> {{ t('New customer') }}</button>
    </div>

    <p v-if="!sorted.length" class="card py-12 text-center text-muted">{{ t('No customers found') }}</p>

    <!-- computers and tablets: a table -->
    <div v-else class="card hidden overflow-x-auto md:block">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('Customer') }}</th><th>{{ t('Phone') }}</th><th class="text-right">{{ t('Visits') }}</th>
            <th class="text-right">{{ t('Spent') }}</th><th>{{ t('Last visit') }}</th><th class="text-right">{{ t('Points') }}</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in sorted" :key="c.id" class="cursor-pointer hover:bg-page" @click="open(c)">
            <td>
              <div class="flex items-center gap-3">
                <span :class="['flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-bold', colour(c)]">{{ initials(c.name) }}</span>
                <div class="min-w-0">
                  <p class="truncate font-semibold">{{ c.name }}</p>
                  <p v-if="c.email" class="truncate text-xs text-muted">{{ c.email }}</p>
                </div>
              </div>
            </td>
            <td class="whitespace-nowrap text-muted tabular-nums">{{ c.phone ?? '—' }}</td>
            <td class="text-right tabular-nums">{{ c.visits }}</td>
            <td class="text-right font-semibold tabular-nums">{{ usd(c.total_spent) }}</td>
            <td class="whitespace-nowrap text-muted">{{ lastVisit(c.last_visit) }}</td>
            <td class="text-right"><span class="pill bg-warn-soft whitespace-nowrap text-amber-800">{{ t('{n} pts', { n: num(c.points) }) }}</span></td>
            <td class="text-right">
              <button class="btn-ghost p-2" :title="t('Edit')" @click.stop="edit(c)"><Pencil :size="17" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- phones: a list -->
    <ul v-if="sorted.length" class="card divide-y divide-line md:hidden">
      <li v-for="c in sorted" :key="c.id">
        <button class="flex w-full items-center gap-3 px-4 py-3 text-left" @click="open(c)">
          <span :class="['flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-bold', colour(c)]">{{ initials(c.name) }}</span>
          <span class="min-w-0 flex-1">
            <span class="block truncate font-semibold">{{ c.name }}</span>
            <span class="block truncate text-sm text-muted">{{ c.phone ?? '—' }} · {{ lastVisit(c.last_visit) }}</span>
          </span>
          <span class="text-right">
            <span class="block font-semibold">{{ usd(c.total_spent) }}</span>
            <span class="text-xs font-semibold text-amber-700">{{ t('{n} pts', { n: num(c.points) }) }}</span>
          </span>
        </button>
      </li>
    </ul>

    <AppModal v-if="editing" :title="t(editing.id ? 'Edit customer' : 'New customer')" width="max-w-md" @close="editing = null">
      <form id="customer-form" class="space-y-3" @submit.prevent="save">
        <div><label class="label">{{ t('Name') }}</label><input v-model="editing.name" class="input" autofocus /></div>
        <div><label class="label">{{ t('Phone') }}</label><input v-model="editing.phone" class="input" inputmode="tel" /></div>
        <div><label class="label">{{ t('Email') }}</label><input v-model="editing.email" class="input" type="email" /></div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="editing = null">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="customer-form">{{ t('Save') }}</button>
      </template>
    </AppModal>

    <!-- one customer: who they are, what they bought -->
    <AppModal v-if="selected" :title="t('Customer')" width="max-w-xl" @close="selected = null">
      <div class="flex items-center gap-4">
        <span :class="['flex size-14 shrink-0 items-center justify-center rounded-full text-lg font-bold', colour(selected)]">{{ initials(selected.name) }}</span>
        <div class="min-w-0">
          <p class="truncate text-lg font-extrabold">{{ selected.name }}</p>
          <p class="flex flex-wrap gap-x-4 text-sm text-muted">
            <span v-if="selected.phone" class="inline-flex items-center gap-1"><Phone :size="14" /> {{ selected.phone }}</span>
            <span v-if="selected.email" class="inline-flex items-center gap-1"><Mail :size="14" /> {{ selected.email }}</span>
          </p>
          <p class="text-xs text-muted">{{ t('Customer since {date}', { date: day(selected.created_at) }) }}</p>
        </div>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div v-for="[label, value] in [
          ['Total spent', usd(selected.total_spent)], ['Visits', num(selected.visits)],
          ['Average sale', usd(average(selected))], ['Points', num(selected.points)],
        ]" :key="label" class="rounded-xl bg-page px-3 py-2.5">
          <p class="text-xs text-muted">{{ t(label) }}</p>
          <p class="font-extrabold">{{ value }}</p>
        </div>
      </div>

      <h3 class="mt-5 mb-1 font-bold">{{ t('Purchases') }}</h3>
      <p v-if="!history.length" class="py-6 text-center text-muted">{{ t('No purchases yet') }}</p>
      <ul class="divide-y divide-line">
        <li v-for="s in history" :key="s.id">
          <RouterLink :to="saleLink(s)" class="flex items-center justify-between gap-3 rounded-lg px-1 py-2.5 hover:bg-page">
            <span>
              <span class="block font-semibold text-primary">{{ s.receipt_no }}</span>
              <span class="text-sm text-muted">{{ dateTime(s.created_at) }}</span>
            </span>
            <span class="text-right">
              <span class="block font-bold">{{ usd(s.total - s.refunded_total) }}</span>
              <span v-if="s.status !== 'completed'" :class="['pill', statusClass[s.status]]">{{ t(s.status.replace('_', ' ')) }}</span>
            </span>
          </RouterLink>
        </li>
      </ul>
      <template #footer>
        <button class="btn-outline" @click="edit(selected)"><Pencil :size="16" /> {{ t('Edit') }}</button>
        <button class="btn-primary" @click="selected = null">{{ t('Done') }}</button>
      </template>
    </AppModal>
  </div>
</template>
