// Shapes returned by the Python service (server/app/schemas.py).
// Money is always an integer: USD in cents, KHR in riel. Percent = basis points (1000 = 10%).

export type Role = 'admin' | 'manager' | 'cashier'
export type DiscountType = 'percent' | 'amount'
export type PaymentMethod = 'cash' | 'card' | 'khqr'
export type Currency = 'USD' | 'KHR'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
  has_pin: boolean
}

export interface TokenResponse {
  access_token: string
  user: User
}

export interface StoreSettings {
  store_name: string
  store_address: string
  store_phone: string
  tax_rate_bp: number
  tax_inclusive: boolean
  exchange_rate: number
  receipt_footer: string
  allow_negative_stock: boolean
  loyalty_points_per_usd: number
  logo_url: string // '' when there is no logo
}

export interface Category {
  id: number
  name: string
  sort_order: number
}

export interface Product {
  id: number
  name: string
  sku: string | null
  barcode: string | null
  category_id: number | null
  category_name: string | null
  price: number
  cost: number
  track_stock: boolean
  stock_qty: number
  low_stock_threshold: number
  is_active: boolean
  image_url: string | null
}

export interface ProductInput {
  name: string
  sku: string | null
  barcode: string | null
  category_id: number | null
  price: number
  cost: number
  track_stock: boolean
  low_stock_threshold: number
  is_active: boolean
  stock_qty?: number
}

export interface StockMovement {
  id: number
  product_id: number
  product_name: string
  change: number
  balance: number
  kind: string
  reference: string | null
  note: string | null
  unit_cost: number | null
  supplier_id: number | null
  supplier_name: string | null
  created_at: string
}

export interface Supplier {
  id: number
  name: string
  phone: string | null
  note: string | null
  is_active: boolean
}

export type WriteOffReason = 'damaged' | 'expired' | 'lost' | 'own_use'

export interface Customer {
  id: number
  name: string
  phone: string | null
  email: string | null
  points: number
  created_at: string
}

export interface PaymentIn {
  method: PaymentMethod
  currency: Currency
  amount: number
  reference?: string | null // card approval code / KHQR transaction id
}

export interface SaleItem {
  id: number
  product_id: number | null
  product_name: string
  qty: number
  unit_price: number
  discount: number
  tax: number
  line_total: number
  refunded_qty: number
  refunded_amount: number
  note: string | null
}

export interface Payment extends PaymentIn {
  amount_usd: number
}

export interface Sale {
  id: number
  receipt_no: string
  cashier_name: string
  customer_id: number | null
  customer_name: string | null
  subtotal: number
  discount_total: number
  tax_total: number
  total: number
  paid_total: number
  change_due: number
  change_due_khr: number
  exchange_rate: number
  refunded_total: number
  status: 'completed' | 'partially_refunded' | 'refunded'
  note: string | null
  created_at: string
  items: SaleItem[]
  payments: Payment[]
}

export interface SaleSummary {
  id: number
  receipt_no: string
  cashier_name: string
  customer_name: string | null
  total: number
  refunded_total: number
  status: Sale['status']
  created_at: string
}

export interface CartItemIn {
  product_id: number
  qty: number
  discount_type: DiscountType | null
  discount_value: number
}

/** POST /sales/quote: the service's prices and totals for a cart. */
export interface QuoteResult {
  total: number
  lines: { product_id: number; unit_price: number; line_total: number }[]
}

/** A held order, kept on the server until a till resumes it. */
export interface ParkedOrder {
  id: number
  label: string
  user_id: number
  cashier_name: string
  customer_id: number | null
  customer_name: string | null
  cart: { items: CartItemIn[]; discount_type: DiscountType | null; discount_value: number }
  total: number
  created_at: string
}

export interface ShiftReport {
  id: number
  user_id: number
  cashier_name: string
  opened_at: string
  closed_at: string | null
  is_open: boolean
  sales_count: number
  opening_cash: number
  cash_sales: number
  card_sales: number
  khqr_sales: number
  cash_in: number
  cash_out: number
  cash_refunds: number
  expected_cash: number
  counted_cash: number | null
  variance: number | null
  note: string | null
}

export interface NameAmount {
  name: string
  qty: number
  count: number
  amount: number
}

export interface ReportSummary {
  date_from: string
  date_to: string
  sales_count: number
  gross_sales: number
  refunds: number
  net_sales: number
  tax: number
  discounts: number
  cost: number
  profit: number
  average_sale: number
  purchases: number
  stock_losses: number
  stock_value: number
  by_payment: NameAmount[]
  by_cashier: NameAmount[]
  by_category: NameAmount[]
  top_products: NameAmount[]
  by_day: { day: string; count: number; amount: number }[]
  by_hour: { hour: number; count: number; amount: number }[]
}

export interface AuditEntry {
  id: number
  user_id: number | null
  username: string | null
  action: string
  detail: string
  created_at: string
}

export interface ImportResult {
  created: number
  updated: number
  errors: string[]
}
