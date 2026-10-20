"""Held orders ("park" a cart while the customer fetches something). Kept on the server so they survive a page
refresh or logout and any till can finish them; resuming takes the order off the list."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import approve, audit, get_current_user
from ..models import Customer, ParkedOrder, User
from ..schemas import ParkedIn, ParkedOut
from .sales import price_cart

router = APIRouter(prefix="/api/parked", tags=["sales"])


class DiscardIn(BaseModel):
    manager_pin: str | None = None


def _out(order: ParkedOrder) -> ParkedOut:
    return ParkedOut(
        id=order.id, label=order.label, user_id=order.user_id, cashier_name=order.cashier_name,
        customer_id=order.customer_id, customer_name=order.customer_name, cart=json.loads(order.cart),
        total=order.total, created_at=order.created_at,
    )


def _get(db: Session, order_id: int) -> ParkedOrder:
    order = db.get(ParkedOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This held order was already resumed on another till")
    return order


@router.get("", response_model=list[ParkedOut])
def list_parked(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_out(o) for o in db.scalars(select(ParkedOrder).order_by(ParkedOrder.id))]


@router.post("", response_model=ParkedOut, status_code=201)
def park(body: ParkedIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, _, totals = price_cart(db, body, store_settings.load(db))
    if body.customer_id is not None and db.get(Customer, body.customer_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Customer not found")
    cart = body.model_dump(include={"items", "discount_type", "discount_value"})
    order = ParkedOrder(user_id=user.id, customer_id=body.customer_id, label=body.label.strip(),
                        cart=json.dumps(cart), total=totals.total)
    db.add(order)
    db.commit()
    db.refresh(order)
    return _out(order)


@router.post("/{order_id}/resume", response_model=ParkedOut)
def resume(order_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Hands the order back to the till and removes it, so two tills can never finish the same order."""
    order = _get(db, order_id)
    out = _out(order)
    db.delete(order)
    db.commit()
    return out


@router.post("/{order_id}/discard", status_code=204)
def discard(order_id: int, body: DiscardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Throwing away a held order is a void: cashiers need a manager PIN and it is logged."""
    order = _get(db, order_id)
    approver = approve(db, user, body.manager_pin)
    items = json.loads(order.cart)["items"]
    by = "" if approver.id == user.id else f", approved by {approver.username}"
    audit(db, user, "void", f"Held order discarded: {len(items)} line(s) (${order.total / 100:.2f}){by}")
    db.delete(order)
    db.commit()
