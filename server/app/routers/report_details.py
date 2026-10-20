"""Reports by feature (the Reports menu): products, cashiers, payments, refunds and voids, discounts, shifts, stock,
customers. Same period rule as the summary: a sale counts on the day it was made, a refund on the day it was given
back, so these pages add up to the summary."""
import re
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_perm
from ..models import (AuditLog, Location, LocationStock, Product, RefundItem, Sale, SaleItem, Shift, StockMovement,
                      StockTransfer, StockTransferItem, Supplier, User)
from ..schemas import (CashierReportRow, CustomerReportRow, DiscountReportRow, ExpenseCategoryOut, ExpenseOut, ExpenseReport,
                       LogReportRow, PaymentReportRow,
                       ProductReportRow, RefundReportRow, ShiftReport, StockFlowRow, StockPlaceRow, StockReport)
from .expenses import expenses_between
from .reports import METHOD_NAMES, _period, build_summary, item_totals, period_sales
from .shifts import report as shift_report

router = APIRouter(prefix="/api/reports", tags=["reports"])
reports_perm = require_perm("reports")


def _name(user: User | None) -> str:
    return (user.full_name or user.username) if user else ""


@router.get("/products", response_model=list[ProductReportRow])
def products(date_from: date | None = None, date_to: date | None = None,
             db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Every product sold (or returned) in the period, with its cost and profit."""
    *_, start, end = _period(date_from, date_to)
    rows, _, _ = item_totals(db, *period_sales(db, start, end))
    out = [ProductReportRow(product_id=r["product_id"], name=name, category=r["category"], qty=r["qty"], sales=r["amount"],
                            cost=r["cost"], profit=r["revenue"] - r["cost"])
           for name, r in rows.items() if r["qty"] or r["amount"]]
    return sorted(out, key=lambda r: r.sales, reverse=True)


@router.get("/cashiers", response_model=list[CashierReportRow])
def cashiers(date_from: date | None = None, date_to: date | None = None,
             db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    *_, start, end = _period(date_from, date_to)
    sales, refunds = period_sales(db, start, end)
    rows: dict[str, dict] = defaultdict(lambda: dict.fromkeys(("sales_count", "gross", "refunds", "discounts", "voids", "shifts", "over_short"), 0))
    for s in sales:
        row = rows[s.cashier_name]
        row["sales_count"] += 1
        row["gross"] += s.total
        row["discounts"] += s.discount_total
    for r in refunds:  # against the cashier of the sale, as in the summary
        rows[r.sale.cashier_name]["refunds"] += r.amount
    for log in db.scalars(select(AuditLog).where(AuditLog.action == "void", AuditLog.created_at >= start, AuditLog.created_at < end)):
        rows[_name(log.user)]["voids"] += 1
    for shift in db.scalars(select(Shift).where(Shift.closed_at >= start, Shift.closed_at < end, Shift.counted_cash.is_not(None))):
        row = rows[_name(shift.user)]
        row["shifts"] += 1
        row["over_short"] += shift.counted_cash - (shift.expected_cash or 0)
    out = [CashierReportRow(name=name, net=r["gross"] - r["refunds"],
                            average_sale=r["gross"] // r["sales_count"] if r["sales_count"] else 0, **r)
           for name, r in rows.items() if name]
    return sorted(out, key=lambda r: r.net, reverse=True)


@router.get("/payments", response_model=list[PaymentReportRow])
def payments(date_from: date | None = None, date_to: date | None = None,
             db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Money in by method: what was handed over in each currency, and the net after change and refunds."""
    summary = build_summary(db, date_from, date_to)
    *_, start, end = _period(date_from, date_to)
    sales, _ = period_sales(db, start, end)
    rows = {name: {"count": 0, "received_usd": 0, "received_khr": 0} for name in METHOD_NAMES.values()}
    for s in sales:
        for p in s.payments:
            row = rows[METHOD_NAMES.get(p.method, p.method)]
            row["count"] += 1
            row["received_usd" if p.currency == "USD" else "received_khr"] += p.amount
    net = {r.name: r.amount for r in summary.by_payment}
    out = [PaymentReportRow(method=name, net=net.get(name, 0), **r) for name, r in rows.items() if r["count"] or net.get(name)]
    if net.get("Riel rounding"):  # the summary's row, so these rows add up to the net sales too
        out.append(PaymentReportRow(method="Riel rounding", count=0, received_usd=0, received_khr=0, net=net["Riel rounding"]))
    return out


@router.get("/refunds", response_model=list[RefundReportRow])
def refunds(date_from: date | None = None, date_to: date | None = None,
            db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    *_, start, end = _period(date_from, date_to)
    _, found = period_sales(db, start, end)
    users = {u.id: u for u in db.scalars(select(User))}
    lines: dict[int, list[str]] = defaultdict(list)
    if found:
        for line, item in db.execute(select(RefundItem, SaleItem).join(SaleItem, SaleItem.id == RefundItem.sale_item_id)
                                     .where(RefundItem.refund_id.in_([r.id for r in found]))):
            lines[line.refund_id].append(f"{line.qty} x {item.product_name}")
    return [RefundReportRow(id=r.id, created_at=r.created_at, receipt_no=r.sale.receipt_no, sale_id=r.sale_id,
                            refunded_by=_name(users.get(r.user_id)), approved_by=_name(users.get(r.approved_by_id)),
                            reason=r.reason, items=", ".join(lines[r.id]), amount=r.amount, cash_amount=r.cash_amount)
            for r in reversed(found)]


@router.get("/voids", response_model=list[LogReportRow])
def voids(date_from: date | None = None, date_to: date | None = None,
          db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Items and orders taken off before payment (from the activity log)."""
    *_, start, end = _period(date_from, date_to)
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "void", AuditLog.created_at >= start, AuditLog.created_at < end)
                      .order_by(AuditLog.id.desc()))
    return [LogReportRow(created_at=log.created_at, user=_name(log.user), detail=log.detail) for log in logs]


@router.get("/discounts", response_model=list[DiscountReportRow])
def discounts(date_from: date | None = None, date_to: date | None = None,
              db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    *_, start, end = _period(date_from, date_to)
    sales = db.scalars(select(Sale).where(Sale.created_at >= start, Sale.created_at < end, Sale.discount_total > 0)
                       .order_by(Sale.id.desc())).unique().all()
    approvers: dict[str, str] = {}
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "discount", AuditLog.created_at >= start, AuditLog.created_at < end))
    for log in logs:  # "20261020-0003: $0.50 approved by manager"
        if m := re.match(r"(\S+): .* approved by (\S+)", log.detail):
            approvers[m[1]] = m[2]
    return [DiscountReportRow(created_at=s.created_at, receipt_no=s.receipt_no, sale_id=s.id, cashier=s.cashier_name,
                              approved_by=approvers.get(s.receipt_no, ""), subtotal=s.subtotal, discount=s.discount_total,
                              total=s.total)
            for s in sales]


@router.get("/shifts", response_model=list[ShiftReport])
def shifts(date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Shifts opened in the period, with their cash count."""
    *_, start, end = _period(date_from, date_to)
    found = db.scalars(select(Shift).where(Shift.opened_at >= start, Shift.opened_at < end).order_by(Shift.id.desc()))
    return [shift_report(db, s) for s in found]


@router.get("/stock", response_model=StockReport)
def stock(date_from: date | None = None, date_to: date | None = None,
          db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Stock on hand now in every place (at cost), and what came in and was lost in the period."""
    *_, start, end = _period(date_from, date_to)
    counted = (Product.is_active.is_(True), Product.track_stock.is_(True))
    qty, value = db.execute(select(func.coalesce(func.sum(Product.stock_qty), 0), func.coalesce(func.sum(Product.stock_qty * Product.cost), 0))
                            .where(*counted, Product.stock_qty > 0)).one()
    places = [StockPlaceRow(name="Main shop", kind="main", qty=qty, value=value)]
    for loc in db.scalars(select(Location).where(Location.is_active.is_(True)).order_by(Location.name)):
        qty, value = db.execute(
            select(func.coalesce(func.sum(LocationStock.qty), 0), func.coalesce(func.sum(LocationStock.qty * Product.cost), 0))
            .join(Product, Product.id == LocationStock.product_id)
            .where(LocationStock.location_id == loc.id, LocationStock.qty > 0, *counted)
        ).one()
        places.append(StockPlaceRow(name=loc.name, kind=loc.kind, qty=qty, value=value))
    qty, value = db.execute(
        select(func.coalesce(func.sum(StockTransferItem.qty), 0), func.coalesce(func.sum(StockTransferItem.qty * StockTransferItem.unit_cost), 0))
        .join(StockTransfer, StockTransfer.id == StockTransferItem.transfer_id).where(StockTransfer.status == "in_transit")
    ).one()
    if qty:
        places.append(StockPlaceRow(name="On the road", kind="transit", qty=qty, value=value))

    received: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    losses: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    moves = db.execute(select(StockMovement.kind, StockMovement.change, StockMovement.unit_cost, StockMovement.note, Supplier.name)
                       .outerjoin(Supplier, Supplier.id == StockMovement.supplier_id)
                       .where(StockMovement.kind.in_(("stock_in", "write_off")), StockMovement.created_at >= start, StockMovement.created_at < end))
    for kind, change, unit_cost, note, supplier in moves:
        row = received[supplier or "No supplier"] if kind == "stock_in" else losses[(note or "Other").split(":")[0]]
        row[0] += abs(change)
        row[1] += abs(change) * (unit_cost or 0)

    def flows(rows: dict[str, list[int]]) -> list[StockFlowRow]:
        return sorted((StockFlowRow(name=n, qty=q, value=v) for n, (q, v) in rows.items()), key=lambda r: r.value, reverse=True)

    return StockReport(places=places, received=flows(received), losses=flows(losses))


@router.get("/expenses", response_model=ExpenseReport)
def expenses(date_from: date | None = None, date_to: date | None = None,
             db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Expenses dated in the period, by category and one by one."""
    date_from, date_to, *_ = _period(date_from, date_to)
    items = expenses_between(db, date_from, date_to)
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e in items:
        by_category[e.category][0] += 1
        by_category[e.category][1] += e.amount
    categories = sorted((ExpenseCategoryOut(name=n, count=c, amount=a) for n, (c, a) in by_category.items()), key=lambda r: r.amount, reverse=True)
    return ExpenseReport(categories=categories, items=[ExpenseOut.model_validate(e) for e in reversed(items)])


@router.get("/customers", response_model=list[CustomerReportRow])
def customers(date_from: date | None = None, date_to: date | None = None,
              db: Session = Depends(get_db), _: User = Depends(reports_perm)):
    """Customers who bought in the period, best first. Walk-in sales are left out."""
    *_, start, end = _period(date_from, date_to)
    sales, refunds = period_sales(db, start, end)
    rows: dict[int, dict] = {}
    for s in sales:
        if s.customer is None:
            continue
        row = rows.setdefault(s.customer_id, {"customer": s.customer, "visits": 0, "spent": 0, "last_visit": None})
        row["visits"] += 1
        row["spent"] += s.total
        row["last_visit"] = max(filter(None, (row["last_visit"], s.created_at)))
    for r in refunds:
        if r.sale.customer_id in rows:
            rows[r.sale.customer_id]["spent"] -= r.amount
    out = [CustomerReportRow(customer_id=cid, name=r["customer"].name, phone=r["customer"].phone, visits=r["visits"],
                             spent=r["spent"], points=r["customer"].points, last_visit=r["last_visit"])
           for cid, r in rows.items()]
    return sorted(out, key=lambda r: r.spent, reverse=True)
