"""Held orders ("park" a cart while the customer fetches something). Kept on the server so they survive a page
refresh or logout and any till of the same outlet can finish them (a branch's held orders stay at the branch);
resuming takes the order off the list."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import approve, audit, get_current_user
from ..models import Customer, ParkedOrder, User
from ..schemas import ParkedAssignIn, ParkedIn, ParkedOut
from .sales import outlet_of, price_cart

router = APIRouter(prefix="/api/parked", tags=["sales"])


class DiscardIn(BaseModel):
    manager_pin: str | None = None


def _out(order: ParkedOrder) -> ParkedOut:
    return ParkedOut(
        id=order.id, label=order.label, user_id=order.user_id, cashier_name=order.cashier_name,
        customer_id=order.customer_id, customer_name=order.customer_name, cart=json.loads(order.cart),
        total=order.total, created_at=order.created_at,
        assigned_to_id=order.assigned_to_id, assigned_to_name=order.assigned_to_name,
    )


def _here(db: Session, user: User) -> int | None:
    """The outlet the user's till is at (None: the main shop)."""
    location = outlet_of(db, user)
    return location.id if location else None


def _get(db: Session, order_id: int, user: User) -> ParkedOrder:
    order = db.get(ParkedOrder, order_id)
    if order is None or order.location_id != _here(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This held order was already resumed on another till")
    return order


@router.get("", response_model=list[ParkedOut])
def list_parked(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The held orders of the outlet this till is at."""
    here = _here(db, user)
    query = select(ParkedOrder).where(ParkedOrder.location_id.is_(None) if here is None else ParkedOrder.location_id == here)
    return [_out(o) for o in db.scalars(query.order_by(ParkedOrder.id))]


def _staff(db: Session, user_id: int | None, location_id: int | None) -> User | None:
    """Who a held order is sent to: someone who can work at the order's outlet."""
    if user_id is None:
        return None
    staff = db.get(User, user_id)
    if staff is None or not staff.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cashier not found")
    if staff.location_id is not None and staff.location_id != location_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{staff.full_name or staff.username} works at {staff.location_name}")
    return staff


@router.post("", response_model=ParkedOut, status_code=201)
def park(body: ParkedIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, _, totals = price_cart(db, body, store_settings.load(db))
    if body.customer_id is not None and db.get(Customer, body.customer_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Customer not found")
    here = _here(db, user)
    to = _staff(db, body.assigned_to_id, here)
    cart = body.model_dump(include={"items", "discount_type", "discount_value"})
    order = ParkedOrder(user_id=user.id, customer_id=body.customer_id, label=body.label.strip(), location_id=here,
                        cart=json.dumps(cart), total=totals.total, assigned_to_id=to.id if to else None)
    db.add(order)
    if to and to.id != user.id:
        audit(db, user, "order_transfer", f"Held order (${totals.total / 100:.2f}) sent to {to.username}")
    db.commit()
    db.refresh(order)
    return _out(order)


@router.post("/{order_id}/assign", response_model=ParkedOut)
def assign(order_id: int, body: ParkedAssignIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Passes a held order to another cashier's till (or back to any till)."""
    order = _get(db, order_id, user)
    to = _staff(db, body.assigned_to_id, order.location_id)
    order.assigned_to_id = to.id if to else None
    audit(db, user, "order_transfer", f"Held order (${order.total / 100:.2f}) sent to {to.username if to else 'any till'}")
    db.commit()
    db.refresh(order)
    return _out(order)


@router.post("/{order_id}/resume", response_model=ParkedOut)
def resume(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hands the order back to the till and removes it, so two tills can never finish the same order."""
    order = _get(db, order_id, user)
    out = _out(order)
    db.delete(order)
    db.commit()
    return out


@router.post("/{order_id}/discard", status_code=204)
def discard(order_id: int, body: DiscardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Throwing away a held order is a void: cashiers need a manager PIN and it is logged."""
    order = _get(db, order_id, user)
    approver = approve(db, user, body.manager_pin)
    items = json.loads(order.cart)["items"]
    by = "" if approver.id == user.id else f", approved by {approver.username}"
    audit(db, user, "void", f"Held order discarded: {len(items)} line(s) (${order.total / 100:.2f}){by}")
    db.delete(order)
    db.commit()
