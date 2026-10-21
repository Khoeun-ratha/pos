"""Shop expenses: rent, electricity, salaries, ice... An expense paid with cash from the drawer is also a cash-out of
the open shift, so the drawer count stays right; it can be changed or removed only while that shift is open."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, require_perm
from ..models import CashMovement, Expense, Shift, User
from ..schemas import ExpenseIn, ExpenseOut
from .sales import open_shift_of
from .shifts import take_cash

router = APIRouter(prefix="/api/expenses", tags=["expenses"])
expenses_perm = require_perm("expenses")

# offered in the form; any other name can be typed
DEFAULT_CATEGORIES = ["Rent", "Electricity", "Water", "Internet & phone", "Salaries", "Transport", "Ice & supplies",
                      "Repairs", "Cleaning", "Taxes & fees", "Other"]


def _describe(e: Expense) -> str:
    return f"${e.amount / 100:.2f} {e.category}" + (f" ({e.note})" if e.note else "")


def _reason(body: ExpenseIn) -> str:
    return (f"Expense: {body.category.strip()}" + (f", {body.note.strip()}" if body.note else ""))[:200]


def _get(db: Session, expense_id: int) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    return expense


def _drawer_still_open(db: Session, expense: Expense) -> CashMovement | None:
    """The cash movement of an expense paid from the drawer, if its shift is still open (None: not from the drawer)."""
    movement = expense.cash_movement
    if movement is None:
        return None
    shift = db.get(Shift, movement.shift_id)
    if shift is None or shift.closed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "It was paid from a cash drawer whose shift is closed: record a new expense to correct it")
    return movement


@router.get("", response_model=list[ExpenseOut])
def list_expenses(date_from: date | None = None, date_to: date | None = None, category: str | None = None,
                  db: Session = Depends(get_db), _: User = Depends(expenses_perm)):
    query = select(Expense)
    if date_from:
        query = query.where(Expense.spent_on >= date_from)
    if date_to:
        query = query.where(Expense.spent_on <= date_to)
    if category:
        query = query.where(Expense.category == category)
    return db.scalars(query.order_by(Expense.spent_on.desc(), Expense.id.desc()).limit(2000)).all()


@router.get("/categories", response_model=list[str])
def categories(db: Session = Depends(get_db), _: User = Depends(expenses_perm)):
    """The usual categories, then any other one already used."""
    used = db.scalars(select(Expense.category).group_by(Expense.category).order_by(func.count().desc())).all()
    return DEFAULT_CATEGORIES + [c for c in used if c not in DEFAULT_CATEGORIES]


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, db: Session = Depends(get_db), user: User = Depends(expenses_perm)):
    expense = Expense(spent_on=body.spent_on, category=body.category.strip(), amount=body.amount,
                      note=(body.note or "").strip() or None, user_id=user.id)
    if body.from_drawer:
        shift = open_shift_of(db, user)
        if shift is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Open a shift first to pay from the cash drawer")
        take_cash(db, shift, body.amount)
        expense.cash_movement = CashMovement(shift_id=shift.id, user_id=user.id, amount=-body.amount, reason=_reason(body))
    db.add(expense)
    audit(db, user, "expense", _describe(expense) + (" from the cash drawer" if body.from_drawer else ""))
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, body: ExpenseIn, db: Session = Depends(get_db), user: User = Depends(expenses_perm)):
    """Date, category, amount and note. Whether it came from the drawer stays as it was."""
    expense = _get(db, expense_id)
    before = _describe(expense)
    # the drawer's cash-out follows a new amount; that is only possible while its shift is open
    movement = _drawer_still_open(db, expense) if expense.amount != body.amount or expense.category != body.category else None
    expense.spent_on = body.spent_on
    expense.category = body.category.strip()
    expense.amount = body.amount
    expense.note = (body.note or "").strip() or None
    if movement is not None:
        if body.amount > -movement.amount:  # the extra comes out of the drawer too
            take_cash(db, db.get(Shift, movement.shift_id), body.amount + movement.amount)
        movement.amount = -body.amount
        movement.reason = _reason(body)
    audit(db, user, "expense_update", f"{before} -> {_describe(expense)}")
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(expenses_perm)):
    expense = _get(db, expense_id)
    movement = _drawer_still_open(db, expense)
    audit(db, user, "expense_delete", f"{expense.spent_on} {_describe(expense)}")
    db.delete(expense)
    if movement is not None:
        db.delete(movement)  # the cash goes back into the drawer count
    db.commit()


def expenses_between(db: Session, date_from: date, date_to: date) -> list[Expense]:
    return list(db.scalars(select(Expense).where(Expense.spent_on >= date_from, Expense.spent_on <= date_to)
                           .order_by(Expense.spent_on, Expense.id)))

