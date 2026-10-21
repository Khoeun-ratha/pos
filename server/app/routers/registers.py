"""Registers: the shop's tills / counters, each with its own cash drawer. A shift opens on one register, and a register
has at most one open shift. Each stands in the main shop or a branch and sells from that outlet's stock; staff with a
home branch open shifts only on its registers. The admin adds, moves, renames and retires them (Store settings)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, get_current_user, require_admin
from ..models import Register, Shift, User
from ..schemas import RegisterIn, RegisterOut, RegisterUpdate
from .inventory import get_branch

router = APIRouter(prefix="/api/registers", tags=["shifts"])


def open_shifts(db: Session, lock: bool = False) -> dict[int, Shift]:
    """Register id -> the shift open on it. `lock` reads what is committed right now (see lock_tills)."""
    query = select(Shift).where(Shift.closed_at.is_(None), Shift.register_id.is_not(None))
    return {s.register_id: s for s in db.scalars(query.with_for_update() if lock else query)}


def lock_tills(db: Session) -> None:
    """Shifts open one at a time: two tills pressing Open together (or a double tap) cannot both take the same
    drawer, or give one person two shifts. Checks made after this must read with lock=True."""
    db.scalars(select(Register.id).with_for_update()).all()


def _out(register: Register, shift: Shift | None) -> RegisterOut:
    return RegisterOut.model_validate(register).model_copy(update={
        "open_shift_id": shift.id if shift else None,
        "open_by": (shift.user.full_name or shift.user.username) if shift else None,
    })


def check_works_at(user: User, register: Register) -> None:
    """Staff with a home branch work only at its registers."""
    if user.location_id is not None and register.location_id != user.location_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{user.full_name or user.username} works at {user.location_name}: {register.name} is elsewhere")


def free_register(db: Session, register_id: int | None, user: User) -> Register:
    """The register a new shift opens on: the one asked for, or else the first free one where `user` works.
    Call lock_tills first."""
    busy = open_shifts(db, lock=True)
    if register_id is not None:
        register = db.get(Register, register_id)
        if register is None or not register.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Register not found")
        check_works_at(user, register)
        if register.id in busy:
            who = busy[register.id].user
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{register.name} is already open ({who.full_name or who.username})")
        return register
    query = select(Register).where(Register.is_active.is_(True)).order_by(Register.id)
    if user.location_id is not None:
        query = query.where(Register.location_id == user.location_id)
    for register in db.scalars(query):
        if register.id not in busy:
            return register
    where = f" at {user.location_name}" if user.location_id is not None else ""
    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"Every register{where} is in use: close a shift first, or add a register in Store settings")


def _unique(db: Session, name: str, register_id: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the register a name, e.g. Counter 2")
    same = db.scalar(select(Register).where(func.lower(Register.name) == name.lower()))
    if same is not None and same.id != register_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"There is already a register called {same.name}")
    return name


@router.get("", response_model=list[RegisterOut])
def list_registers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    busy = open_shifts(db)
    return [_out(r, busy.get(r.id)) for r in db.scalars(select(Register).order_by(Register.id))]


@router.post("", response_model=RegisterOut, status_code=201)
def create_register(body: RegisterIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    location = get_branch(db, body.location_id)
    register = Register(name=_unique(db, body.name), location=location)
    db.add(register)
    audit(db, admin, "register_create", register.name + (f" at {location.name}" if location else ""))
    db.commit()
    return _out(register, None)


@router.patch("/{register_id}", response_model=RegisterOut)
def update_register(register_id: int, body: RegisterUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    register = db.get(Register, register_id)
    if register is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Register not found")
    shift = open_shifts(db).get(register.id)
    changes = []
    if body.name is not None and body.name.strip() != register.name:
        name = _unique(db, body.name, register.id)
        changes.append(f"renamed {register.name} -> {name}")
        register.name = name
    if body.is_active is False and register.is_active:
        if shift is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{register.name} has an open shift: close it first")
        if db.scalar(select(func.count()).select_from(Register).where(Register.is_active.is_(True))) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The shop needs at least one register")
        register.is_active = False
        changes.append(f"{register.name} retired")
    elif body.is_active and not register.is_active:
        register.is_active = True
        changes.append(f"{register.name} back in use")
    if "location_id" in body.model_fields_set and body.location_id != register.location_id:
        if shift is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{register.name} has an open shift: close it first")
        location = get_branch(db, body.location_id)
        register.location = location
        changes.append(f"{register.name} moved to {location.name if location else 'the main shop'}")
    if changes:
        audit(db, admin, "register_update", "; ".join(changes))
    db.commit()
    return _out(register, shift)
