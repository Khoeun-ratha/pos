from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import require_perm
from ..excel import report_workbook
from ..models import Expense, LocationStock, Product, Refund, RefundItem, Sale, SaleItem, StockMovement, StockTransfer, StockTransferItem, User
from ..pricing import allocate, share_of
from ..schemas import DayAmount, HourAmount, NameAmount, ReportSummary

router = APIRouter(prefix="/api/reports", tags=["reports"])

METHOD_NAMES = {"cash": "Cash", "card": "Card", "khqr": "KHQR"}


def _ranked(rows: dict[str, dict], top: int | None = None) -> list[NameAmount]:
    ranked = sorted((NameAmount(name=name, **values) for name, values in rows.items()), key=lambda r: r.amount, reverse=True)
    return ranked[:top] if top else ranked


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date, datetime, datetime]:
    date_from = date_from or date.today()
    date_to = date_to or date_from
    if date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_to is before date_from")
    return date_from, date_to, datetime.combine(date_from, time.min), datetime.combine(date_to + timedelta(days=1), time.min)


@router.get("/summary", response_model=ReportSummary)
def summary(date_from: date | None = None, date_to: date | None = None,
            db: Session = Depends(get_db), _: User = Depends(require_perm("reports"))):
    """Sales in the date range (inclusive). All amounts are USD cents."""
    return build_summary(db, date_from, date_to)


@router.get("/export")
def export(date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db), _: User = Depends(require_perm("reports"))):
    """The same report as an Excel file, with every product, every receipt and the stock losses."""
    report = build_summary(db, date_from, date_to, top=None)
    _, _, start, end = _period(date_from, date_to)
    sales = db.scalars(select(Sale).where(Sale.created_at >= start, Sale.created_at < end).order_by(Sale.created_at, Sale.id)).all()
    losses = db.scalars(select(StockMovement).where(
        StockMovement.kind == "write_off", StockMovement.created_at >= start, StockMovement.created_at < end,
    ).order_by(StockMovement.id)).all()
    spent = db.scalars(select(Expense).where(Expense.spent_on >= report.date_from, Expense.spent_on <= report.date_to)
                       .order_by(Expense.spent_on, Expense.id)).all()
    data = report_workbook(report, sales, losses, store_settings.load(db)["store_name"], spent)
    name = f"sales-{report.date_from}" + ("" if report.date_from == report.date_to else f"-to-{report.date_to}")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={name}.xlsx"},
    )


def item_totals(db: Session, sales: list[Sale], refunds: list[Refund]) -> tuple[dict[str, dict], int, int]:
    """Per product (by the name on the receipt): qty, amount, cost and revenue without tax, for the sales and the
    refunds of a period. Also the VAT and discount given back by those refunds. Shared by the summary and the
    product report, so their figures always agree."""
    category_names = {p.id: p.category_name for p in db.scalars(select(Product))}
    rows: dict[str, dict] = defaultdict(lambda: {"product_id": None, "category": "", "qty": 0, "amount": 0, "cost": 0, "revenue": 0})

    def add(item: SaleItem, qty: int, amount: int, item_tax: int) -> None:
        row = rows[item.product_name]
        row["product_id"] = row["product_id"] or item.product_id
        row["category"] = category_names.get(item.product_id) or "Uncategorized"
        row["qty"] += qty
        row["amount"] += amount
        row["cost"] += item.unit_cost * qty
        row["revenue"] += amount - item_tax

    for sale in sales:
        for item in sale.items:
            add(item, item.qty, item.line_total, item.tax)

    tax_back = discount_back = 0
    if refunds:
        lines = db.scalars(select(RefundItem).where(RefundItem.refund_id.in_([r.id for r in refunds]))).all()
        items = {i.id: i for i in db.scalars(select(SaleItem).where(SaleItem.id.in_({l.sale_item_id for l in lines})))}
        # units of the same item refunded earlier, so tax and discount shares add up exactly
        before: dict[int, int] = {}
        done: dict[int, int] = defaultdict(int)
        for line in db.scalars(select(RefundItem).where(RefundItem.sale_item_id.in_(items)).order_by(RefundItem.id)):
            before[line.id] = done[line.sale_item_id]
            done[line.sale_item_id] += line.qty
        for line in lines:
            item = items[line.sale_item_id]
            line_tax = share_of(before[line.id], line.qty, item.tax, item.qty)
            tax_back += line_tax
            discount_back += share_of(before[line.id], line.qty, item.discount, item.qty)
            add(item, -line.qty, -line.amount, -line_tax)
    return rows, tax_back, discount_back


def period_sales(db: Session, start: datetime, end: datetime) -> tuple[list[Sale], list[Refund]]:
    """A sale counts on the day it was made, a refund on the day it was given back."""
    sales = db.scalars(select(Sale).where(Sale.created_at >= start, Sale.created_at < end)).unique().all()
    refunds = db.scalars(select(Refund).where(Refund.created_at >= start, Refund.created_at < end).order_by(Refund.id)).all()
    return list(sales), list(refunds)


def build_summary(db: Session, date_from: date | None, date_to: date | None, top: int | None = 10) -> ReportSummary:
    date_from, date_to, start, end = _period(date_from, date_to)

    # One rule everywhere: a sale counts on the day it was made, a refund on the day it was given back,
    # so a refund never changes a report that was already printed and every total below agrees.
    sales, refunds = period_sales(db, start, end)
    items, tax_back, discount_back = item_totals(db, sales, refunds)

    gross = sum(s.total for s in sales)
    refunded = sum(r.amount for r in refunds)
    tax = sum(s.tax_total for s in sales) - tax_back
    discounts = sum(s.discount_total for s in sales) - discount_back
    cost = sum(r["cost"] for r in items.values())
    revenue = sum(r["revenue"] for r in items.values())  # without tax, for the profit
    by_payment: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0})
    by_cashier: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0})
    by_category: dict[str, dict] = defaultdict(lambda: {"qty": 0, "amount": 0})
    by_product = {name: {"qty": r["qty"], "amount": r["amount"]} for name, r in items.items()}
    for r in items.values():
        by_category[r["category"]]["qty"] += r["qty"]
        by_category[r["category"]]["amount"] += r["amount"]
    by_day: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    by_hour = [[0, 0] for _ in range(24)]

    for sale in sales:
        for p in sale.payments:
            name = METHOD_NAMES.get(p.method, p.method)
            by_payment[name]["count"] += 1
            by_payment[name]["amount"] += p.amount_usd
        if sale.change_due:  # change is always given in cash, once per sale
            by_payment[METHOD_NAMES["cash"]]["amount"] -= sale.change_due
        by_cashier[sale.cashier_name]["count"] += 1
        by_cashier[sale.cashier_name]["amount"] += sale.total
        for row in (by_day[sale.created_at.date()], by_hour[sale.created_at.hour]):
            row[0] += 1
            row[1] += sale.total

    if refunds:
        for refund in refunds:
            sale = refund.sale
            if refund.cash_amount:
                by_payment[METHOD_NAMES["cash"]]["amount"] -= refund.cash_amount
            other = [p for p in sale.payments if p.method != "cash"]
            for p, part in zip(other, allocate(refund.amount - refund.cash_amount, [p.amount_usd for p in other])):
                by_payment[METHOD_NAMES.get(p.method, p.method)]["amount"] -= part
            by_cashier[sale.cashier_name]["amount"] -= refund.amount
            by_day[refund.created_at.date()][1] -= refund.amount
            by_hour[refund.created_at.hour][1] -= refund.amount

    stock_costs = dict(db.execute(
        select(StockMovement.kind, func.sum(StockMovement.change * StockMovement.unit_cost))
        .where(StockMovement.created_at >= start, StockMovement.created_at < end,
               StockMovement.kind.in_(("stock_in", "write_off")), StockMovement.unit_cost.is_not(None))
        .group_by(StockMovement.kind)
    ).all())
    stock_value = db.scalar(
        select(func.coalesce(func.sum(Product.stock_qty * Product.cost), 0))
        .where(Product.is_active.is_(True), Product.track_stock.is_(True), Product.stock_qty > 0)
    )
    # plus branches / warehouses, and goods on the road between them
    stock_value += db.scalar(
        select(func.coalesce(func.sum(LocationStock.qty * Product.cost), 0))
        .join(Product, Product.id == LocationStock.product_id)
        .where(Product.is_active.is_(True), Product.track_stock.is_(True), LocationStock.qty > 0)
    )
    stock_value += db.scalar(
        select(func.coalesce(func.sum(StockTransferItem.qty * StockTransferItem.unit_cost), 0))
        .join(StockTransfer, StockTransfer.id == StockTransferItem.transfer_id)
        .where(StockTransfer.status == "in_transit")
    )

    expenses = int(db.scalar(select(func.coalesce(func.sum(Expense.amount), 0))
                             .where(Expense.spent_on >= date_from, Expense.spent_on <= date_to)) or 0)

    def used(rows: dict[str, dict]) -> dict[str, dict]:
        return {name: row for name, row in rows.items() if row["qty"] or row["amount"]}

    return ReportSummary(
        date_from=date_from,
        date_to=date_to,
        sales_count=len(sales),
        gross_sales=gross,
        refunds=refunded,
        net_sales=gross - refunded,
        tax=tax,
        discounts=discounts,
        cost=cost,
        profit=revenue - cost,
        average_sale=gross // len(sales) if sales else 0,
        purchases=int(stock_costs.get("stock_in") or 0),
        stock_losses=-int(stock_costs.get("write_off") or 0),
        stock_value=int(stock_value),
        expenses=expenses,
        net_profit=revenue - cost - expenses,
        by_payment=_ranked(by_payment),
        by_cashier=_ranked(by_cashier),
        by_category=_ranked(used(by_category)),
        top_products=_ranked(used(by_product), top=top),
        by_day=[DayAmount(day=d, count=v[0], amount=v[1]) for d, v in sorted(by_day.items())],
        by_hour=[HourAmount(hour=h, count=v[0], amount=v[1]) for h, v in enumerate(by_hour)],
    )
