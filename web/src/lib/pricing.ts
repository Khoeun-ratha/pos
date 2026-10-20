// Mirror of server/app/pricing.py so the cart shows exactly what the service will charge.
// Percent discounts and tax rates are basis points: 1000 = 10%.
import type { DiscountType } from '@/api/types'
import { divRound } from './money'

export interface LineInput {
  unitPrice: number
  qty: number
  discountType?: DiscountType | null
  discountValue?: number
}

export interface LineResult {
  gross: number
  discount: number
  tax: number
  total: number
}

export interface CartTotals {
  subtotal: number
  discountTotal: number
  taxTotal: number
  total: number
  lines: LineResult[]
}

export function discountOf(base: number, type: DiscountType | null | undefined, value = 0) {
  if (!type || value <= 0 || base <= 0) return 0
  if (type === 'percent') return Math.min(base, divRound(base * Math.min(value, 10000), 10000))
  return Math.min(base, value)
}

/** Split an amount across weights proportionally; the parts always add up to the amount. */
export function allocate(amount: number, weights: number[]) {
  const sum = weights.reduce((a, b) => a + b, 0)
  if (amount <= 0 || sum <= 0) return weights.map(() => 0)
  const shares = weights.map((w) => Math.floor((amount * w) / sum))
  const order = weights.map((_, i) => i).sort((a, b) => ((amount * weights[b]!) % sum) - ((amount * weights[a]!) % sum))
  let left = amount - shares.reduce((a, b) => a + b, 0)
  for (const i of order) {
    if (left === 0) break
    shares[i]! += 1
    left -= 1
  }
  return shares
}

export function calculate(
  lines: LineInput[],
  orderDiscountType: DiscountType | null = null,
  orderDiscountValue = 0,
  taxRateBp = 0,
  taxInclusive = false,
): CartTotals {
  const gross = lines.map((l) => l.unitPrice * l.qty)
  const lineDiscounts = lines.map((l, i) => discountOf(gross[i]!, l.discountType, l.discountValue))
  const nets = gross.map((g, i) => g - lineDiscounts[i]!)
  const orderDiscount = discountOf(
    nets.reduce((a, b) => a + b, 0),
    orderDiscountType,
    orderDiscountValue,
  )
  const shares = allocate(orderDiscount, nets)

  const results = lines.map((_, i): LineResult => {
    const taxable = nets[i]! - shares[i]!
    const tax = taxInclusive ? taxable - divRound(taxable * 10000, 10000 + taxRateBp) : divRound(taxable * taxRateBp, 10000)
    return { gross: gross[i]!, discount: lineDiscounts[i]! + shares[i]!, tax, total: taxInclusive ? taxable : taxable + tax }
  })
  const sum = (pick: (r: LineResult) => number) => results.reduce((a, r) => a + pick(r), 0)
  return {
    subtotal: gross.reduce((a, b) => a + b, 0),
    discountTotal: sum((r) => r.discount),
    taxTotal: sum((r) => r.tax),
    total: sum((r) => r.total),
    lines: results,
  }
}
