// The period shown by the reports. Shared by every page of the Reports menu, so moving from one report to the
// next keeps the same days; kept for the browser tab only.
import { ref, watch } from 'vue'

import { addDays, isoDate } from './money'

function stored(key: string) {
  try {
    const value = sessionStorage.getItem(key)
    return value && /^\d{4}-\d\d-\d\d$/.test(value) ? value : null
  } catch {
    return null
  }
}

function storedOutlet() {
  try {
    const value = sessionStorage.getItem('pos.report.outlet') ?? ''
    return value === 'main' || /^\d+$/.test(value) ? value : ''
  } catch {
    return ''
  }
}

export const today = () => isoDate(new Date())
export const reportFrom = ref(stored('pos.report.from') ?? today())
export const reportTo = ref(stored('pos.report.to') ?? today())
/** The outlet the reports cover: '' the whole business, 'main' the main shop, or a branch id. Staff of a branch
 *  always get their branch (the service decides). */
export const reportOutlet = ref(storedOutlet())

watch([reportFrom, reportTo, reportOutlet], ([from, to, outlet]) => {
  try {
    sessionStorage.setItem('pos.report.from', from)
    sessionStorage.setItem('pos.report.to', to)
    sessionStorage.setItem('pos.report.outlet', outlet)
  } catch {
    // private window
  }
})

/** Quick choices: [label, from, to]. */
export function presets(): [string, string, string][] {
  const now = new Date()
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1)
  const lastMonthEnd = addDays(firstOfMonth, -1)
  return [
    ['Today', today(), today()],
    ['Yesterday', isoDate(addDays(now, -1)), isoDate(addDays(now, -1))],
    ['7 days', isoDate(addDays(now, -6)), today()],
    ['30 days', isoDate(addDays(now, -29)), today()],
    ['This month', isoDate(firstOfMonth), today()],
    ['Last month', isoDate(new Date(lastMonthEnd.getFullYear(), lastMonthEnd.getMonth(), 1)), isoDate(lastMonthEnd)],
  ]
}

/** The period, for pages that are not reports (expenses). */
export const rangeQuery = () => ({ date_from: reportFrom.value, date_to: reportTo.value })

/** Query for the report endpoints: the period and the outlet. */
export const reportQuery = () => ({ ...rangeQuery(), location: reportOutlet.value })

/** "2026-10-01" or "2026-10-01-to-2026-10-20", for file names. */
export const rangeName = () => (reportFrom.value === reportTo.value ? reportFrom.value : `${reportFrom.value}-to-${reportTo.value}`)
