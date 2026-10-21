from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import permissions, store_settings
from ..database import get_db
from ..deps import audit, get_current_user, require_perm, sees_all_sales
from ..models import CashMovement, Refund, Register, Sale, Shift, User, now
from ..pricing import khr_to_usd_cents
from ..security import verify_secret
from ..schemas import CashMovementIn, ShiftCloseIn, ShiftHandoverIn, ShiftHandoverOut, ShiftOpenIn, ShiftReport
from .registers import check_works_at, free_register, lock_tills
from .sales import open_shift_of, same_outlet

router = APIRouter(prefix="/api/shifts", tags=["shifts"])


def report(db: Session, shift: Shift) -> ShiftReport:
    """Cash figures are USD cents; KHR payments are counted at the rate of each sale."""
    sales = db.scalars(select(Sale).where(Sale.shift_id == shift.id)).all()
    by_method = {"cash": 0, "card": 0, "khqr": 0}
    for sale in sales:
        for p in sale.payments:
            by_method[p.method] += p.amount_usd
        by_method["cash"] -= sale.change_due

    movements = db.scalars(select(CashMovement).where(CashMovement.shift_id == shift.id)).all()
    cash_in = sum(m.amount for m in movements if m.amount > 0)
    cash_out = -sum(m.amount for m in movements if m.amount < 0)
    cash_refunds = db.scalar(select(func.coalesce(func.sum(Refund.cash_amount), 0)).where(Refund.shift_id == shift.id))

    expected = shift.opening_cash + by_method["cash"] + cash_in - cash_out - cash_refunds
    if shift.closed_at is not None and shift.expected_cash is not None:
        expected = shift.expected_cash
    handed_from = db.get(Shift, shift.handed_from_id) if shift.handed_from_id else None

    return ShiftReport(
        id=shift.id,
        user_id=shift.user_id,
        cashier_name=shift.user.full_name or shift.user.username,
        register_id=shift.register_id,
        register_name=shift.register.name if shift.register else None,
        location_id=shift.register.location_id if shift.register else None,
        location_name=shift.register.location_name if shift.register else None,
        opened_at=shift.opened_at,
        closed_at=shift.closed_at,
        is_open=shift.closed_at is None,
        sales_count=len(sales),
        opening_cash=shift.opening_cash,
        cash_sales=by_method["cash"],
        card_sales=by_method["card"],
        khqr_sales=by_method["khqr"],
        cash_in=cash_in,
        cash_out=cash_out,
        cash_refunds=cash_refunds,
        expected_cash=expected,
        counted_cash=shift.counted_cash,
        variance=None if shift.counted_cash is None else shift.counted_cash - expected,
        note=shift.note,
        handed_to_name=(shift.handed_to.full_name or shift.handed_to.username) if shift.handed_to else None,
        handed_from_name=(handed_from.user.full_name or handed_from.user.username) if handed_from else None,
    )


def take_cash(db: Session, shift: Shift, amount: int) -> None:
    """Refuse taking more cash out than the drawer should hold: it cannot be paid, and the count would go below zero."""
    have = report(db, shift).expected_cash
    if amount > have:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Only ${max(have, 0) / 100:.2f} is in the cash drawer: ${amount / 100:.2f} cannot come out")


def shift_outlet(shift: Shift) -> int | None:
    """The outlet of the shift's register (None: the main shop)."""
    return shift.register.location_id if shift.register else None


def at_outlet(query, location_id: int | None):
    """Shifts of one outlet: its registers' (the main shop's include shifts from before registers)."""
    if location_id is None:
        return query.outerjoin(Register, Register.id == Shift.register_id).where(Register.location_id.is_(None))
    return query.join(Register, Register.id == Shift.register_id).where(Register.location_id == location_id)


def _require_open(db: Session, user: User) -> Shift:
    shift = open_shift_of(db, user)
    if shift is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You have no open shift")
    return shift


@router.get("/current", response_model=ShiftReport | None)
def current(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = open_shift_of(db, user)
    return report(db, shift) if shift else None


@router.post("/open", response_model=ShiftReport, status_code=201)
def open_shift(body: ShiftOpenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lock_tills(db)
    if open_shift_of(db, user, lock=True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You already have an open shift")
    register = free_register(db, body.register_id, user)
    shift = Shift(user_id=user.id, opening_cash=body.opening_cash, register=register)
    db.add(shift)
    audit(db, user, "shift_open", f"{register.name}, opening cash ${body.opening_cash / 100:.2f}")
    db.commit()
    db.refresh(shift)
    return report(db, shift)


@router.post("/current/cash", response_model=ShiftReport)
def cash_movement(body: CashMovementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.amount == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Amount cannot be 0")
    shift = _require_open(db, user)
    if body.amount < 0:
        take_cash(db, shift, -body.amount)
    db.add(CashMovement(shift_id=shift.id, user_id=user.id, amount=body.amount, reason=body.reason))
    audit(db, user, "cash_in" if body.amount > 0 else "cash_out", f"${abs(body.amount) / 100:.2f} {body.reason}")
    db.commit()
    return report(db, shift)


def _count_and_close(db: Session, shift: Shift, body: ShiftCloseIn) -> None:
    rate = store_settings.get_int(store_settings.load(db), "exchange_rate")
    shift.expected_cash = report(db, shift).expected_cash
    shift.counted_cash = body.counted_usd + khr_to_usd_cents(body.counted_khr, rate)
    shift.closed_at = now()
    shift.note = body.note


@router.post("/current/close", response_model=ShiftReport)
def close_shift(body: ShiftCloseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = _require_open(db, user)
    _count_and_close(db, shift, body)
    audit(db, user, "shift_close", f"expected ${shift.expected_cash / 100:.2f} counted ${shift.counted_cash / 100:.2f}")
    db.commit()
    return report(db, shift)


@router.post("/current/handover", response_model=ShiftHandoverOut)
def handover(body: ShiftHandoverIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cashier change without emptying the drawer: this shift closes with the counted cash (over / short is
    on the outgoing cashier) and the next cashier's shift opens with exactly that cash. The next cashier
    types their own PIN to agree with the count."""
    shift = _require_open(db, user)
    nxt = db.get(User, body.to_user_id)
    if nxt is None or not nxt.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose who takes over the drawer")
    if nxt.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose another cashier to take over")
    if shift.register is not None:
        check_works_at(nxt, shift.register)
    if nxt.pin_hash is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{nxt.username} has no PIN yet: ask the admin to set one")
    if not verify_secret(body.pin, nxt.pin_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Wrong PIN for {nxt.username}")
    lock_tills(db)
    if open_shift_of(db, nxt, lock=True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{nxt.username} already has an open shift")

    _count_and_close(db, shift, body)
    shift.handed_to = nxt
    opened = Shift(user_id=nxt.id, opening_cash=shift.counted_cash, handed_from_id=shift.id, register_id=shift.register_id)
    db.add(opened)
    audit(db, user, "shift_handover",
          f"to {nxt.username}: expected ${shift.expected_cash / 100:.2f} counted ${shift.counted_cash / 100:.2f}")
    db.commit()
    db.refresh(opened)
    return ShiftHandoverOut(closed=report(db, shift), opened=report(db, opened))


@router.get("", response_model=list[ShiftReport])
def list_shifts(limit: int = Query(50, le=500), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every cashier's shifts for managers (reports / all sales permission); a cashier gets their own."""
    query = select(Shift)
    if not permissions.has(db, user, "reports", "all_sales"):
        query = query.where(Shift.user_id == user.id)
    elif user.location_id is not None:  # a branch manager: their branch's tills
        query = at_outlet(query, user.location_id)
    return [report(db, s) for s in db.scalars(query.order_by(Shift.id.desc()).limit(limit))]


@router.post("/{shift_id}/close", response_model=ShiftReport)
def close_other_shift(shift_id: int, body: ShiftCloseIn, db: Session = Depends(get_db),
                      manager: User = Depends(require_perm("reports"))):
    """A manager counts and closes a shift its cashier left open (went home, phone lost, account deactivated)."""
    shift = db.get(Shift, shift_id)
    if shift is None or not same_outlet(shift_outlet(shift), manager):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shift not found")
    if shift.closed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This shift is already closed")
    _count_and_close(db, shift, body)
    if not shift.note:
        shift.note = f"Closed by {manager.full_name or manager.username}"
    audit(db, manager, "shift_close",
          f"{shift.user.username}'s shift closed by {manager.username}: "
          f"expected ${shift.expected_cash / 100:.2f} counted ${shift.counted_cash / 100:.2f}")
    db.commit()
    return report(db, shift)


@router.get("/{shift_id}", response_model=ShiftReport)
def get_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.get(Shift, shift_id)
    if shift is None or (shift.user_id != user.id and not (sees_all_sales(db, user) and same_outlet(shift_outlet(shift), user))):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shift not found")
    return report(db, shift)
