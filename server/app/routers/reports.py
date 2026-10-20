from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import require_manager
from ..excel import report_workbook
from ..models import Product, Refund, RefundItem, Sale, SaleItem, StockMovement, User
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
            db: Session = Depends(get_db), _: User = Depends(require_manager)):
    """Sales in the date range (inclusive). All amounts are USD cents."""
    return build_summary(db, date_from, date_to)


@router.get("/export")
def export(date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db), _: User = Depends(require_manager)):
    """The same report as an Excel file, with every product, every receipt and the stock losses."""
    report = build_summary(db, date_from, date_to, top=None)
    _, _, start, end = _period(date_from, date_to)
    sales = db.scalars(select(Sale).where(Sale.created_at >= start, Sale.created_at < end).order_by(Sale.created_at, Sale.id)).all()
    losses = db.scalars(select(StockMovement).where(
        StockMovement.kind == "write_off", StockMovement.created_at >= start, StockMovement.created_at < end,
    ).order_by(StockMovement.id)).all()
    data = report_workbook(report, sales, losses, store_settings.load(db)["store_name"])
    name = f"sales-{report.date_from}" + ("" if report.date_from == report.date_to else f"-to-{report.date_to}")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={name}.xlsx"},
    )


def build_summary(db: Session, date_from: date | None, date_to: date | None, top: int | None = 10) -> ReportSummary:
    date_from, date_to, start, end = _period(date_from, date_to)

    # One rule everywhere: a sale counts on the day it was made, a refund on the day it was given back,
    # so a refund never changes a report that was already printed and every total below agrees.
    sales = db.scalars(select(Sale).where(Sale.created_at >= start, Sale.created_at < end)).all()
    refunds = db.scalars(select(Refund).where(Refund.created_at >= start, Refund.created_at < end).order_by(Refund.id)).all()
    category_names = {p.id: p.category_name for p in db.scalars(select(Product))}

    gross = sum(s.total for s in sales)
    refunded = sum(r.amount for r in refunds)
    tax = sum(s.tax_total for s in sales)
    discounts = sum(s.discount_total for s in sales)
    cost = revenue = 0  # revenue without tax, for the profit
    by_payment: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0})
    by_cashier: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0})
    by_category: dict[str, dict] = defaultdict(lambda: {"qty": 0, "amount": 0})
    by_product: dict[str, dict] = defaultdict(lambda: {"qty": 0, "amount": 0})
    by_day: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    by_hour = [[0, 0] for _ in range(24)]

    def add_item(item: SaleItem, qty: int, amount: int, item_tax: int) -> None:
        nonlocal cost, revenue
        cost += item.unit_cost * qty
        revenue += amount - item_tax
        category = category_names.get(item.product_id) or "Uncategorized"
        for row in (by_product[item.product_name], by_category[category]):
            row["qty"] += qty
            row["amount"] += amount

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
        for item in sale.items:
            add_item(item, item.qty, item.line_total, item.tax)

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
            tax -= line_tax
            discounts -= share_of(before[line.id], line.qty, item.discount, item.qty)
            add_item(item, -line.qty, -line.amount, -line_tax)

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
        by_payment=_ranked(by_payment),
        by_cashier=_ranked(by_cashier),
        by_category=_ranked(used(by_category)),
        top_products=_ranked(used(by_product), top=top),
        by_day=[DayAmount(day=d, count=v[0], amount=v[1]) for d, v in sorted(by_day.items())],
        by_hour=[HourAmount(hour=h, count=v[0], amount=v[1]) for h, v in enumerate(by_hour)],
    )
