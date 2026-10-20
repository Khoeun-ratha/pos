from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, find_manager_by_pin, get_current_user
from ..models import User
from ..schemas import ApprovalOut, LoginIn, PinIn, PinLoginIn, TokenOut, UserOut
from ..security import create_token, verify_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue(db: Session, user: User, how: str) -> TokenOut:
    audit(db, user, "login", how)
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.role), user=UserOut.model_validate(user))


def _active_user(db: Session, username: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    return user if user and user.is_active else None


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = _active_user(db, body.username)
    if user is None or not verify_secret(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    return _issue(db, user, "password")


@router.post("/pin-login", response_model=TokenOut)
def pin_login(body: PinLoginIn, db: Session = Depends(get_db)):
    user = _active_user(db, body.username)
    if user is None or not verify_secret(body.pin, user.pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or PIN")
    return _issue(db, user, "pin")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/verify-manager-pin", response_model=ApprovalOut)
def verify_manager_pin(body: PinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Used by clients before manager-only actions such as voiding a cart line."""
    manager = find_manager_by_pin(db, body.pin)
    if manager is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid manager PIN")
    audit(db, user, "manager_approval", f"approved by {manager.username}")
    db.commit()
    return ApprovalOut(approved=True, manager_id=manager.id, manager_name=manager.full_name or manager.username)
