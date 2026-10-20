from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import audit, get_current_user, is_manager, require_manager
from ..models import CashMovement, Refund, Sale, Shift, User, now
from ..pricing import khr_to_usd_cents
from ..schemas import CashMovementIn, ShiftCloseIn, ShiftOpenIn, ShiftReport
from .sales import open_shift_of

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

    return ShiftReport(
        id=shift.id,
        user_id=shift.user_id,
        cashier_name=shift.user.full_name or shift.user.username,
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
    )


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
    if open_shift_of(db, user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You already have an open shift")
    shift = Shift(user_id=user.id, opening_cash=body.opening_cash)
    db.add(shift)
    audit(db, user, "shift_open", f"opening cash ${body.opening_cash / 100:.2f}")
    db.commit()
    db.refresh(shift)
    return report(db, shift)


@router.post("/current/cash", response_model=ShiftReport)
def cash_movement(body: CashMovementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.amount == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Amount cannot be 0")
    shift = _require_open(db, user)
    db.add(CashMovement(shift_id=shift.id, user_id=user.id, amount=body.amount, reason=body.reason))
    audit(db, user, "cash_in" if body.amount > 0 else "cash_out", f"${abs(body.amount) / 100:.2f} {body.reason}")
    db.commit()
    return report(db, shift)


@router.post("/current/close", response_model=ShiftReport)
def close_shift(body: ShiftCloseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = _require_open(db, user)
    rate = store_settings.get_int(store_settings.load(db), "exchange_rate")
    live = report(db, shift)
    shift.expected_cash = live.expected_cash
    shift.counted_cash = body.counted_usd + khr_to_usd_cents(body.counted_khr, rate)
    shift.closed_at = now()
    shift.note = body.note
    audit(db, user, "shift_close", f"expected ${shift.expected_cash / 100:.2f} counted ${shift.counted_cash / 100:.2f}")
    db.commit()
    return report(db, shift)


@router.get("", response_model=list[ShiftReport])
def list_shifts(limit: int = Query(50, le=500), db: Session = Depends(get_db), _: User = Depends(require_manager)):
    return [report(db, s) for s in db.scalars(select(Shift).order_by(Shift.id.desc()).limit(limit))]


@router.get("/{shift_id}", response_model=ShiftReport)
def get_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.get(Shift, shift_id)
    if shift is None or (not is_manager(user) and shift.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shift not found")
    return report(db, shift)
