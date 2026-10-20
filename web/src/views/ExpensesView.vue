<script setup lang="ts">
// Shop expenses: rent, electricity, salaries, ice... for the chosen period, by category and one by one.
// "Paid from my cash drawer" also takes the cash out of your open shift, so the drawer count stays right.
import { Banknote, Pencil, Plus, Trash2, TrendingDown, Wallet } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/client'
import type { Expense, ReportSummary } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import ReportRange from '@/components/ReportRange.vue'
import { t } from '@/lib/i18n'
import { parseHundredths, toDollars, usd } from '@/lib/money'
import { rangeQuery, today } from '@/lib/reportRange'
import { useAuth } from '@/stores/auth'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const shift = useShift()
const ui = useUi()
const expenses = ref<Expense[]>([])
const categories = ref<string[]>([])
const summary = ref<ReportSummary | null>(null)
const category = ref('')
const editing = ref<Expense | null>(null)
const formOpen = ref(false)
const busy = ref(false)
const form = reactive({ spent_on: today(), category: 'Electricity', amount: '', note: '', from_drawer: false })

async function load() {
  try {
    const [list, cats] = await Promise.all([api.get<Expense[]>('/expenses', rangeQuery()), api.get<string[]>('/expenses/categories')])
    expenses.value = list
    categories.value = cats
    summary.value = auth.can('reports') ? await api.get<ReportSummary>('/reports/summary', rangeQuery()) : null
  } catch (e) {
    ui.error(e)
  }
}

const shown = computed(() => (category.value ? expenses.value.filter((e) => e.category === category.value) : expenses.value))
const total = computed(() => shown.value.reduce((sum, e) => sum + e.amount, 0))
const byCategory = computed(() => {
  const rows = new Map<string, number>()
  for (const e of expenses.value) rows.set(e.category, (rows.get(e.category) ?? 0) + e.amount)
  const all = [...rows.values()].reduce((a, b) => a + b, 0)
  return [...rows.entries()].sort((a, b) => b[1] - a[1]).map(([name, amount]) => ({ name, amount, share: all ? Math.round((amount / all) * 100) : 0 }))
})

function openForm(e: Expense | null) {
  editing.value = e
  Object.assign(form, e
    ? { spent_on: e.spent_on, category: e.category, amount: toDollars(e.amount), note: e.note ?? '', from_drawer: e.from_drawer }
    : { spent_on: today(), category: category.value || form.category, amount: '', note: '', from_drawer: false })
  formOpen.value = true
}

async function save() {
  const amount = parseHundredths(form.amount)
  if (!amount) return ui.toast(t('Enter the amount'), 'error')
  if (!form.category.trim()) return ui.toast(t('Choose a category'), 'error')
  busy.value = true
  try {
    const body = { spent_on: form.spent_on, category: form.category.trim(), amount, note: form.note.trim() || null, from_drawer: form.from_drawer }
    if (editing.value) await api.put(`/expenses/${editing.value.id}`, body)
    else await api.post('/expenses', body)
    formOpen.value = false
    ui.toast(editing.value ? t('Expense saved') : t('Expense added: {amount}', { amount: usd(amount) }), 'success')
    if (form.from_drawer) shift.refresh().catch(() => {})
    load()
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

async function remove(e: Expense) {
  const message = e.from_drawer ? t('The cash goes back into the drawer count of the shift.') : t('This cannot be undone.')
  if (!(await ui.confirm(t('Delete {amount} {category}?', { amount: usd(e.amount), category: t(e.category) }), message, 'Delete', true))) return
  try {
    await api.delete(`/expenses/${e.id}`)
    ui.toast(t('Expense deleted'), 'success')
    load()
  } catch (err) {
    ui.error(err)
  }
}

const dayLabel = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

onMounted(() => {
  load()
  shift.refresh().catch(() => {})
})
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-5 p-4 lg:p-6">
    <ReportRange @load="load">
      <button class="btn-primary" @click="openForm(null)"><Plus :size="18" /> {{ t('Add expense') }}</button>
    </ReportRange>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div class="card flex items-center gap-3 p-4">
        <div class="flex size-11 items-center justify-center rounded-xl bg-rose-50 text-price"><TrendingDown :size="20" /></div>
        <div>
          <p class="text-xs font-semibold text-muted uppercase">{{ t('Expenses') }}</p>
          <p class="text-xl font-extrabold" data-expense-total>{{ usd(expenses.reduce((s, e) => s + e.amount, 0)) }}</p>
        </div>
      </div>
      <template v-if="summary">
        <div class="card flex items-center gap-3 p-4">
          <div class="flex size-11 items-center justify-center rounded-xl bg-ok-soft text-ok"><Wallet :size="20" /></div>
          <div>
            <p class="text-xs font-semibold text-muted uppercase">{{ t('Gross profit') }}</p>
            <p class="text-xl font-extrabold">{{ usd(summary.profit) }}</p>
          </div>
        </div>
        <div class="card flex items-center gap-3 p-4">
          <div :class="['flex size-11 items-center justify-center rounded-xl', summary.net_profit >= 0 ? 'bg-ok-soft text-ok' : 'bg-rose-50 text-price']"><Banknote :size="20" /></div>
          <div>
            <p class="text-xs font-semibold text-muted uppercase">{{ t('Profit after expenses') }}</p>
            <p :class="['text-xl font-extrabold', summary.net_profit < 0 && 'text-price']" data-net-profit>{{ usd(summary.net_profit) }}</p>
          </div>
        </div>
      </template>
    </div>

    <div class="grid gap-5 lg:grid-cols-[18rem_1fr]">
      <!-- by category; a click filters the list -->
      <div class="card h-fit p-4">
        <h2 class="mb-3 font-bold">{{ t('By category') }}</h2>
        <p v-if="!byCategory.length" class="text-sm text-muted">{{ t('No expenses in this period') }}</p>
        <button
          v-for="c in byCategory"
          :key="c.name"
          :class="['mb-1 block w-full rounded-lg px-2 py-1.5 text-left hover:bg-page', category === c.name && 'bg-primary-soft']"
          @click="category = category === c.name ? '' : c.name"
        >
          <div class="flex justify-between text-sm"><span class="font-semibold">{{ t(c.name) }}</span><span>{{ usd(c.amount) }}</span></div>
          <div class="mt-1 h-1.5 rounded-full bg-page"><div class="h-1.5 rounded-full bg-price/70" :style="{ width: `${c.share}%` }" /></div>
        </button>
      </div>

      <div class="card overflow-x-auto">
        <div class="flex items-center gap-2 border-b border-line px-5 py-3">
          <h2 class="flex-1 font-bold">{{ category ? t(category) : t('All expenses') }}</h2>
          <button v-if="category" class="text-sm font-semibold text-primary hover:underline" @click="category = ''">{{ t('Show all') }}</button>
        </div>
        <table class="table min-w-[640px]">
          <thead>
            <tr><th>{{ t('Date') }}</th><th>{{ t('Category') }}</th><th>{{ t('Note') }}</th><th>{{ t('By') }}</th><th class="text-right">{{ t('Amount') }}</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="e in shown" :key="e.id" data-expense-row>
              <td class="whitespace-nowrap">{{ dayLabel(e.spent_on) }}</td>
              <td>
                <span class="font-semibold">{{ t(e.category) }}</span>
                <span v-if="e.from_drawer" class="pill ml-2 bg-warn-soft text-warn">{{ t('from the drawer') }}</span>
              </td>
              <td class="text-muted">{{ e.note || '—' }}</td>
              <td class="text-muted">{{ e.recorded_by }}</td>
              <td class="text-right font-bold whitespace-nowrap">{{ usd(e.amount) }}</td>
              <td class="text-right whitespace-nowrap">
                <button class="btn-ghost p-2" :title="t('Edit')" @click="openForm(e)"><Pencil :size="16" /></button>
                <button class="btn-ghost p-2 text-price" :title="t('Delete')" @click="remove(e)"><Trash2 :size="16" /></button>
              </td>
            </tr>
            <tr v-if="!shown.length">
              <td colspan="6" class="py-10 text-center text-muted">{{ t('No expenses in this period') }}</td>
            </tr>
          </tbody>
          <tfoot v-if="shown.length > 1">
            <tr class="border-t-2 border-line font-bold"><td colspan="4">{{ t('Total') }}</td><td class="text-right">{{ usd(total) }}</td><td /></tr>
          </tfoot>
        </table>
      </div>
    </div>

    <AppModal v-if="formOpen" :title="editing ? t('Edit expense') : t('Add expense')" width="max-w-md" @close="formOpen = false">
      <form id="expense-form" class="space-y-3" @submit.prevent="save">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="label">{{ t('Date') }}</label><input v-model="form.spent_on" type="date" class="input" :max="today()" /></div>
          <div><label class="label">{{ t('Amount (USD)') }}</label><input v-model="form.amount" class="input" inputmode="decimal" placeholder="0.00" autofocus /></div>
        </div>
        <div>
          <label class="label">{{ t('Category') }}</label>
          <input v-model="form.category" class="input" list="expense-categories" maxlength="50" />
          <datalist id="expense-categories"><option v-for="c in categories" :key="c" :value="c">{{ t(c) }}</option></datalist>
          <div class="mt-2 flex flex-wrap gap-1">
            <button
              v-for="c in categories.slice(0, 11)"
              :key="c"
              type="button"
              :class="['rounded-lg px-2 py-1 text-xs font-semibold', form.category === c ? 'bg-primary text-white' : 'bg-page text-muted hover:text-ink']"
              @click="form.category = c"
            >
              {{ t(c) }}
            </button>
          </div>
        </div>
        <div><label class="label">{{ t('Note (optional)') }}</label><input v-model="form.note" class="input" maxlength="200" :placeholder="t('e.g. invoice number, month')" /></div>
        <label :class="['flex items-start gap-2 rounded-lg bg-page p-3 text-sm', editing && 'opacity-60']">
          <input v-model="form.from_drawer" type="checkbox" class="mt-0.5 size-4 accent-primary" :disabled="!!editing" />
          <span>
            <span class="font-semibold">{{ t('Paid with cash from my drawer') }}</span>
            <span class="block text-muted">
              {{ shift.current ? t('It is taken out of your open shift, so the cash count stays right.') : t('Open a shift first to pay from the cash drawer') }}
            </span>
          </span>
        </label>
      </form>
      <template #footer>
        <button class="btn-outline" @click="formOpen = false">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="expense-form" :disabled="busy">{{ editing ? t('Save') : t('Add expense') }}</button>
      </template>
    </AppModal>
  </div>
</template>
