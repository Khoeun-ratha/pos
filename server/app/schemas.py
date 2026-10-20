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


class StockInIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    unit_cost: int | None = Field(default=None, ge=0)  # price paid per unit; updates the product's average cost
    supplier_id: int | None = None
    note: str | None = Field(default=None, max_length=200)  # e.g. invoice number


class WriteOffIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0)
    reason: Literal["damaged", "expired", "lost", "own_use"]
    note: str | None = Field(default=None, max_length=150)


class StockCountIn(BaseModel):
    product_id: int
    counted_qty: int = Field(ge=0)
    note: str | None = None


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
    created_at: datetime


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
    stock_value: int  # cost of all stock on hand now
    by_payment: list[NameAmount]
    by_cashier: list[NameAmount]
    by_category: list[NameAmount]
    top_products: list[NameAmount]  # top 10 (all products in the Excel export)
    by_day: list[DayAmount]
    by_hour: list[HourAmount]  # always 24 entries, for the "busy hours" chart


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


class AuditOut(ORM):
    id: int
    user_id: int | None
    username: str | None
    action: str
    detail: str
    created_at: datetime
