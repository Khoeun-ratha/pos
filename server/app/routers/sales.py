from collections import Counter
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import approve, audit, get_current_user, is_manager
from ..models import Customer, Product, Refund, RefundItem, Sale, SaleItem, Payment, Shift, User, now
from ..pricing import CartTotals, LineInput, calculate, div_round, khr_to_usd_cents, share_of, usd_cents_to_khr
from ..receipt import render
from ..schemas import CartIn, QuoteLineOut, QuoteOut, RefundIn, RefundOut, SaleCreate, SaleOut, SaleSummaryOut, VoidIn
from .inventory import move_stock

router = APIRouter(prefix="/api/sales", tags=["sales"])


def bad_request(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def sale_out(sale: Sale) -> SaleOut:
    out = SaleOut.model_validate(sale)
    out.change_due_khr = usd_cents_to_khr(sale.change_due, sale.exchange_rate)
    return out


def sale_cash(sale: Sale) -> int:
    """Cash the drawer kept for this sale: cash paid minus change."""
    cash = sum(p.amount_usd for p in sale.payments if p.method == "cash") - sale.change_due
    return min(max(cash, 0), sale.total)


def open_shift_of(db: Session, user: User) -> Shift | None:
    return db.scalar(select(Shift).where(Shift.user_id == user.id, Shift.closed_at.is_(None)))


def shift_at(db: Session, user: User, when: datetime) -> Shift | None:
    """The user's shift that was open at `when`: an offline sale belongs to the drawer it was paid into."""
    return db.scalar(
        select(Shift)
        .where(Shift.user_id == user.id, Shift.opened_at <= when, or_(Shift.closed_at.is_(None), Shift.closed_at >= when))
        .order_by(Shift.id.desc())
        .limit(1)
    )


def price_cart(db: Session, cart: CartIn, cfg: dict[str, str], offline: bool = False) -> tuple[list[Product], list[int], CartTotals]:
    """Products, unit prices and totals. The server's prices count, except for an offline sale, which keeps
    the prices the customer was charged (and may contain a product deactivated since)."""
    ids = {item.product_id for item in cart.items}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    for item in cart.items:
        product = products.get(item.product_id)
        if product is None:
            raise bad_request(f"Product {item.product_id} does not exist")
        if not product.is_active and not offline:
            raise bad_request(f"{product.name} is no longer for sale")

    prices = [i.unit_price if offline and i.unit_price is not None else products[i.product_id].price for i in cart.items]
    lines = [LineInput(price, i.qty, i.discount_type, i.discount_value) for price, i in zip(prices, cart.items)]
    totals = calculate(
        lines,
        cart.discount_type,
        cart.discount_value,
        store_settings.get_int(cfg, "tax_rate_bp"),
        store_settings.get_bool(cfg, "tax_inclusive"),
    )
    return [products[i.product_id] for i in cart.items], prices, totals


def _has_discount(cart: CartIn) -> bool:
    return bool(cart.discount_type and cart.discount_value) or any(i.discount_type and i.discount_value for i in cart.items)


@router.post("/quote", response_model=QuoteOut)
def quote(body: CartIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Totals for the cart without saving anything (the screen shows these while ringing up)."""
    cfg = store_settings.load(db)
    products, prices, totals = price_cart(db, body, cfg)
    rate = store_settings.get_int(cfg, "exchange_rate")
    return QuoteOut(
        subtotal=totals.subtotal,
        discount_total=totals.discount_total,
        tax_total=totals.tax_total,
        total=totals.total,
        total_khr=usd_cents_to_khr(totals.total, rate),
        exchange_rate=rate,
        lines=[
            QuoteLineOut(product_id=p.id, name=p.name, qty=i.qty, unit_price=price,
                         discount=line.discount, tax=line.tax, line_total=line.total)
            for p, price, i, line in zip(products, prices, body.items, totals.lines)
        ],
    )


@router.post("", response_model=SaleOut, status_code=201)
def create_sale(body: SaleCreate, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.client_uuid:
        existing = db.scalar(select(Sale).where(Sale.client_uuid == body.client_uuid))
        if existing:  # already synced from an offline device: return the original
            response.status_code = status.HTTP_200_OK
            return sale_out(existing)

    cfg = store_settings.load(db)
    rate = body.exchange_rate if body.offline and body.exchange_rate else store_settings.get_int(cfg, "exchange_rate")
    products, prices, totals = price_cart(db, body, cfg, offline=body.offline)

    # A standard till: no selling before the cash drawer is counted. An offline sale already happened,
    # so it goes to the shift that was open at that moment (or none) instead of being refused.
    created_at = body.created_at.replace(tzinfo=None, microsecond=0) if body.created_at else now()
    shift = shift_at(db, user, created_at) if body.offline else open_shift_of(db, user)
    if shift is None and not body.offline:
        raise bad_request("Open a shift before selling: count the cash drawer first")

    approver = approve(db, user, body.manager_pin) if _has_discount(body) else None

    customer = None
    if body.customer_id is not None:
        customer = db.get(Customer, body.customer_id)
        if customer is None:
            raise bad_request("Customer not found")

    # payments
    paid = non_cash = 0
    has_khr = False
    payments: list[Payment] = []
    for p in body.payments:
        amount_usd = p.amount if p.currency == "USD" else khr_to_usd_cents(p.amount, rate)
        has_khr |= p.currency == "KHR"
        paid += amount_usd
        if p.method != "cash":
            non_cash += amount_usd
        payments.append(Payment(method=p.method, currency=p.currency, amount=p.amount, amount_usd=amount_usd,
                                reference=(p.reference or "").strip() or None))
    if non_cash > totals.total:
        raise bad_request("Card / QR payments cannot be more than the total")
    shortfall = totals.total - paid
    # riel cash is rounded to the 100-riel note, so a shortfall under 100 riel is accepted
    if shortfall > 0 and not (has_khr and shortfall * rate < 100 * 100):
        raise bad_request(f"Not enough paid: ${shortfall / 100:.2f} still due")

    # stock (an offline sale was already handed over, so it is never refused)
    if not body.offline and not store_settings.get_bool(cfg, "allow_negative_stock"):
        needed = Counter()
        for product, item in zip(products, body.items):
            needed[product.id] += item.qty
        for product in {p.id: p for p in products}.values():
            if product.track_stock and product.stock_qty < needed[product.id]:
                raise bad_request(f"Not enough stock for {product.name} (have {product.stock_qty})")

    prefix = created_at.strftime("%Y%m%d")
    count_today = db.scalar(select(func.count()).select_from(Sale).where(Sale.receipt_no.like(f"{prefix}-%")))

    sale = Sale(
        client_uuid=body.client_uuid,
        user_id=user.id,
        shift_id=shift.id if shift else None,
        customer_id=customer.id if customer else None,
        subtotal=totals.subtotal,
        discount_total=totals.discount_total,
        tax_total=totals.tax_total,
        total=totals.total,
        paid_total=paid,
        change_due=max(0, paid - totals.total),
        exchange_rate=rate,
        note=body.note,
        created_at=created_at,
        payments=payments,
        items=[
            SaleItem(product_id=p.id, product_name=p.name, qty=i.qty, unit_price=price, unit_cost=p.cost,
                     discount=line.discount, tax=line.tax, line_total=line.total, note=i.note)
            for p, price, i, line in zip(products, prices, body.items, totals.lines)
        ],
    )
    for attempt in range(5):  # two tills finishing at the same moment can pick the same number
        sale.receipt_no = f"{prefix}-{count_today + 1 + attempt:04d}"
        try:
            with db.begin_nested():
                db.add(sale)
                db.flush()
            break
        except IntegrityError:
            existing = body.client_uuid and db.scalar(select(Sale).where(Sale.client_uuid == body.client_uuid))
            if existing:  # the same offline sale arrived twice at once
                response.status_code = status.HTTP_200_OK
                return sale_out(existing)
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not save the sale, please try again")

    for product, item in zip(products, body.items):
        if product.track_stock:
            move_stock(db, product, -item.qty, "sale", user, reference=sale.receipt_no)

    if customer:
        customer.points += totals.total // 100 * store_settings.get_int(cfg, "loyalty_points_per_usd")

    if approver:
        audit(db, user, "discount", f"{sale.receipt_no}: ${totals.discount_total / 100:.2f} approved by {approver.username}")
    if body.offline:
        changed = [f"{p.name} ${price / 100:.2f} (now ${p.price / 100:.2f})" for p, price in zip(products, prices) if price != p.price]
        if changed:
            audit(db, user, "offline_sale", f"{sale.receipt_no} synced with the phone's prices: " + ", ".join(changed))
    db.commit()
    db.refresh(sale)
    return sale_out(sale)


@router.post("/void", status_code=204)
def record_void(body: VoidIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Items taken off an unpaid order. Cashiers need a manager PIN; every void lands in the activity log."""
    approver = approve(db, user, body.manager_pin)
    what = ", ".join(f"{i.qty} x {i.name}" for i in body.items)
    amount = sum(i.amount for i in body.items)
    label = {"line": "Item voided", "clear": "Order cleared", "parked": "Held order discarded"}[body.kind]
    by = "" if approver.id == user.id else f", approved by {approver.username}"
    audit(db, user, "void", f"{label}: {what} (${amount / 100:.2f}){by}")
    db.commit()


@router.get("", response_model=list[SaleSummaryOut])
def list_sales(
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Sale)
    if not is_manager(user):
        query = query.where(Sale.user_id == user.id)
    if date_from:
        query = query.where(Sale.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(Sale.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if q:
        query = query.where(Sale.receipt_no.contains(q))
    return db.scalars(query.order_by(Sale.id.desc()).limit(limit).offset(offset)).all()


def _visible_sale(db: Session, sale_id: int, user: User) -> Sale:
    sale = db.get(Sale, sale_id)
    if sale is None or (not is_manager(user) and sale.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found")
    return sale


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return sale_out(_visible_sale(db, sale_id, user))


@router.get("/{sale_id}/receipt", response_class=PlainTextResponse)
def receipt(sale_id: int, width: int = Query(42, ge=24, le=64), reprint: bool = False,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """`reprint=true` for any receipt shown after the sale itself: it is marked as a copy and logged."""
    sale = _visible_sale(db, sale_id, user)
    if reprint:
        audit(db, user, "receipt_reprint", sale.receipt_no)
        db.commit()
    return render(sale, store_settings.load(db), width, reprint=reprint)


@router.post("/{sale_id}/refund", response_model=RefundOut)
def refund(sale_id: int, body: RefundIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sale not found")
    approver = approve(db, user, body.manager_pin)

    items_by_id = {item.id: item for item in sale.items}
    if body.items:
        wanted = Counter()
        for r in body.items:
            if r.sale_item_id not in items_by_id:
                raise bad_request(f"Item {r.sale_item_id} is not on receipt {sale.receipt_no}")
            wanted[r.sale_item_id] += r.qty
    else:
        wanted = Counter({i.id: i.qty - i.refunded_qty for i in sale.items if i.qty > i.refunded_qty})
    if not wanted:
        raise bad_request("Nothing left to refund on this receipt")

    record = Refund(sale_id=sale.id, user_id=user.id, approved_by_id=approver.id, reason=body.reason, amount=0)
    shift = open_shift_of(db, user)
    record.shift_id = shift.id if shift else None
    db.add(record)
    db.flush()

    total = 0
    for item_id, qty in wanted.items():
        item = items_by_id[item_id]
        remaining = item.qty - item.refunded_qty
        if qty > remaining:
            raise bad_request(f"Only {remaining} of {item.product_name} can be refunded")
        # the last unit takes whatever is left so rounding never refunds more than was paid
        amount = item.line_total - item.refunded_amount if qty == remaining else div_round(item.line_total * qty, item.qty)
        item.refunded_qty += qty
        item.refunded_amount += amount
        total += amount
        db.add(RefundItem(refund_id=record.id, sale_item_id=item.id, qty=qty, amount=amount))
        product = db.get(Product, item.product_id) if item.product_id else None
        if product and product.track_stock:
            move_stock(db, product, qty, "refund", user, reference=sale.receipt_no, note=body.reason)

    record.amount = total
    # money goes back the way it was paid: only the cash part leaves the drawer
    record.cash_amount = share_of(sale.refunded_total, total, sale_cash(sale), sale.total)
    if record.cash_amount and shift is None:
        raise bad_request(f"Open a shift first: ${record.cash_amount / 100:.2f} cash comes out of the drawer")

    if sale.customer:  # take back the loyalty points earned on the refunded part
        per_usd = store_settings.get_int(store_settings.load(db), "loyalty_points_per_usd")
        kept = sale.total - sale.refunded_total
        lost = kept // 100 * per_usd - (kept - total) // 100 * per_usd
        sale.customer.points = max(0, sale.customer.points - lost)

    sale.refunded_total += total
    sale.status = "refunded" if all(i.refunded_qty == i.qty for i in sale.items) else "partially_refunded"
    audit(db, user, "refund", f"{sale.receipt_no}: ${total / 100:.2f} ({body.reason}) approved by {approver.username}")
    db.commit()
    db.refresh(sale)
    return RefundOut(refund_id=record.id, amount=total, sale=sale_out(sale))
