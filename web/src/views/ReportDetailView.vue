<script setup lang="ts">
// One page of the Reports menu (see lib/reportDefs.ts): period picker, then tables you can sort, search and
// download for Excel, with a totals row and, for some, a chart.
import { BarElement, CategoryScale, Chart as ChartJS, LinearScale, Tooltip } from 'chart.js'
import { ArrowDown, ArrowUp, FileSpreadsheet, Search } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { Bar } from 'vue-chartjs'
import { useRoute } from 'vue-router'

import ReportRange from '@/components/ReportRange.vue'
import { saveBlob } from '@/lib/download'
import { t } from '@/lib/i18n'
import { dateTime, khr, num, usd } from '@/lib/money'
import { type Column, REPORTS, type Row, type Section } from '@/lib/reportDefs'
import { rangeName } from '@/lib/reportRange'
import { useUi } from '@/stores/ui'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip)

const route = useRoute()
const ui = useUi()
const kind = computed(() => String(route.params.kind))
const def = computed(() => REPORTS[kind.value])
const sections = ref<Section[]>([])
const loading = ref(false)
const query = ref('')
const sortBy = ref<Record<number, { key: string; desc: boolean }>>({})

async function load() {
  if (!def.value) return
  loading.value = true
  try {
    sections.value = await def.value.load()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}
watch(kind, () => {
  sections.value = []
  sortBy.value = {}
  query.value = ''
  load()
}, { immediate: true })

const isNumber = (c: Column) => !!c.format && c.format !== 'text' && c.format !== 'datetime'

function format(value: Row[string], c: Column): string {
  if (value === null || value === undefined || value === '') return '—'
  switch (c.format) {
    case 'usd': return usd(Number(value))
    case 'signed': return Number(value) > 0 ? `+${usd(Number(value))}` : usd(Number(value))
    case 'num': return num(Number(value))
    case 'khr': return khr(Number(value))
    case 'pct': return `${value}%`
    case 'datetime': return dateTime(String(value))
    default: return t(String(value))
  }
}

function rowsOf(i: number, s: Section): Row[] {
  const q = query.value.trim().toLowerCase()
  const rows = q ? s.rows.filter((r) => s.columns.some((c) => !isNumber(c) && String(r[c.key] ?? '').toLowerCase().includes(q))) : [...s.rows]
  const sort = sortBy.value[i]
  if (sort) {
    rows.sort((a, b) => {
      const x = a[sort.key] ?? ''
      const y = b[sort.key] ?? ''
      const order = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return sort.desc ? -order : order
    })
  }
  return rows
}

function toggleSort(i: number, c: Column) {
  const now = sortBy.value[i]
  sortBy.value = { ...sortBy.value, [i]: { key: c.key, desc: now?.key === c.key ? !now.desc : isNumber(c) } }
}

const total = (rows: Row[], c: Column) => rows.reduce((sum, r) => sum + Number(r[c.key] ?? 0), 0)
const hasTotals = (s: Section) => s.columns.some((c) => c.total)

/** /sales?day=YYYY-MM-DD&sale=id: the receipt opens on the Sales page. */
function saleLink(r: Row, c: Column) {
  const at = String(r[c.sale!.at] ?? '')
  return { path: '/sales', query: { sale: String(r[c.sale!.id]), day: `${at.slice(0, 4)}-${at.slice(4, 6)}-${at.slice(6, 8)}` } }
}

function chartFor(s: Section) {
  const rows = s.rows
  return {
    data: {
      labels: rows.map((r) => t(String(r[s.chart!.label]))),
      datasets: [{ data: rows.map((r) => Number(r[s.chart!.value]) / 100), backgroundColor: '#2563eb', borderRadius: 6, maxBarThickness: 36 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: (ctx: { parsed: { y: number | null } }) => usd(Math.round((ctx.parsed.y ?? 0) * 100)) } } },
      scales: { y: { ticks: { callback: (v: string | number) => `$${v}` }, grid: { color: '#e2e8f0' } }, x: { grid: { display: false } } },
    },
  }
}

/** CSV that Excel opens (with Khmer text): every table of the page, one after the other. */
function download() {
  const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const plain = (value: Row[string], c: Column) =>
    value === null || value === undefined ? '' : c.format === 'usd' || c.format === 'signed' ? (Number(value) / 100).toFixed(2) : c.format === 'datetime' ? dateTime(String(value)) : c.format === 'text' || !c.format ? t(String(value)) : value
  const lines: string[] = [cell(t(def.value!.title)), cell(rangeName())]
  sections.value.forEach((s, i) => {
    lines.push('')
    if (s.title) lines.push(cell(t(s.title)))
    lines.push(s.columns.map((c) => cell(t(c.label) + (c.format === 'usd' || c.format === 'signed' ? ' ($)' : ''))).join(','))
    const rows = rowsOf(i, s)
    for (const r of rows) lines.push(s.columns.map((c) => cell(plain(r[c.key], c))).join(','))
    if (hasTotals(s)) lines.push(s.columns.map((c, j) => cell(c.total ? plain(total(rows, c), c) : j === 0 ? t('Total') : '')).join(','))
  })
  saveBlob(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }), `${kind.value}-${rangeName()}.csv`)
}
</script>

<template>
  <div v-if="def" class="mx-auto max-w-7xl space-y-5 p-4 lg:p-6">
    <div>
      <h1 class="text-xl font-extrabold">{{ t(def.title) }}</h1>
      <p class="text-muted">{{ t(def.description) }}</p>
    </div>

    <ReportRange @load="load">
      <div class="relative">
        <Search :size="17" class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input w-56 py-2 pl-9" :placeholder="t('Search the table')" />
      </div>
      <button class="btn-outline" :disabled="!sections.length" @click="download"><FileSpreadsheet :size="18" /> {{ t('Download for Excel') }}</button>
    </ReportRange>

    <p v-if="loading && !sections.length" class="text-muted">{{ t('Loading...') }}</p>

    <section v-for="(s, i) in sections" :key="i" class="space-y-3" data-report-section>
      <div v-if="s.title || s.note">
        <h2 v-if="s.title" class="font-bold">{{ t(s.title) }}</h2>
        <p v-if="s.note" class="text-sm text-muted">{{ t(s.note) }}</p>
      </div>
      <div v-if="s.chart && s.rows.length > 1" class="card p-5">
        <div class="relative h-60 w-full"><Bar v-bind="chartFor(s)" /></div>
      </div>
      <div class="card overflow-x-auto">
        <table class="table">
          <thead>
            <tr>
              <th v-for="c in s.columns" :key="c.key" :class="['cursor-pointer whitespace-nowrap select-none', isNumber(c) && 'text-right']" @click="toggleSort(i, c)">
                {{ t(c.label) }}
                <ArrowDown v-if="sortBy[i]?.key === c.key && sortBy[i]!.desc" :size="13" class="inline" />
                <ArrowUp v-else-if="sortBy[i]?.key === c.key" :size="13" class="inline" />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, n) in rowsOf(i, s)" :key="n">
              <td
                v-for="c in s.columns"
                :key="c.key"
                :class="[
                  isNumber(c) ? 'text-right whitespace-nowrap tabular-nums' : '',
                  c.format === 'signed' && Number(r[c.key]) < 0 && 'text-price font-semibold',
                  c.format === 'signed' && Number(r[c.key]) > 0 && 'text-ok font-semibold',
                ]"
              >
                <RouterLink v-if="c.sale" :to="saleLink(r, c)" class="font-semibold text-primary hover:underline">{{ r[c.key] }}</RouterLink>
                <span v-else :class="c === s.columns[0] && 'font-semibold'">{{ format(r[c.key], c) }}</span>
              </td>
            </tr>
            <tr v-if="!rowsOf(i, s).length">
              <td :colspan="s.columns.length" class="py-8 text-center text-muted">{{ t('Nothing in this period') }}</td>
            </tr>
          </tbody>
          <tfoot v-if="hasTotals(s) && rowsOf(i, s).length > 1">
            <tr class="border-t-2 border-line font-bold">
              <td v-for="(c, j) in s.columns" :key="c.key" :class="isNumber(c) && 'text-right whitespace-nowrap tabular-nums'">
                {{ c.total ? format(total(rowsOf(i, s), c), c) : j === 0 ? t('Total') : '' }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  </div>
  <div v-else class="p-6 text-muted">{{ t('Report not found') }}</div>
</template>
