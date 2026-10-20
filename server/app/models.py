"""Database tables. All money columns are integers: USD in cents, KHR in riel."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER)


def now() -> datetime:
    """Shop-local time (the server runs in the shop), second precision."""
    return datetime.now().replace(microsecond=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(100))
    pin_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_CASHIER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    @property
    def has_pin(self) -> bool:
        return self.pin_hash is not None


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    sku: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    price: Mapped[int] = mapped_column(Integer)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. /uploads/products/12-3f9a.webp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    category: Mapped[Category | None] = relationship(lazy="joined")

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opening_cash: Mapped[int] = mapped_column(Integer, default=0)
    expected_cash: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_cash: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(lazy="joined")


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer)  # positive = cash in, negative = cash out
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    client_uuid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    discount_total: Mapped[int] = mapped_column(Integer, default=0)
    tax_total: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    paid_total: Mapped[int] = mapped_column(Integer)
    change_due: Mapped[int] = mapped_column(Integer, default=0)
    exchange_rate: Mapped[int] = mapped_column(Integer)  # KHR per 1 USD
    refunded_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | partially_refunded | refunded
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    user: Mapped[User] = relationship(lazy="joined")
    customer: Mapped[Customer | None] = relationship(lazy="joined")
    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", lazy="selectin", order_by="SaleItem.id"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", lazy="selectin", order_by="Payment.id"
    )

    @property
    def cashier_name(self) -> str:
        return self.user.full_name or self.user.username

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200))
    qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[int] = mapped_column(Integer, default=0)
    discount: Mapped[int] = mapped_column(Integer, default=0)  # line discount + share of order discount
    tax: Mapped[int] = mapped_column(Integer, default=0)
    line_total: Mapped[int] = mapped_column(Integer)
    refunded_qty: Mapped[int] = mapped_column(Integer, default=0)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    sale: Mapped[Sale] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"))
    method: Mapped[str] = mapped_column(String(20))  # cash | card | khqr
    currency: Mapped[str] = mapped_column(String(3))  # USD | KHR
    amount: Mapped[int] = mapped_column(Integer)  # in the currency's unit (cents / riel)
    amount_usd: Mapped[int] = mapped_column(Integer)  # USD cents equivalent
    reference: Mapped[str | None] = mapped_column(String(50), nullable=True)  # card approval code / KHQR transaction id

    sale: Mapped[Sale] = relationship(back_populates="payments")


class ParkedOrder(Base):
    """A held cart ("customer went to fetch something"), kept on the server so it survives a page refresh
    and any till can finish it."""

    __tablename__ = "parked_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    label: Mapped[str] = mapped_column(String(100), default="")
    cart: Mapped[str] = mapped_column(Text)  # JSON: items + order discount, as sent to POST /api/sales
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    user: Mapped[User] = relationship(lazy="joined")
    customer: Mapped[Customer | None] = relationship(lazy="joined")

    @property
    def cashier_name(self) -> str:
        return self.user.full_name or self.user.username

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    cash_amount: Mapped[int] = mapped_column(Integer, default=0)  # part paid back from the cash drawer
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    sale: Mapped["Sale"] = relationship(lazy="joined")


class RefundItem(Base):
    __tablename__ = "refund_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey("refunds.id", ondelete="CASCADE"))
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id"))
    qty: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    change: Mapped[int] = mapped_column(Integer)
    balance: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # sale | refund | stock_in | adjustment | count | write_off
    reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)  # stock_in: price paid; write_off: cost lost
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    product: Mapped[Product] = relationship(lazy="joined")
    supplier: Mapped[Supplier | None] = relationship(lazy="joined")

    @property
    def product_name(self) -> str:
        return self.product.name

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.name if self.supplier else None


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    user: Mapped[User | None] = relationship(lazy="joined")

    @property
    def username(self) -> str | None:
        return self.user.username if self.user else None
