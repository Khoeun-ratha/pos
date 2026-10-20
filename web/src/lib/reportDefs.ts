// The reports of the Reports menu (besides the overview). Each one loads its data for the chosen period and
// returns tables (and charts) that ReportDetailView shows, sorts, totals and downloads.
import { api } from '@/api/client'
import type {
  CashierReportRow, CustomerReportRow, DiscountReportRow, LogReportRow, PaymentReportRow, ProductReportRow,
  ExpenseReport, RefundReportRow, ReportSummary, ShiftReport, StockReport,
} from '@/api/types'
import { rangeQuery } from './reportRange'

export type Format = 'text' | 'usd' | 'num' | 'khr' | 'datetime' | 'pct' | 'signed'
export type Row = Record<string, string | number | null>

export interface Column {
  key: string
  label: string
  format?: Format
  /** sum it in the totals row */
  total?: boolean
  /** the cell opens this receipt on the Sales page */
  sale?: { id: string; at: string }
}

export interface Section {
  title?: string
  note?: string
  columns: Column[]
  rows: Row[]
  /** a bar chart of one column over the label column */
  chart?: { label: string; value: string }
}

export interface ReportDef {
  title: string
  description: string
  load: () => Promise<Section[]>
}

const get = <T>(path: string) => api.get<T>(path, rangeQuery())
/** Profit as a share of the sales without VAT (sales without VAT = cost + profit). */
const margin = (profit: number, cost: number) => (profit + cost > 0 ? Math.round((profit / (profit + cost)) * 1000) / 10 : null)

const productColumns: Column[] = [
  { key: 'qty', label: 'Qty sold', format: 'num', total: true },
  { key: 'sales', label: 'Sales', format: 'usd', total: true },
  { key: 'cost', label: 'Cost', format: 'usd', total: true },
  { key: 'profit', label: 'Profit', format: 'usd', total: true },
  { key: 'margin', label: 'Margin', format: 'pct' },
]

export const REPORTS: Record<string, ReportDef> = {
  products: {
    title: 'Sales by product',
    description: 'Every product sold, after returns, with its cost and profit. Click a column to sort.',
    async load() {
      const rows = await get<ProductReportRow[]>('/reports/products')
      return [{
        columns: [{ key: 'name', label: 'Product' }, { key: 'category', label: 'Category' }, ...productColumns],
        rows: rows.map((r) => ({ ...r, margin: margin(r.profit, r.cost) })),
      }]
    },
  },

  categories: {
    title: 'Sales by category',
    description: 'Products added up by category, with each category\'s share of the sales.',
    async load() {
      const byCategory = new Map<string, Row & { qty: number; sales: number; cost: number; profit: number }>()
      for (const r of await get<ProductReportRow[]>('/reports/products')) {
        const row = byCategory.get(r.category) ?? { category: r.category, products: 0, qty: 0, sales: 0, cost: 0, profit: 0 }
        row.products = Number(row.products) + 1
        row.qty += r.qty
        row.sales += r.sales
        row.cost += r.cost
        row.profit += r.profit
        byCategory.set(r.category, row)
      }
      const rows = [...byCategory.values()].sort((a, b) => b.sales - a.sales)
      const total = rows.reduce((sum, r) => sum + r.sales, 0)
      return [{
        columns: [
          { key: 'category', label: 'Category' }, { key: 'products', label: 'Products', format: 'num' }, ...productColumns,
          { key: 'share', label: 'Share of sales', format: 'pct' },
        ],
        rows: rows.map((r) => ({ ...r, margin: margin(r.profit, r.cost), share: total ? Math.round((r.sales / total) * 1000) / 10 : null })),
        chart: { label: 'category', value: 'sales' },
      }]
    },
  },

  time: {
    title: 'Sales by day & hour',
    description: 'Net sales for each day, and the busy hours of the period.',
    async load() {
      const s = await get<ReportSummary>('/reports/summary')
      return [
        {
          title: 'By day',
          columns: [{ key: 'day', label: 'Day' }, { key: 'count', label: 'Receipts', format: 'num', total: true }, { key: 'amount', label: 'Net sales', format: 'usd', total: true }],
          rows: s.by_day.map((d) => ({ ...d })),
          chart: { label: 'day', value: 'amount' },
        },
        {
          title: 'By hour',
          note: 'Hours with no sale are left out of the table.',
          columns: [{ key: 'hour', label: 'Hour' }, { key: 'count', label: 'Receipts', format: 'num', total: true }, { key: 'amount', label: 'Net sales', format: 'usd', total: true }],
          rows: s.by_hour.filter((h) => h.count || h.amount).map((h) => ({ ...h, hour: `${String(h.hour).padStart(2, '0')}:00` })),
          chart: { label: 'hour', value: 'amount' },
        },
      ]
    },
  },

  payments: {
    title: 'Payment methods',
    description: 'Money received by cash, card and KHQR, in dollars and in riel. Net is after change and refunds.',
    async load() {
      const rows = await get<PaymentReportRow[]>('/reports/payments')
      return [{
        columns: [
          { key: 'method', label: 'Method' }, { key: 'count', label: 'Payments', format: 'num', total: true },
          { key: 'received_usd', label: 'Received in USD', format: 'usd', total: true },
          { key: 'received_khr', label: 'Received in riel', format: 'khr', total: true },
          { key: 'net', label: 'Net', format: 'usd', total: true },
        ],
        rows: rows.map((r) => ({ ...r })),
        chart: { label: 'method', value: 'net' },
      }]
    },
  },

  cashiers: {
    title: 'Sales by cashier',
    description: 'Each cashier\'s sales, refunds, discounts, voids, and the over / short of their closed shifts.',
    async load() {
      const rows = await get<CashierReportRow[]>('/reports/cashiers')
      return [{
        columns: [
          { key: 'name', label: 'Cashier' }, { key: 'sales_count', label: 'Receipts', format: 'num', total: true },
          { key: 'gross', label: 'Gross sales', format: 'usd', total: true }, { key: 'refunds', label: 'Refunds', format: 'usd', total: true },
          { key: 'net', label: 'Net sales', format: 'usd', total: true }, { key: 'average_sale', label: 'Average sale', format: 'usd' },
          { key: 'discounts', label: 'Discounts', format: 'usd', total: true }, { key: 'voids', label: 'Voids', format: 'num', total: true },
          { key: 'shifts', label: 'Shifts closed', format: 'num', total: true }, { key: 'over_short', label: 'Over / short', format: 'signed', total: true },
        ],
        rows: rows.map((r) => ({ ...r })),
      }]
    },
  },

  refunds: {
    title: 'Refunds & voids',
    description: 'Money given back after a sale, and items taken off before payment, with who approved them.',
    async load() {
      const [refunds, voids] = await Promise.all([get<RefundReportRow[]>('/reports/refunds'), get<LogReportRow[]>('/reports/voids')])
      return [
        {
          title: 'Refunds',
          columns: [
            { key: 'created_at', label: 'Time', format: 'datetime' },
            { key: 'receipt_no', label: 'Receipt', sale: { id: 'sale_id', at: 'sale_day' } },
            { key: 'items', label: 'Items' }, { key: 'reason', label: 'Reason' }, { key: 'refunded_by', label: 'By' },
            { key: 'approved_by', label: 'Approved by' }, { key: 'cash_amount', label: 'From the drawer', format: 'usd', total: true },
            { key: 'amount', label: 'Amount', format: 'usd', total: true },
          ],
          rows: refunds.map((r) => ({ ...r, sale_day: r.receipt_no.slice(0, 8) })),
        },
        {
          title: 'Voids (taken off before payment)',
          columns: [{ key: 'created_at', label: 'Time', format: 'datetime' }, { key: 'user', label: 'Cashier' }, { key: 'detail', label: 'What' }],
          rows: voids.map((v) => ({ ...v })),
        },
      ]
    },
  },

  discounts: {
    title: 'Discounts',
    description: 'Every receipt with a discount, and the manager who approved it.',
    async load() {
      const rows = await get<DiscountReportRow[]>('/reports/discounts')
      return [{
        columns: [
          { key: 'created_at', label: 'Time', format: 'datetime' },
          { key: 'receipt_no', label: 'Receipt', sale: { id: 'sale_id', at: 'sale_day' } },
          { key: 'cashier', label: 'Cashier' }, { key: 'approved_by', label: 'Approved by' },
          { key: 'subtotal', label: 'Subtotal', format: 'usd', total: true }, { key: 'discount', label: 'Discount', format: 'usd', total: true },
          { key: 'total', label: 'Total paid', format: 'usd', total: true },
        ],
        rows: rows.map((r) => ({ ...r, sale_day: r.receipt_no.slice(0, 8) })),
      }]
    },
  },

  shifts: {
    title: 'Shifts & cash',
    description: 'Shifts opened in the period: cash expected in the drawer, cash counted, and over / short.',
    async load() {
      const rows = await get<ShiftReport[]>('/reports/shifts')
      return [{
        columns: [
          { key: 'cashier_name', label: 'Cashier' }, { key: 'opened_at', label: 'Opened', format: 'datetime' },
          { key: 'closed_at', label: 'Closed', format: 'datetime' }, { key: 'sales_count', label: 'Receipts', format: 'num', total: true },
          { key: 'opening_cash', label: 'Opening cash', format: 'usd' }, { key: 'cash_sales', label: 'Cash sales', format: 'usd', total: true },
          { key: 'card_sales', label: 'Card', format: 'usd', total: true }, { key: 'khqr_sales', label: 'KHQR', format: 'usd', total: true },
          { key: 'expected_cash', label: 'Expected', format: 'usd' }, { key: 'counted_cash', label: 'Counted', format: 'usd' },
          { key: 'variance', label: 'Over / short', format: 'signed', total: true }, { key: 'handed', label: 'Handover' },
        ],
        rows: rows.map((s) => ({
          ...s,
          handed: s.handed_to_name ? `→ ${s.handed_to_name}` : s.handed_from_name ? `← ${s.handed_from_name}` : '',
        })) as unknown as Row[],
      }]
    },
  },

  stock: {
    title: 'Stock & losses',
    description: 'Stock on hand now in every place (at cost), deliveries received and stock lost in the period.',
    async load() {
      const s = await get<StockReport>('/reports/stock')
      const flow = (label: string): Column[] => [
        { key: 'name', label }, { key: 'qty', label: 'Qty', format: 'num', total: true }, { key: 'value', label: 'Value at cost', format: 'usd', total: true },
      ]
      return [
        {
          title: 'Stock on hand now',
          columns: [{ key: 'name', label: 'Place' }, { key: 'kind', label: 'Type' }, { key: 'qty', label: 'Qty', format: 'num', total: true }, { key: 'value', label: 'Value at cost', format: 'usd', total: true }],
          rows: s.places.map((p) => ({ ...p, kind: { main: 'main shop', branch: 'branch', warehouse: 'warehouse', transit: 'On the road' }[p.kind] ?? p.kind })),
        },
        { title: 'Deliveries received, by supplier', note: 'Value only where the cost was entered.', columns: flow('Supplier'), rows: s.received.map((r) => ({ ...r })) },
        { title: 'Stock lost, by reason', columns: flow('Reason'), rows: s.losses.map((r) => ({ ...r })) },
      ]
    },
  },

  expenses: {
    title: 'Expenses',
    description: 'Shop costs in the period by category, and profit after expenses.',
    async load() {
      const [r, s] = await Promise.all([get<ExpenseReport>('/reports/expenses'), get<ReportSummary>('/reports/summary')])
      return [
        {
          title: 'Profit after expenses',
          columns: [{ key: 'label', label: 'What' }, { key: 'amount', label: 'Amount', format: 'signed' }],
          rows: [
            { label: 'Net sales', amount: s.net_sales },
            { label: 'Gross profit', amount: s.profit },
            { label: 'Expenses', amount: -s.expenses },
            { label: 'Profit after expenses', amount: s.net_profit },
          ],
        },
        {
          title: 'By category',
          columns: [{ key: 'name', label: 'Category' }, { key: 'count', label: 'Entries', format: 'num', total: true }, { key: 'amount', label: 'Amount', format: 'usd', total: true }],
          rows: r.categories.map((c) => ({ ...c })),
          chart: { label: 'name', value: 'amount' },
        },
        {
          title: 'Every expense',
          columns: [
            { key: 'spent_on', label: 'Date' }, { key: 'category', label: 'Category' }, { key: 'note', label: 'Note' },
            { key: 'drawer', label: 'Paid from' }, { key: 'recorded_by', label: 'By' }, { key: 'amount', label: 'Amount', format: 'usd', total: true },
          ],
          rows: r.items.map((e) => ({ ...e, drawer: e.from_drawer ? 'cash drawer' : '' })) as unknown as Row[],
        },
      ]
    },
  },

  customers: {
    title: 'Customers',
    description: 'Customers who bought in the period, best first. Walk-in sales are not counted.',
    async load() {
      const rows = await get<CustomerReportRow[]>('/reports/customers')
      return [{
        columns: [
          { key: 'name', label: 'Customer' }, { key: 'phone', label: 'Phone' }, { key: 'visits', label: 'Visits', format: 'num', total: true },
          { key: 'spent', label: 'Spent', format: 'usd', total: true }, { key: 'points', label: 'Points now', format: 'num' },
          { key: 'last_visit', label: 'Last visit', format: 'datetime' },
        ],
        rows: rows.map((r) => ({ ...r })),
      }]
    },
  },
}

/** Order in the menu: [kind, label, section]. */
export const REPORT_MENU: [string, string, string][] = [
  ['products', 'Sales by product', 'Sales'],
  ['categories', 'Sales by category', 'Sales'],
  ['time', 'Sales by day & hour', 'Sales'],
  ['payments', 'Payment methods', 'Sales'],
  ['cashiers', 'Sales by cashier', 'Sales'],
  ['refunds', 'Refunds & voids', 'Checks'],
  ['discounts', 'Discounts', 'Checks'],
  ['shifts', 'Shifts & cash', 'Checks'],
  ['stock', 'Stock & losses', 'Stock & customers'],
  ['customers', 'Customers', 'Stock & customers'],
  ['expenses', 'Expenses', 'Costs'],
]
