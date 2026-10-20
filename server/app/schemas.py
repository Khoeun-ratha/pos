"""API request/response shapes. Money is integer: USD cents, KHR riel.
Percent discounts are basis points (1000 = 10%)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "manager", "cashier"]
DiscountType = Literal["percent", "amount"]
PaymentMethod = Literal["cash", "card", "khqr"]
Currency = Literal["USD", "KHR"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------

class LoginIn(BaseModel):
    username: str
    password: str


class PinLoginIn(BaseModel):
    username: str
    pin: str


class PinIn(BaseModel):
    pin: str


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    has_pin: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ApprovalOut(BaseModel):
    approved: bool
    manager_id: int
    manager_name: str


class StaffOut(ORM):
    """Active users, for choosing who takes over a shift or a held order."""
    id: int
    username: str
    full_name: str
    role: str
    has_pin: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = ""
    password: str = Field(min_length=6)
    pin: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    role: Role = "cashier"


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=6)
    pin: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    role: Role | None = None
    is_active: bool | None = None


# ---------- catalog ----------

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class CategoryOut(ORM):
    id: int
    name: str
    sort_order: int


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = None
    barcode: str | None = None
    category_id: int | None = None
    price: int = Field(ge=0)
    cost: int = Field(default=0, ge=0)
    track_stock: bool = True
    low_stock_threshold: int = Field(default=5, ge=0)
    is_active: bool = True


class ProductCreate(ProductIn):
    stock_qty: int = Field(default=0, ge=0)


class ProductOut(ORM):
    id: int
    name: str
    sku: str | None
    barcode: str | None
    category_id: int | None
    category_name: str | None
    price: int
    cost: int
    track_stock: bool
    stock_qty: int
    low_stock_threshold: int
    is_active: bool
    image_url: str | None = None


class ImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str]


# ---------- inventory ----------

class StockChangeIn(BaseModel):
    product_id: int
    qty: int  # stock_in: amount received (> 0); adjustment: +/- change
    note: str | None = None
    location_id: int | None = None  # branch / warehouse; None = main shop


class StockInIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    unit_cost: int | None = Field(default=None, ge=0)  # price paid per unit; updates the product's average cost
    supplier_id: int | None = None
    note: str | None = Field(default=None, max_length=200)  # e.g. invoice number
    location_id: int | None = None  # branch / warehouse; None = main shop


class WriteOffIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    reason: Literal["damaged", "expired", "lost", "own_use"]
    note: str | None = Field(default=None, max_length=150)
    location_id: int | None = None  # branch / warehouse; None = main shop


class StockCountIn(BaseModel):
    product_id: int
    counted_qty: int = Field(ge=0)
    note: str | None = None
    location_id: int | None = None  # branch / warehouse; None = main shop


class StockMovementOut(ORM):
    id: int
    product_id: int
    product_name: str
    change: int
    balance: int
    kind: str
    reference: str | None
    note: str | None
    unit_cost: int | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    location_id: int | None = None
    location_name: str | None = None  # None = main shop
    created_at: datetime


# ---------- branches / warehouses and stock transfers ----------

class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["warehouse", "branch"] = "warehouse"
    address: str | None = Field(default=None, max_length=200)
    is_active: bool = True


class LocationOut(ORM):
    id: int
    name: str
    kind: str
    address: str | None
    is_active: bool


class LocationStockOut(BaseModel):
    product_id: int
    qty: int


class TransferItemIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)


class TransferIn(BaseModel):
    from_location_id: int | None = None  # None = main shop
    to_location_id: int | None = None
    items: list[TransferItemIn] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=200)


class TransferItemOut(ORM):
    product_id: int
    product_name: str
    qty: int
    unit_cost: int


class TransferOut(BaseModel):
    id: int
    transfer_no: str
    from_location_id: int | None
    from_name: str
    to_location_id: int | None
    to_name: str
    status: str  # in_transit | received | cancelled
    note: str | None
    created_by: str
    created_at: datetime
    closed_by: str | None
    closed_at: datetime | None
    items: list[TransferItemOut]
    total_qty: int
    total_cost: int


# ---------- suppliers ----------

class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=200)
    is_active: bool = True


class SupplierOut(ORM):
    id: int
    name: str
    phone: str | None
    note: str | None
    is_active: bool


# ---------- customers ----------

class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = None
    email: str | None = None


class CustomerOut(ORM):
    id: int
    name: str
    phone: str | None
    email: str | None
    points: int
    created_at: datetime
    # from their sales: receipts, money spent after refunds, last purchase
    visits: int = 0
    total_spent: int = 0
    last_visit: datetime | None = None


# ---------- sales ----------

class CartItemIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    discount_type: DiscountType | None = None
    discount_value: int = Field(default=0, ge=0)
    note: str | None = None
    unit_price: int | None = Field(default=None, ge=0)  # price the till showed; only used for offline sales


class CartIn(BaseModel):
    items: list[CartItemIn] = Field(min_length=1)
    discount_type: DiscountType | None = None
    discount_value: int = Field(default=0, ge=0)


class PaymentIn(BaseModel):
    method: PaymentMethod
    currency: Currency = "USD"
    amount: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=50)  # card approval code / KHQR transaction id


class SaleCreate(CartIn):
    payments: list[PaymentIn] = Field(min_length=1)
    customer_id: int | None = None
    note: str | None = None
    manager_pin: str | None = None  # needed when a cashier gives a discount
    client_uuid: str | None = Field(default=None, max_length=64)  # makes offline re-sync safe
    created_at: datetime | None = None  # time the sale really happened (offline sales)
    # Offline sale synced later: the customer already paid what the phone showed, so the server keeps the
    # phone's prices and exchange rate instead of today's, and never rejects it for stock or shift.
    offline: bool = False
    exchange_rate: int | None = Field(default=None, gt=0)


class QuoteLineOut(BaseModel):
    product_id: int
    name: str
    qty: int
    unit_price: int
    discount: int
    tax: int
    line_total: int


class QuoteOut(BaseModel):
    subtotal: int
    discount_total: int
    tax_total: int
    total: int
    total_khr: int
    exchange_rate: int
    lines: list[QuoteLineOut]


class SaleItemOut(ORM):
    id: int
    product_id: int | None
    product_name: str
    qty: int
    unit_price: int
    discount: int
    tax: int
    line_total: int
    refunded_qty: int
    refunded_amount: int
    note: str | None


class PaymentOut(ORM):
    method: str
    currency: str
    amount: int
    amount_usd: int
    reference: str | None = None


class SaleOut(ORM):
    id: int
    receipt_no: str
    client_uuid: str | None
    user_id: int
    cashier_name: str
    shift_id: int | None
    customer_id: int | None
    customer_name: str | None
    subtotal: int
    discount_total: int
    tax_total: int
    total: int
    paid_total: int
    change_due: int
    change_due_khr: int = 0
    exchange_rate: int
    refunded_total: int
    status: str
    note: str | None
    created_at: datetime
    items: list[SaleItemOut]
    payments: list[PaymentOut]


class SaleSummaryOut(ORM):
    id: int
    receipt_no: str
    cashier_name: str
    customer_name: str | None
    total: int
    refunded_total: int
    status: str
    created_at: datetime


class RefundItemIn(BaseModel):
    sale_item_id: int
    qty: int = Field(gt=0)


class ParkedIn(CartIn):
    customer_id: int | None = None
    label: str = Field(default="", max_length=100)
    assigned_to_id: int | None = None  # send it to this cashier's till


class ParkedAssignIn(BaseModel):
    assigned_to_id: int | None = None  # None = any till


class ParkedOut(ORM):
    id: int
    label: str
    user_id: int
    cashier_name: str
    customer_id: int | None
    customer_name: str | None
    cart: dict
    total: int
    created_at: datetime
    assigned_to_id: int | None = None
    assigned_to_name: str | None = None


class VoidLineIn(BaseModel):
    name: str = Field(max_length=200)
    qty: int = Field(gt=0)
    amount: int = Field(ge=0)


class VoidIn(BaseModel):
    """Items taken off an unpaid order, recorded so voids show in the activity log."""
    kind: Literal["line", "clear", "parked"]
    items: list[VoidLineIn] = Field(min_length=1)
    manager_pin: str | None = None


class RefundIn(BaseModel):
    items: list[RefundItemIn] = []  # empty = refund everything still refundable
    reason: str = Field(min_length=1, max_length=200)
    manager_pin: str | None = None


class RefundOut(BaseModel):
    refund_id: int
    amount: int
    sale: SaleOut


# ---------- shifts ----------

class ShiftOpenIn(BaseModel):
    opening_cash: int = Field(default=0, ge=0)


class CashMovementIn(BaseModel):
    amount: int  # positive = cash in, negative = cash out
    reason: str = Field(min_length=1, max_length=200)


class ShiftCloseIn(BaseModel):
    counted_usd: int = Field(default=0, ge=0)  # cents
    counted_khr: int = Field(default=0, ge=0)  # riel
    note: str | None = None


class ShiftHandoverIn(ShiftCloseIn):
    """Next cashier takes over the drawer: this shift closes with the count, theirs opens with it."""
    to_user_id: int
    pin: str = Field(min_length=1)  # the next cashier's own PIN: they agree with the count


class ShiftReport(BaseModel):
    id: int
    user_id: int
    cashier_name: str
    opened_at: datetime
    closed_at: datetime | None
    is_open: bool
    sales_count: int
    opening_cash: int
    cash_sales: int
    card_sales: int
    khqr_sales: int
    cash_in: int
    cash_out: int
    cash_refunds: int
    expected_cash: int
    counted_cash: int | None
    variance: int | None
    note: str | None
    handed_to_name: str | None = None  # closed by handing the drawer to this cashier
    handed_from_name: str | None = None  # opened by taking the drawer over from this cashier


class ShiftHandoverOut(BaseModel):
    closed: ShiftReport  # the shift that was handed over
    opened: ShiftReport  # the next cashier's shift


# ---------- reports ----------

class NameAmount(BaseModel):
    name: str
    qty: int = 0
    count: int = 0
    amount: int


class DayAmount(BaseModel):
    day: date
    count: int
    amount: int


class HourAmount(BaseModel):
    hour: int  # 0-23, shop time
    count: int
    amount: int


class ReportSummary(BaseModel):
    date_from: date
    date_to: date
    sales_count: int
    gross_sales: int
    refunds: int
    net_sales: int
    tax: int
    discounts: int
    cost: int
    profit: int
    average_sale: int
    purchases: int  # cost of stock received in the period (when the cost was entered)
    stock_losses: int  # cost of damaged / expired / lost stock written off in the period
    stock_value: int  # cost of all stock on hand now: main shop, branches / warehouses and transfers on the road
    expenses: int = 0  # shop expenses dated in the period
    net_profit: int = 0  # profit minus expenses
    by_payment: list[NameAmount]
    by_cashier: list[NameAmount]
    by_category: list[NameAmount]
    top_products: list[NameAmount]  # top 10 (all products in the Excel export)
    by_day: list[DayAmount]
    by_hour: list[HourAmount]  # always 24 entries, for the "busy hours" chart




# ---------- expenses ----------

class ExpenseIn(BaseModel):
    spent_on: date
    category: str = Field(min_length=1, max_length=50)
    amount: int = Field(gt=0)  # USD cents
    note: str | None = Field(default=None, max_length=200)
    from_drawer: bool = False  # paid with cash from the drawer of your open shift


class ExpenseOut(ORM):
    id: int
    spent_on: date
    category: str
    amount: int
    note: str | None
    from_drawer: bool
    recorded_by: str
    created_at: datetime


class ExpenseCategoryOut(BaseModel):
    name: str
    count: int
    amount: int


class ExpenseReport(BaseModel):
    categories: list[ExpenseCategoryOut]
    items: list[ExpenseOut]

# ---------- reports by feature (Reports menu) ----------

class ProductReportRow(BaseModel):
    product_id: int | None
    name: str
    category: str
    qty: int  # sold minus returned
    sales: int  # cents, VAT included
    cost: int
    profit: int  # sales without VAT minus cost


class CashierReportRow(BaseModel):
    name: str
    sales_count: int
    gross: int
    refunds: int
    net: int
    discounts: int
    average_sale: int
    voids: int  # items / orders taken off before payment
    shifts: int  # closed in the period
    over_short: int  # sum of the counted minus expected cash of those shifts


class PaymentReportRow(BaseModel):
    method: str  # Cash | Card | KHQR
    count: int
    received_usd: int  # cents paid in dollars
    received_khr: int  # riel paid in riel
    net: int  # cents, after change and refunds (as in the summary)


class RefundReportRow(BaseModel):
    id: int
    created_at: datetime
    receipt_no: str
    sale_id: int
    refunded_by: str
    approved_by: str
    reason: str
    items: str
    amount: int
    cash_amount: int


class LogReportRow(BaseModel):
    created_at: datetime
    user: str
    detail: str


class DiscountReportRow(BaseModel):
    created_at: datetime
    receipt_no: str
    sale_id: int
    cashier: str
    approved_by: str
    subtotal: int
    discount: int
    total: int


class StockPlaceRow(BaseModel):
    name: str
    kind: str  # main | branch | warehouse | transit
    qty: int
    value: int  # at cost


class StockFlowRow(BaseModel):
    name: str  # supplier, or write-off reason
    qty: int
    value: int


class StockReport(BaseModel):
    places: list[StockPlaceRow]
    received: list[StockFlowRow]  # by supplier, in the period
    losses: list[StockFlowRow]  # by reason, in the period


class CustomerReportRow(BaseModel):
    customer_id: int
    name: str
    phone: str | None
    visits: int
    spent: int  # net of refunds given in the period
    points: int
    last_visit: datetime | None

# ---------- settings / audit ----------

class SettingsOut(BaseModel):
    store_name: str
    store_address: str
    store_phone: str
    tax_rate_bp: int
    tax_inclusive: bool
    exchange_rate: int
    receipt_footer: str
    allow_negative_stock: bool
    loyalty_points_per_usd: int
    logo_url: str  # empty when no logo


class SettingsUpdate(BaseModel):
    store_name: str | None = None
    store_address: str | None = None
    store_phone: str | None = None
    tax_rate_bp: int | None = Field(default=None, ge=0, le=10000)
    tax_inclusive: bool | None = None
    exchange_rate: int | None = Field(default=None, gt=0)
    receipt_footer: str | None = None
    allow_negative_stock: bool | None = None
    loyalty_points_per_usd: int | None = Field(default=None, ge=0)


class PermissionOut(BaseModel):
    key: str
    label: str


class PermissionsOut(BaseModel):
    permissions: list[PermissionOut]  # every permission there is
    roles: dict[str, list[str]]  # admin / manager / cashier -> permission keys
    mine: list[str]  # the logged-in user's permissions


class PermissionsUpdate(BaseModel):
    manager: list[str]
    cashier: list[str]


class AuditOut(ORM):
    id: int
    user_id: int | None
    username: str | None
    action: str
    detail: str
    created_at: datetime
