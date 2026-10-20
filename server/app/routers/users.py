from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, get_current_user, require_admin
from ..models import User
from ..schemas import StaffOut, UserCreate, UserOut, UserUpdate
from ..security import hash_secret

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.username)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_secret(body.password),
        pin_hash=hash_secret(body.pin) if body.pin else None,
        role=body.role,
    )
    db.add(user)
    audit(db, admin, "user_create", f"{body.username} ({body.role})")
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate or demote yourself")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password:
        user.password_hash = hash_secret(body.password)
    if body.pin:
        user.pin_hash = hash_secret(body.pin)
    if body.role:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    audit(db, admin, "user_update", user.username)
    db.commit()
    return user
