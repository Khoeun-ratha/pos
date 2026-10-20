<script setup lang="ts">
import { BarElement, CategoryScale, Chart as ChartJS, LinearScale, Tooltip } from 'chart.js'
import { AlertTriangle, Banknote, Boxes, FileSpreadsheet, PackageMinus, PackagePlus, Percent, Receipt, RotateCcw, ShoppingCart, TrendingUp, Wallet } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { Bar } from 'vue-chartjs'

import { api } from '@/api/client'
import type { NameAmount, Product, ReportSummary } from '@/api/types'
import { saveBlob } from '@/lib/download'
import { t } from '@/lib/i18n'
import { addDays, isoDate, num, usd } from '@/lib/money'
import { useUi } from '@/stores/ui'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip)

const ui = useUi()
const today = isoDate(new Date())
const from = ref(today)
const to = ref(today)
const report = ref<ReportSummary | null>(null)
const lowStock = ref<Product[]>([])
const exporting = ref(false)

const ranges = [
  { label: 'Today', days: 1 },
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
]

async function load() {
  try {
    ;[report.value, lowStock.value] = await Promise.all([
      api.get<ReportSummary>('/reports/summary', { date_from: from.value, date_to: to.value }),
      api.get<Product[]>('/inventory/low-stock'),
    ])
  } catch (e) {
    ui.error(e)
  }
}

async function exportExcel() {
  exporting.value = true
  try {
    const blob = await api.blob('/reports/export', { date_from: from.value, date_to: to.value })
    saveBlob(blob, from.value === to.value ? `sales-${from.value}.xlsx` : `sales-${from.value}-to-${to.value}.xlsx`)
  } catch (e) {
    ui.error(e)
  } finally {
    exporting.value = false
  }
}

function range(days: number) {
  to.value = today
  from.value = isoDate(addDays(new Date(), 1 - days))
  load()
}

const stats = computed(() => {
  const r = report.value
  if (!r) return []
  return [
    { label: 'Net sales', value: usd(r.net_sales), icon: Wallet, color: 'bg-blue-50 text-primary' },
    { label: 'Sales', value: num(r.sales_count), icon: ShoppingCart, color: 'bg-violet-50 text-violet-600' },
    { label: 'Profit', value: usd(r.profit), icon: TrendingUp, color: 'bg-ok-soft text-ok' },
    { label: 'Average sale', value: usd(r.average_sale), icon: Receipt, color: 'bg-sky-50 text-sky-600' },
    { label: 'Gross sales', value: usd(r.gross_sales), icon: Banknote, color: 'bg-blue-50 text-primary' },
    { label: 'Refunds', value: usd(r.refunds), icon: RotateCcw, color: 'bg-rose-50 text-price' },
    { label: 'Discounts', value: usd(r.discounts), icon: Percent, color: 'bg-warn-soft text-warn' },
    { label: 'VAT collected', value: usd(r.tax), icon: Receipt, color: 'bg-slate-100 text-muted' },
    { label: 'Stock received', value: usd(r.purchases), icon: PackagePlus, color: 'bg-sky-50 text-sky-600' },
    { label: 'Stock losses', value: usd(r.stock_losses), icon: PackageMinus, color: 'bg-rose-50 text-price' },
    { label: 'Stock value now', value: usd(r.stock_value), icon: Boxes, color: 'bg-violet-50 text-violet-600' },
  ]
})

const chartData = computed(() => ({
  labels: report.value?.by_day.map((d) => d.day.slice(5).replace('-', '/')) ?? [],
  datasets: [{ data: report.value?.by_day.map((d) => d.amount / 100) ?? [], backgroundColor: '#2563eb', borderRadius: 6, maxBarThickness: 36 }],
}))
const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { tooltip: { callbacks: { label: (c: { parsed: { y: number | null } }) => usd(Math.round((c.parsed.y ?? 0) * 100)) } } },
  scales: { y: { ticks: { callback: (v: string | number) => `$${v}` }, grid: { color: '#e2e8f0' } }, x: { grid: { display: false } } },
}

function share(rows: NameAmount[], row: NameAmount) {
  const max = Math.max(...rows.map((r) => r.amount), 1)
  return `${Math.round((row.amount / max) * 100)}%`
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 p-4 lg:p-6">
    <div class="card flex flex-wrap items-end gap-3 p-4">
      <div class="flex gap-1 rounded-xl bg-page p-1">
        <button v-for="r in ranges" :key="r.days" class="rounded-lg px-3 py-1.5 font-semibold hover:bg-white" @click="range(r.days)">{{ t(r.label) }}</button>
      </div>
      <div>
        <label class="label">{{ t('From') }}</label>
        <input v-model="from" type="date" class="input py-2" :max="to" />
      </div>
      <div>
        <label class="label">{{ t('To') }}</label>
        <input v-model="to" type="date" class="input py-2" :min="from" :max="today" />
      </div>
      <button class="btn-primary" @click="load">{{ t('Show') }}</button>
      <button class="btn-outline ml-auto" :disabled="exporting" @click="exportExcel"><FileSpreadsheet :size="18" /> {{ t('Export Excel') }}</button>
    </div>

    <template v-if="report">
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div v-for="s in stats" :key="s.label" class="card flex items-center gap-3 p-4">
          <div :class="['flex size-11 shrink-0 items-center justify-center rounded-xl', s.color]"><component :is="s.icon" :size="20" /></div>
          <div class="min-w-0">
            <p class="text-xs font-semibold text-muted uppercase">{{ t(s.label) }}</p>
            <p class="truncate text-xl font-extrabold">{{ s.value }}</p>
          </div>
        </div>
      </div>

      <div v-if="report.by_day.length > 1" class="card p-5">
        <h2 class="mb-3 font-bold">{{ t('Sales by day') }}</h2>
        <div class="relative h-64 w-full"><Bar :data="chartData" :options="chartOptions" /></div>
      </div>

      <div class="grid gap-5 lg:grid-cols-2">
        <div class="space-y-5">
          <div class="card p-5">
            <h2 class="mb-3 font-bold">{{ t('Top products') }}</h2>
            <p v-if="!report.top_products.length" class="text-muted">{{ t('No sales yet') }}</p>
            <div v-for="p in report.top_products" :key="p.name" class="mb-3">
              <div class="flex justify-between text-sm"><span class="font-semibold">{{ p.name }}</span><span>{{ usd(p.amount) }} · {{ t('{n} sold', { n: p.qty }) }}</span></div>
              <div class="mt-1 h-2 rounded-full bg-page"><div class="h-2 rounded-full bg-primary" :style="{ width: share(report.top_products, p) }" /></div>
            </div>
          </div>
          <div class="card p-5">
            <h2 class="mb-3 font-bold">{{ t('Categories') }}</h2>
            <div v-for="c in report.by_category" :key="c.name" class="mb-3">
              <div class="flex justify-between text-sm"><span class="font-semibold">{{ c.name }}</span><span>{{ usd(c.amount) }} · {{ t('{n} sold', { n: c.qty }) }}</span></div>
              <div class="mt-1 h-2 rounded-full bg-page"><div class="h-2 rounded-full bg-violet-500" :style="{ width: share(report.by_category, c) }" /></div>
            </div>
          </div>
        </div>
        <div class="space-y-5">
          <div class="card overflow-x-auto">
            <h2 class="border-b border-line px-5 py-4 font-bold">{{ t('Payment methods') }}</h2>
            <table class="table">
              <tbody>
                <tr v-for="p in report.by_payment" :key="p.name"><td class="font-semibold">{{ t(p.name) }}</td><td class="text-muted">{{ t('{n} payments', { n: p.count }) }}</td><td class="text-right font-bold">{{ usd(p.amount) }}</td></tr>
              </tbody>
            </table>
          </div>
          <div class="card overflow-x-auto">
            <h2 class="border-b border-line px-5 py-4 font-bold">{{ t('Cashiers') }}</h2>
            <table class="table">
              <tbody>
                <tr v-for="c in report.by_cashier" :key="c.name"><td class="font-semibold">{{ c.name }}</td><td class="text-muted">{{ t('{n} sales', { n: c.count }) }}</td><td class="text-right font-bold">{{ usd(c.amount) }}</td></tr>
              </tbody>
            </table>
          </div>
          <div class="card overflow-x-auto">
            <h2 class="flex items-center gap-2 border-b border-line px-5 py-4 font-bold"><AlertTriangle :size="18" class="text-warn" /> {{ t('Low stock') }}</h2>
            <p v-if="!lowStock.length" class="p-5 text-muted">{{ t('All products have enough stock') }}</p>
            <table v-else class="table">
              <tbody>
                <tr v-for="p in lowStock" :key="p.id">
                  <td class="font-semibold">{{ p.name }}</td>
                  <td class="text-right"><span :class="['pill', p.stock_qty <= 0 ? 'bg-rose-50 text-price' : 'bg-warn-soft text-warn']">{{ t('{n} left', { n: p.stock_qty }) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
