<script setup lang="ts">
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Minus,
  PackagePlus,
  Percent,
  Receipt,
  RotateCcw,
  ShoppingCart,
  TrendingUp,
  UserRound,
  Wallet,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { Bar, Doughnut } from 'vue-chartjs'

import { api } from '@/api/client'
import type { Product, ReportSummary, SaleSummary, ShiftReport } from '@/api/types'
import ProductArt from '@/components/ProductArt.vue'
import { addDays, isoDate, khr, num, time, usd, usdCentsToKhr } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

ChartJS.register(ArcElement, BarController, BarElement, CategoryScale, Filler, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip)
import { dateLocale, longDate, t } from '@/lib/i18n'

const auth = useAuth()
const ui = useUi()

type Period = 1 | 7 | 30
const period = ref<Period>((Number(localStorage.getItem('pos.dashboardPeriod')) as Period) || 1)
const periods: { value: Period; label: string; previous: string }[] = [
  { value: 1, label: 'Today', previous: 'yesterday' },
  { value: 7, label: '7 days', previous: 'previous 7 days' },
  { value: 30, label: '30 days', previous: 'previous 30 days' },
]
const previousLabel = computed(() => t(periods.find((p) => p.value === period.value)!.previous))

const current = ref<ReportSummary | null>(null)
const previous = ref<ReportSummary | null>(null)
const lowStock = ref<Product[]>([])
const recent = ref<SaleSummary[]>([])
const onShift = ref<ShiftReport[]>([])
const loading = ref(true)
const updatedAt = ref<Date | null>(null)

const range = (days: number, back = 0) => {
  const end = addDays(new Date(), -back * days)
  return { date_from: isoDate(addDays(end, 1 - days)), date_to: isoDate(end) }
}

async function load() {
  loading.value = true
  try {
    const today = isoDate(new Date())
    ;[current.value, previous.value, lowStock.value, recent.value, onShift.value] = await Promise.all([
      api.get<ReportSummary>('/reports/summary', range(period.value)),
      api.get<ReportSummary>('/reports/summary', range(period.value, 1)),
      api.get<Product[]>('/inventory/low-stock'),
      api.get<SaleSummary[]>('/sales', { date_from: today, date_to: today, limit: 6 }),
      api.get<ShiftReport[]>('/shifts', { limit: 20 }).then((all) => all.filter((s) => s.is_open)),
    ])
    updatedAt.value = new Date()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

watch(period, (p) => {
  localStorage.setItem('pos.dashboardPeriod', String(p))
  load()
})
onMounted(load)

// ---------- header ----------
const greeting = computed(() => {
  const h = new Date().getHours()
  return t(h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening')
})
const todayText = computed(() => longDate(new Date()))

// ---------- KPI cards ----------
function change(now: number, before: number) {
  if (!before) return now ? null : 0 // null = "new" (nothing to compare with)
  return Math.round(((now - before) / before) * 1000) / 10
}

const kpis = computed(() => {
  const c = current.value
  const p = previous.value
  if (!c || !p) return []
  const margin = c.net_sales ? Math.round((c.profit / (c.net_sales - c.tax || 1)) * 100) : 0
  return [
    { label: 'Net sales', value: usd(c.net_sales), sub: khr(usdCentsToKhr(c.net_sales, auth.settings.exchange_rate)), change: change(c.net_sales, p.net_sales), icon: Wallet, tone: 'bg-blue-50 text-primary' },
    { label: 'Transactions', value: num(c.sales_count), sub: t('{value} {period}', { value: num(p.sales_count), period: previousLabel.value }), change: change(c.sales_count, p.sales_count), icon: ShoppingCart, tone: 'bg-violet-50 text-violet-600' },
    { label: 'Average sale', value: usd(c.average_sale), sub: t('{value} {period}', { value: usd(p.average_sale), period: previousLabel.value }), change: change(c.average_sale, p.average_sale), icon: Receipt, tone: 'bg-sky-50 text-sky-600' },
    { label: 'Profit', value: usd(c.profit), sub: t('{n}% margin', { n: margin }), change: change(c.profit, p.profit), icon: TrendingUp, tone: 'bg-ok-soft text-ok' },
  ]
})

const minor = computed(() => {
  const c = current.value
  if (!c) return []
  return [
    { label: 'Refunds', value: usd(c.refunds), icon: RotateCcw },
    { label: 'Discounts given', value: usd(c.discounts), icon: Percent },
    { label: 'VAT collected', value: usd(c.tax), icon: Receipt },
    { label: 'Items sold', value: num(c.by_category.reduce((n, x) => n + x.qty, 0)), icon: PackagePlus },
  ]
})

// ---------- sales chart: by hour for today, by day for 7 / 30 days, with the previous period as a line ----------
function dailySeries(report: ReportSummary, days: number, back: number) {
  const byDay = new Map(report.by_day.map((d) => [d.day, d.amount]))
  return Array.from({ length: days }, (_, i) => {
    const day = addDays(new Date(), -back * days - (days - 1 - i))
    return { label: day.toLocaleDateString(dateLocale(), { day: 'numeric', month: 'short' }), amount: byDay.get(isoDate(day)) ?? 0 }
  })
}

const chart = computed(() => {
  const c = current.value
  const p = previous.value
  if (!c || !p) return null
  let labels: string[]
  let now: number[]
  let before: number[]
  if (period.value === 1) {
    // shop hours only: first to last hour that had sales in either day, at least 7:00-21:00
    const busy = [...c.by_hour, ...p.by_hour].filter((h) => h.count).map((h) => h.hour)
    const first = Math.min(7, ...busy)
    const last = Math.max(21, ...busy)
    const hours = Array.from({ length: last - first + 1 }, (_, i) => first + i)
    labels = hours.map((h) => `${String(h).padStart(2, '0')}:00`)
    now = hours.map((h) => c.by_hour[h]!.amount / 100)
    before = hours.map((h) => p.by_hour[h]!.amount / 100)
  } else {
    const cur = dailySeries(c, period.value, 0)
    labels = cur.map((d) => d.label)
    now = cur.map((d) => d.amount / 100)
    before = dailySeries(p, period.value, 1).map((d) => d.amount / 100)
  }
  return {
    labels,
    datasets: [
      { type: 'bar' as const, label: t(periods.find((x) => x.value === period.value)!.label), data: now, backgroundColor: '#2563eb', borderRadius: 6, maxBarThickness: 34, order: 2 },
      {
        type: 'line' as const,
        label: previousLabel.value[0]!.toUpperCase() + previousLabel.value.slice(1),
        data: before,
        borderColor: '#94a3b8',
        backgroundColor: 'rgba(148,163,184,0.12)',
        borderDash: [5, 4],
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.35,
        fill: true,
        order: 1,
      },
    ],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { position: 'top' as const, align: 'end' as const, labels: { boxWidth: 12, boxHeight: 12, usePointStyle: true } },
    tooltip: { callbacks: { label: (c: { dataset: { label?: string }; parsed: { y: number | null } }) => `${c.dataset.label}: ${usd(Math.round((c.parsed.y ?? 0) * 100))}` } },
  },
  scales: {
    y: { beginAtZero: true, ticks: { callback: (v: string | number) => `$${v}` }, grid: { color: '#eef2f7' }, border: { display: false } },
    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
  },
}

// ---------- payment mix ----------
const paymentColors: Record<string, string> = { Cash: '#16a34a', Card: '#2563eb', KHQR: '#e11d48' }
const payments = computed(() => {
  const rows = current.value?.by_payment ?? []
  const total = rows.reduce((n, r) => n + r.amount, 0) || 1
  return rows.map((r) => ({ ...r, share: Math.round((r.amount / total) * 100), color: paymentColors[r.name] ?? '#94a3b8' }))
})
const paymentChart = computed(() => ({
  labels: payments.value.map((p) => t(p.name)),
  datasets: [{ data: payments.value.map((p) => p.amount / 100), backgroundColor: payments.value.map((p) => p.color), borderWidth: 0, hoverOffset: 6 }],
}))
const paymentOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '72%',
  plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c: { label: string; parsed: number }) => `${c.label}: ${usd(Math.round(c.parsed * 100))}` } } },
}

// ---------- lists ----------
const topProducts = computed(() => {
  const rows = current.value?.top_products.slice(0, 6) ?? []
  const max = Math.max(...rows.map((r) => r.amount), 1)
  return rows.map((r) => ({ ...r, width: `${Math.max(4, Math.round((r.amount / max) * 100))}%` }))
})
const statusClass = { completed: 'bg-ok-soft text-ok', partially_refunded: 'bg-warn-soft text-warn', refunded: 'bg-rose-50 text-price' }
</script>

<template>
  <div class="mx-auto max-w-[1400px] space-y-5 p-4 lg:p-6">
    <!-- header -->
    <div class="flex flex-col gap-4 xl:flex-row xl:items-end">
      <div class="min-w-0 flex-1">
        <p class="text-sm text-muted">{{ todayText }}</p>
        <h2 class="text-2xl font-extrabold">{{ greeting }}, {{ auth.displayName }}</h2>
        <p class="text-muted">
          {{ t('Here is how') }} <b class="text-ink">{{ auth.settings.store_name }}</b> {{ t('is doing.') }}
          <span v-if="updatedAt" class="text-xs">{{ t('Updated {time}', { time: time(updatedAt.toISOString()) }) }} · <button class="font-semibold text-primary hover:underline" @click="load">{{ t('refresh') }}</button></span>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div class="flex rounded-xl border border-line bg-white p-1">
          <button
            v-for="p in periods"
            :key="p.value"
            :class="['rounded-lg px-3.5 py-1.5 text-sm font-semibold transition', period === p.value ? 'bg-primary text-white' : 'text-muted hover:text-ink']"
            @click="period = p.value"
          >
            {{ t(p.label) }}
          </button>
        </div>
        <RouterLink to="/sell" class="btn-primary"><ShoppingCart :size="18" /> {{ t('New sale') }}</RouterLink>
        <RouterLink to="/products" class="btn-outline hidden sm:inline-flex"><PackagePlus :size="18" /> {{ t('Products') }}</RouterLink>
      </div>
    </div>

    <!-- KPI cards -->
    <div class="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      <template v-if="kpis.length">
        <div v-for="k in kpis" :key="k.label" class="card min-w-0 p-4 sm:p-5">
          <div class="flex items-start justify-between gap-2">
            <div :class="['flex size-9 shrink-0 items-center justify-center rounded-xl sm:size-11', k.tone]"><component :is="k.icon" :size="20" /></div>
            <span
              v-if="k.change !== 0"
              :class="['pill', k.change === null ? 'bg-primary-soft text-primary' : k.change > 0 ? 'bg-ok-soft text-ok' : 'bg-rose-50 text-price']"
              :title="t('Compared with {period}', { period: previousLabel })"
            >
              <template v-if="k.change === null">{{ t('new') }}</template>
              <template v-else>
                <component :is="k.change > 0 ? ArrowUpRight : ArrowDownRight" :size="14" />
                {{ Math.abs(k.change) }}%
              </template>
            </span>
            <span v-else class="pill bg-page text-muted"><Minus :size="14" /> 0%</span>
          </div>
          <p class="mt-3 text-sm font-semibold text-muted sm:mt-4">{{ t(k.label) }}</p>
          <p class="truncate text-2xl font-extrabold tracking-tight sm:text-3xl">{{ k.value }}</p>
          <p class="mt-1 truncate text-xs text-muted sm:text-sm">{{ k.sub }}</p>
        </div>
      </template>
      <template v-else>
        <div v-for="n in 4" :key="n" class="card h-[178px] animate-pulse bg-white/60" />
      </template>
    </div>

    <!-- small figures -->
    <div v-if="minor.length" class="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <div v-for="m in minor" :key="m.label" class="flex min-w-0 items-center gap-3 rounded-xl border border-line bg-white px-4 py-3">
        <component :is="m.icon" :size="18" class="hidden shrink-0 text-muted sm:block" />
        <span class="min-w-0 flex-1 truncate text-sm text-muted">{{ t(m.label) }}</span>
        <span class="font-bold">{{ m.value }}</span>
      </div>
    </div>

    <!-- charts -->
    <div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
      <div class="card min-w-0 p-5 xl:col-span-2">
        <div class="mb-2">
          <h3 class="font-bold">{{ period === 1 ? t('Sales by hour') : t('Sales by day') }}</h3>
          <p class="text-sm text-muted">{{ t('Compared with {period} (dashed line)', { period: previousLabel }) }}</p>
        </div>
        <div class="relative h-72 w-full">
          <Bar v-if="chart" :data="chart as any" :options="chartOptions" />
        </div>
      </div>

      <div class="card flex min-w-0 flex-col p-5">
        <h3 class="font-bold">{{ t('Payment methods') }}</h3>
        <p class="text-sm text-muted">{{ t('Money taken at the till, before refunds') }}</p>
        <div v-if="payments.length" class="relative mx-auto my-4 size-48">
          <Doughnut :data="paymentChart" :options="paymentOptions" />
          <div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span class="text-xs text-muted">{{ t('Total') }}</span>
            <span class="text-xl font-extrabold">{{ usd(payments.reduce((n, p) => n + p.amount, 0)) }}</span>
          </div>
        </div>
        <p v-else class="flex flex-1 items-center justify-center text-muted">{{ t('No payments yet') }}</p>
        <ul class="mt-auto space-y-2">
          <li v-for="p in payments" :key="p.name" class="flex items-center gap-3">
            <span class="size-3 rounded-full" :style="{ background: p.color }" />
            <span class="flex-1 font-semibold">{{ t(p.name) }}</span>
            <span class="text-sm text-muted">{{ p.count }} · {{ p.share }}%</span>
            <span class="w-24 text-right font-bold">{{ usd(p.amount) }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- lists -->
    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
      <div class="card min-w-0 p-5">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="font-bold">{{ t('Top products') }}</h3>
          <RouterLink to="/reports" class="text-sm font-semibold text-primary hover:underline">{{ t('Reports') }}</RouterLink>
        </div>
        <p v-if="!topProducts.length" class="py-8 text-center text-muted">{{ t('No sales in this period') }}</p>
        <div v-for="(p, i) in topProducts" :key="p.name" class="mb-3.5 last:mb-0">
          <div class="flex items-center gap-3 text-sm">
            <span class="flex size-6 items-center justify-center rounded-md bg-page text-xs font-bold text-muted">{{ i + 1 }}</span>
            <span class="min-w-0 flex-1 truncate font-semibold">{{ p.name }}</span>
            <span class="text-muted">{{ p.qty }} sold</span>
            <span class="w-20 text-right font-bold">{{ usd(p.amount) }}</span>
          </div>
          <div class="mt-1.5 ml-9 h-1.5 rounded-full bg-page"><div class="h-1.5 rounded-full bg-primary" :style="{ width: p.width }" /></div>
        </div>
      </div>

      <div class="card min-w-0 p-5">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="font-bold">{{ t('Latest sales today') }}</h3>
          <RouterLink to="/sales" class="text-sm font-semibold text-primary hover:underline">{{ t('All sales') }}</RouterLink>
        </div>
        <p v-if="!recent.length" class="py-8 text-center text-muted">{{ t('No sales yet today') }}</p>
        <ul class="divide-y divide-line">
          <li v-for="s in recent" :key="s.id" class="flex items-center gap-3 py-2.5">
            <div class="flex size-9 items-center justify-center rounded-xl bg-page text-muted"><Receipt :size="17" /></div>
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold">{{ s.receipt_no }}</p>
              <p class="truncate text-xs text-muted">{{ time(s.created_at) }} · {{ s.cashier_name }}{{ s.customer_name ? ` · ${s.customer_name}` : '' }}</p>
            </div>
            <div class="text-right">
              <p class="font-bold">{{ usd(s.total) }}</p>
              <span v-if="s.status !== 'completed'" :class="['pill', statusClass[s.status]]">{{ t(s.status.replace('_', ' ')) }}</span>
            </div>
          </li>
        </ul>
      </div>

      <div class="min-w-0 space-y-5 lg:col-span-2 xl:col-span-1">
        <div class="card p-5">
          <h3 class="mb-3 flex items-center gap-2 font-bold"><Clock :size="18" class="text-ok" /> {{ t('On shift now') }}</h3>
          <p v-if="!onShift.length" class="text-sm text-muted">{{ t('Nobody has an open cash drawer.') }}</p>
          <ul class="space-y-2.5">
            <li v-for="s in onShift" :key="s.id" class="flex items-center gap-3">
              <div class="flex size-9 items-center justify-center rounded-full bg-ok-soft text-ok"><UserRound :size="17" /></div>
              <div class="min-w-0 flex-1">
                <p class="truncate font-semibold">{{ s.cashier_name }}</p>
                <p class="text-xs text-muted">{{ t('since {time}', { time: time(s.opened_at) }) }} · {{ t('{n} sales', { n: s.sales_count }) }}</p>
              </div>
              <div class="text-right">
                <p class="text-xs text-muted">{{ t('in drawer') }}</p>
                <p class="font-bold">{{ usd(s.expected_cash) }}</p>
              </div>
            </li>
          </ul>
        </div>

        <div class="card p-5">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="flex items-center gap-2 font-bold"><AlertTriangle :size="18" class="text-warn" /> {{ t('Low stock') }}</h3>
            <span v-if="lowStock.length" class="pill bg-warn-soft text-warn">{{ lowStock.length }} items</span>
          </div>
          <p v-if="!lowStock.length" class="text-sm text-muted">{{ t('Everything is well stocked.') }}</p>
          <ul class="space-y-2">
            <li v-for="p in lowStock.slice(0, 5)" :key="p.id" class="flex items-center gap-3">
              <ProductArt :category="p.category_name" :image="p.image_url" :size="16" class="size-9 shrink-0 rounded-lg" />
              <span class="min-w-0 flex-1 truncate font-semibold">{{ p.name }}</span>
              <span :class="['pill', p.stock_qty <= 0 ? 'bg-rose-50 text-price' : 'bg-warn-soft text-warn']">
                {{ p.stock_qty <= 0 ? t('out') : t('{n} left', { n: p.stock_qty }) }}
              </span>
            </li>
          </ul>
          <RouterLink v-if="lowStock.length" to="/products" class="mt-3 inline-block text-sm font-semibold text-primary hover:underline">{{ t('Receive stock') }}</RouterLink>
        </div>
      </div>
    </div>

    <p v-if="loading && !current" class="text-center text-muted">{{ t('Loading dashboard...') }}</p>
  </div>
</template>
