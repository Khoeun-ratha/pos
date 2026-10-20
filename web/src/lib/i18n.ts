// English / Khmer. The English text is the key: t('Net sales') shows "ការលក់សុទ្ធ" in Khmer, and any text
// without a translation in km.ts simply stays English. Use {name} for values: t('{n} sold', { n: 3 }).
import { ref } from 'vue'

import { km } from './km'

export type Lang = 'en' | 'km'

function stored(): Lang {
  try {
    return localStorage.getItem('pos.lang') === 'km' ? 'km' : 'en'
  } catch {
    return 'en'
  }
}

export const lang = ref<Lang>(stored())
document.documentElement.lang = lang.value

export function setLang(value: Lang) {
  lang.value = value
  document.documentElement.lang = value
  try {
    localStorage.setItem('pos.lang', value)
  } catch {
    // private window: the choice lasts until the page closes
  }
}

/** Locale for short dates like "16 Oct" (browsers without Khmer dates fall back to English). */
export function dateLocale() {
  return lang.value === 'km' ? 'km-KH' : 'en-GB'
}

const KM_DAYS = ['អាទិត្យ', 'ច័ន្ទ', 'អង្គារ', 'ពុធ', 'ព្រហស្បតិ៍', 'សុក្រ', 'សៅរ៍']
const KM_MONTHS = ['មករា', 'កុម្ភៈ', 'មីនា', 'មេសា', 'ឧសភា', 'មិថុនា', 'កក្កដា', 'សីហា', 'កញ្ញា', 'តុលា', 'វិច្ឆិកា', 'ធ្នូ']

/** "Friday 16 October 2026" / "ថ្ងៃសុក្រ ទី16 ខែតុលា ឆ្នាំ2026", written out by hand so it works in every browser. */
export function longDate(date: Date) {
  if (lang.value === 'km') {
    return `ថ្ងៃ${KM_DAYS[date.getDay()]} ទី${date.getDate()} ខែ${KM_MONTHS[date.getMonth()]} ឆ្នាំ${date.getFullYear()}`
  }
  return new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(date)
}

export function t(text: string, values?: Record<string, string | number>): string {
  const out = lang.value === 'km' ? (km[text] ?? text) : text
  return values ? out.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match)) : out
}
