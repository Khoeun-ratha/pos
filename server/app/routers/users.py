from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, get_current_user, require_perm
from ..models import ROLE_ADMIN, ROLE_CASHIER, User
from ..schemas import StaffOut, UserCreate, UserOut, UserUpdate
from ..security import hash_pin, hash_secret
from .inventory import get_branch

router = APIRouter(prefix="/api/users", tags=["users"])
# the admin manages everyone; a role given "staff" (managers by default) manages the cashiers only
staff_perm = require_perm("staff")


def _check_may_manage(actor: User, role: str) -> None:
    if actor.role != ROLE_ADMIN and role != ROLE_CASHIER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the admin can manage managers and admins")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(staff_perm)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.username)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(staff_perm)):
    _check_may_manage(admin, body.role)
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_secret(body.password),
        pin_hash=hash_pin(body.pin) if body.pin else None,
        role=body.role,
        location=get_branch(db, body.location_id),
    )
    db.add(user)
    audit(db, admin, "user_create", f"{body.username} ({body.role})")
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(staff_perm)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    _check_may_manage(admin, user.role)
    if body.role:
        _check_may_manage(admin, body.role)
    if user.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate or demote yourself")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password:
        user.password_hash = hash_secret(body.password)
    if body.pin:
        user.pin_hash = hash_pin(body.pin)
    if body.role:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    changed = [name for name, value in (("name", body.full_name), ("password", body.password), ("PIN", body.pin),
                                        ("role", body.role), ("active", body.is_active)) if value is not None]
    if "location_id" in body.model_fields_set and body.location_id != user.location_id:
        user.location = get_branch(db, body.location_id)
        changed.append(f"works at {user.location.name if user.location else 'any outlet'}")
    audit(db, admin, "user_update", f"{user.username}: {', '.join(changed)}")
    db.commit()
    return user
