import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, ApiError } from '@/api/client'
import type { Customer, DiscountType, ParkedOrder, Product, QuoteResult, Staff } from '@/api/types'
import { t } from '@/lib/i18n'
import { calculate } from '@/lib/pricing'
import { useAuth } from './auth'
import { useUi } from './ui'

export interface CartLine {
  product: Product
  qty: number
  discountType: DiscountType | null
  discountValue: number
}

/** crypto.randomUUID only exists on https / localhost; the shop network uses plain http by IP. */
function uuid() {
  if (typeof globalThis.crypto?.randomUUID === 'function' && window.isSecureContext) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

export const useCart = defineStore('cart', () => {
  const lines = ref<CartLine[]>([])
  const customer = ref<Customer | null>(null)
  const discountType = ref<DiscountType | null>(null)
  const discountValue = ref(0)
  /** PIN of the manager who approved a cashier's discount or void; one approval covers the whole order. */
  const managerPin = ref<string | null>(null)
  /** Stays the same for every payment attempt of this order, so a retry after a network error can never
   *  record the sale twice (the service returns the first one). A new order gets a new id. */
  const orderId = ref(uuid())
  /** Held orders of every till, from the service; the ones sent to this cashier come first. */
  const held = ref<ParkedOrder[]>([])
  /** Who a held order can be sent to (loaded the first time it is needed). */
  const staff = ref<Staff[]>([])
  /** The line the last tap or scan went to, so the cart can show it; addCount changes on every add. */
  const lastAdded = ref<CartLine | null>(null)
  const addCount = ref(0)

  const auth = useAuth()
  const ui = useUi()

  const totals = computed(() =>
    calculate(
      lines.value.map((l) => ({ unitPrice: l.product.price, qty: l.qty, discountType: l.discountType, discountValue: l.discountValue })),
      discountType.value,
      discountValue.value,
      auth.settings.tax_rate_bp,
      auth.settings.tax_inclusive,
    ),
  )
  const itemCount = computed(() => lines.value.reduce((n, l) => n + l.qty, 0))
  const isEmpty = computed(() => lines.value.length === 0)
  const hasAnyDiscount = computed(() => (discountType.value !== null && discountValue.value > 0) || lines.value.some((l) => l.discountType && l.discountValue > 0))

  /** Cashiers need a manager PIN to give discounts; one approval covers the order. */
  async function approve(reason: string) {
    if (auth.can('approve') || managerPin.value) return true
    const pin = await ui.managerPin(reason)
    if (!pin) return false
    managerPin.value = pin
    return true
  }

  /** Takes items off an unpaid order. Cashiers need a manager PIN (asked once per order); the service checks
   *  it and writes the void to the activity log. Returns false when not approved. */
  async function recordVoid(kind: 'line' | 'clear' | 'parked', items: { name: string; qty: number; amount: number }[]) {
    let pin = auth.can('approve') ? null : managerPin.value
    if (!auth.can('approve') && !pin) {
      pin = await ui.prompt({ title: kind === 'clear' ? 'Void sale' : 'Void item', label: 'Manager PIN', inputmode: 'numeric', password: true, confirmText: 'Approve' })
      if (!pin) return false
    }
    try {
      await api.post('/sales/void', { kind, items, manager_pin: pin })
      if (pin) managerPin.value = pin
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) managerPin.value = null
      ui.error(e)
      return false
    }
  }

  const voidItem = (line: CartLine, qty: number) => ({ name: line.product.name, qty, amount: line.product.price * qty })

  function add(product: Product, qty = 1) {
    let line = lines.value.find((l) => l.product.id === product.id && !l.discountType)
    if (line) line.qty += qty
    else {
      lines.value.push({ product, qty, discountType: null, discountValue: 0 })
      line = lines.value[lines.value.length - 1]!
    }
    lastAdded.value = line
    addCount.value += 1
  }

  /** More is always fine; fewer is a void. */
  async function setQty(line: CartLine, qty: number) {
    if (qty < 1 || qty === line.qty) return
    if (qty < line.qty && !(await recordVoid('line', [voidItem(line, line.qty - qty)]))) return
    line.qty = qty
  }

  async function remove(line: CartLine) {
    if (!(await recordVoid('line', [voidItem(line, line.qty)]))) return
    lines.value = lines.value.filter((l) => l !== line)
  }

  async function setLineDiscount(line: CartLine, type: DiscountType | null, value: number) {
    if (type && value > 0 && !(await approve('Approve discount'))) return false
    line.discountType = type && value > 0 ? type : null
    line.discountValue = type && value > 0 ? value : 0
    return true
  }

  async function setOrderDiscount(type: DiscountType, value: number) {
    if (value > 0 && !(await approve('Approve discount'))) return false
    discountType.value = value > 0 ? type : null
    discountValue.value = value > 0 ? value : 0
    return true
  }

  /** Empties the till for the next order (after a sale, or after holding this one). */
  function reset() {
    lines.value = []
    customer.value = null
    discountType.value = null
    discountValue.value = 0
    managerPin.value = null
    lastAdded.value = null
    orderId.value = uuid()
  }

  async function clear() {
    if (isEmpty.value || !(await ui.confirm('Clear sale', 'Remove all items from this sale?', 'Clear', true))) return
    if (await recordVoid('clear', lines.value.map((l) => voidItem(l, l.qty)))) reset()
  }

  function cartBody() {
    return {
      items: lines.value.map((l) => ({ product_id: l.product.id, qty: l.qty, discount_type: l.discountType, discount_value: l.discountValue })),
      discount_type: discountType.value,
      discount_value: discountValue.value,
    }
  }

  // ---------- held orders (on the service, shared by all tills) ----------

  async function loadHeld() {
    const me = auth.user?.id
    const all = await api.get<ParkedOrder[]>('/parked')
    held.value = [...all.filter((o) => o.assigned_to_id === me), ...all.filter((o) => o.assigned_to_id !== me)]
  }

  /** "Any till" plus every other active user, for the "Send to" list. */
  async function sendToChoices() {
    if (!staff.value.length) staff.value = await api.get<Staff[]>('/users/staff').catch(() => [])
    return [
      { value: '', label: 'Any till' },
      ...staff.value.filter((s) => s.id !== auth.user?.id).map((s) => ({ value: String(s.id), label: s.full_name || s.username })),
    ]
  }

  async function hold() {
    if (isEmpty.value) return
    const answer = await ui.promptChoice({
      title: 'Hold order',
      label: 'Name or note, so you can find it again (optional)',
      placeholder: 'e.g. Lady in red',
      choiceLabel: 'Send to',
      choices: await sendToChoices(),
    })
    if (answer === null) return
    try {
      await api.post('/parked', {
        ...cartBody(),
        customer_id: customer.value?.id ?? null,
        label: answer.text.trim(),
        assigned_to_id: answer.choice ? Number(answer.choice) : null,
      })
      reset()
      ui.toast(answer.choice ? 'Order sent to the other till.' : 'Order held. Tap it above the cart to continue later.', 'success')
    } catch (e) {
      ui.error(e)
    }
    loadHeld().catch(() => {})
  }

  /** Passes a held order to another cashier's till. */
  async function sendHeld(order: ParkedOrder) {
    const answer = await ui.promptChoice({
      title: 'Send held order',
      message: t('{name} · {total}', { name: order.label || order.customer_name || order.cashier_name, total: `$${(order.total / 100).toFixed(2)}` }),
      noInput: true,
      choiceLabel: 'Send to',
      choices: await sendToChoices(),
      initialChoice: order.assigned_to_id ? String(order.assigned_to_id) : '',
      confirmText: 'Send',
    })
    if (answer === null) return
    try {
      await api.post(`/parked/${order.id}/assign`, { assigned_to_id: answer.choice ? Number(answer.choice) : null })
      ui.toast('Held order sent', 'success')
    } catch (e) {
      ui.error(e)
    }
    loadHeld().catch(() => {})
  }

  /** Brings a held order back to this till. `catalog` gives today's products and prices. */
  async function resume(order: ParkedOrder, catalog: Product[]) {
    if (!isEmpty.value) {
      ui.toast('Finish or hold the current sale first')
      return
    }
    try {
      const taken = await api.post<ParkedOrder>(`/parked/${order.id}/resume`)
      const byId = new Map(catalog.map((p) => [p.id, p]))
      const missing = taken.cart.items.filter((i) => !byId.has(i.product_id)).length
      lines.value = taken.cart.items
        .filter((i) => byId.has(i.product_id))
        .map((i) => ({ product: byId.get(i.product_id)!, qty: i.qty, discountType: i.discount_type, discountValue: i.discount_value }))
      discountType.value = taken.cart.discount_type
      discountValue.value = taken.cart.discount_value
      customer.value = taken.customer_id ? await api.get<Customer>(`/customers/${taken.customer_id}`).catch(() => null) : null
      if (missing) ui.toast(t('{n} item(s) are no longer for sale and were left out', { n: missing }), 'error')
    } catch (e) {
      ui.error(e)
    }
    loadHeld().catch(() => {})
  }

  async function discardHeld(order: ParkedOrder) {
    if (!(await ui.confirm('Discard held order', t('Throw away the held order of {total}?', { total: `$${(order.total / 100).toFixed(2)}` }), 'Discard', true))) return
    let pin: string | null = null
    if (!auth.can('approve')) {
      pin = await ui.prompt({ title: 'Discard held order', label: 'Manager PIN', inputmode: 'numeric', password: true, confirmText: 'Approve' })
      if (!pin) return
    }
    try {
      await api.post(`/parked/${order.id}/discard`, { manager_pin: pin })
    } catch (e) {
      ui.error(e)
    }
    loadHeld().catch(() => {})
  }

  /** Before taking payment: makes sure the till shows the service's current prices, so the customer pays
   *  exactly what will be recorded. Returns false if the order cannot be sold as it is. */
  async function syncPrices() {
    try {
      const quote = await api.post<QuoteResult>('/sales/quote', cartBody())
      let changed = false
      quote.lines.forEach((q, i) => {
        const line = lines.value[i]
        if (line && line.product.price !== q.unit_price) {
          line.product = { ...line.product, price: q.unit_price }
          changed = true
        }
      })
      if (changed) ui.toast('A price changed since this screen was loaded. The total is updated.', 'info')
      return true
    } catch (e) {
      ui.error(e)
      return false
    }
  }

  /** Body for POST /api/sales. */
  function saleRequest(payments: { method: string; currency: string; amount: number; reference?: string | null }[]) {
    return {
      ...cartBody(),
      payments,
      customer_id: customer.value?.id ?? null,
      manager_pin: managerPin.value,
      client_uuid: orderId.value,
    }
  }

  return {
    lines,
    customer,
    discountType,
    discountValue,
    managerPin,
    held,
    lastAdded,
    addCount,
    totals,
    itemCount,
    isEmpty,
    hasAnyDiscount,
    add,
    setQty,
    remove,
    setLineDiscount,
    setOrderDiscount,
    clear,
    reset,
    loadHeld,
    hold, sendHeld, staff,
    resume,
    discardHeld,
    syncPrices,
    saleRequest,
  }
})
