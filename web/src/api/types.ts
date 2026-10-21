// Shapes returned by the Python service (server/app/schemas.py).
// Money is always an integer: USD in cents, KHR in riel. Percent = basis points (1000 = 10%).

export type Role = 'admin' | 'manager' | 'cashier'

/** What a role may do; the admin edits them on the Users page (server/app/permissions.py). */
export type Permission = 'reports' | 'all_sales' | 'approve' | 'products' | 'inventory' | 'suppliers' | 'expenses' | 'staff'

export interface PermissionsInfo {
  permissions: { key: Permission; label: string }[]
  roles: Record<Role, Permission[]>
  mine: Permission[]
}
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
  /** home branch: opens shifts only on its registers (null: any outlet) */
  location_id: number | null
  location_name: string | null
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
  location_id: number | null
  /** null = main shop */
  location_name: string | null
  created_at: string
}

/** A branch or warehouse. The main shop (where the tills sell) is not one of these: it is `null`. */
export interface Location {
  id: number
  name: string
  kind: 'warehouse' | 'branch'
  address: string | null
  is_active: boolean
}

export interface Transfer {
  id: number
  transfer_no: string
  from_location_id: number | null
  from_name: string
  to_location_id: number | null
  to_name: string
  status: 'in_transit' | 'received' | 'cancelled'
  note: string | null
  created_by: string
  created_at: string
  closed_by: string | null
  closed_at: string | null
  items: { product_id: number; product_name: string; qty: number; unit_cost: number }[]
  total_qty: number
  total_cost: number
}

/** Active users, for choosing who takes over a shift or a held order. */
export interface Staff {
  id: number
  username: string
  full_name: string
  role: Role
  has_pin: boolean
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
  visits: number
  total_spent: number // cents, after refunds
  last_visit: string | null
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
  /** the branch that sold it (null: the main shop) */
  location_name: string | null
  register_name: string | null
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
  /** sent to this cashier's till (any till can still finish it) */
  assigned_to_id: number | null
  assigned_to_name: string | null
}

export interface ShiftHandover {
  closed: ShiftReport
  opened: ShiftReport
}

/** A till / counter with its own cash drawer; a shift opens on one. */
export interface Register {
  id: number
  name: string
  is_active: boolean
  /** the branch it stands in (null: the main shop); it sells from that outlet's stock */
  location_id: number | null
  location_name: string | null
  open_shift_id: number | null
  open_by: string | null
}

export interface ShiftReport {
  id: number
  user_id: number
  cashier_name: string
  register_id: number | null
  register_name: string | null
  /** the register's branch (null: the main shop); the till sells its stock */
  location_id: number | null
  location_name: string | null
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
  /** closed by handing the drawer to this cashier */
  handed_to_name: string | null
  /** opened by taking the drawer over from this cashier */
  handed_from_name: string | null
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
  /** the outlet the report is for (null: the whole business) */
  location_name: string | null
  expenses: number
  net_profit: number
  by_payment: NameAmount[]
  by_cashier: NameAmount[]
  by_branch: NameAmount[]
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

// ---------- reports by feature (Reports menu) ----------

export interface ProductReportRow {
  product_id: number | null
  name: string
  category: string
  qty: number
  sales: number
  cost: number
  profit: number
}

export interface CashierReportRow {
  name: string
  sales_count: number
  gross: number
  refunds: number
  net: number
  discounts: number
  average_sale: number
  voids: number
  shifts: number
  over_short: number
}

export interface PaymentReportRow {
  method: string
  count: number
  received_usd: number
  received_khr: number
  net: number
}

export interface RefundReportRow {
  id: number
  created_at: string
  receipt_no: string
  sale_id: number
  refunded_by: string
  approved_by: string
  reason: string
  items: string
  amount: number
  cash_amount: number
}

export interface LogReportRow {
  created_at: string
  user: string
  detail: string
}

export interface DiscountReportRow {
  created_at: string
  receipt_no: string
  sale_id: number
  cashier: string
  approved_by: string
  subtotal: number
  discount: number
  total: number
}

export interface StockReport {
  places: { name: string; kind: string; qty: number; value: number }[]
  received: { name: string; qty: number; value: number }[]
  losses: { name: string; qty: number; value: number }[]
}

export interface CustomerReportRow {
  customer_id: number
  name: string
  phone: string | null
  visits: number
  spent: number
  points: number
  last_visit: string | null
}

export interface Expense {
  id: number
  spent_on: string
  category: string
  amount: number
  note: string | null
  from_drawer: boolean
  recorded_by: string
  created_at: string
}

export interface ExpenseReport {
  categories: { name: string; count: number; amount: number }[]
  items: Expense[]
}
