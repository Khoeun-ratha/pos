// Money is always an integer: USD in cents, KHR in riel.

const usdFormat = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const numberFormat = new Intl.NumberFormat('en-US')

export const usd = (cents: number) => usdFormat.format(cents / 100)
export const khr = (riel: number) => `${numberFormat.format(riel)} ៛`
export const num = (value: number) => numberFormat.format(value)

/** Integer division rounding half up (non-negative inputs), same as the server. */
export const divRound = (numerator: number, denominator: number) => Math.floor((2 * numerator + denominator) / (2 * denominator))

export const khrToUsdCents = (riel: number, rate: number) => divRound(riel * 100, rate)

/** Cents to riel, rounded to the nearest 100-riel note. */
export const usdCentsToKhr = (cents: number, rate: number, roundTo = 100) => divRound(cents * rate, 100 * roundTo) * roundTo

/** "12.5" -> 1250 (cents, or basis points for percent). null when not a valid non-negative number. */
export function parseHundredths(text: string | number | null | undefined): number | null {
  const value = Number(String(text ?? '').replace(/,/g, '').trim())
  if (String(text ?? '').trim() === '' || !Number.isFinite(value) || value < 0) return null
  return Math.round(value * 100)
}

export function parseWhole(text: string | number | null | undefined): number | null {
  const value = Number(String(text ?? '').replace(/,/g, '').trim())
  if (String(text ?? '').trim() === '' || !Number.isInteger(value) || value < 0) return null
  return value
}

export const toDollars = (cents: number) => (cents / 100).toFixed(2)

const dateTimeFormat = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
const timeFormat = new Intl.DateTimeFormat('en-GB', { timeStyle: 'short' })

export const dateTime = (iso: string) => dateTimeFormat.format(new Date(iso))
export const time = (iso: string) => timeFormat.format(new Date(iso))

/** yyyy-mm-dd in local time. */
export function isoDate(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function addDays(date: Date, days: number) {
  const copy = new Date(date)
  copy.setDate(copy.getDate() + days)
  return copy
}
