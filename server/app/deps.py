import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import ROLE_ADMIN, ROLE_MANAGER, AuditLog, User
from .security import decode_token, verify_secret

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if cred is None:
        raise unauthorized
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return dependency


require_admin = require_roles(ROLE_ADMIN)
require_manager = require_roles(ROLE_ADMIN, ROLE_MANAGER)


def is_manager(user: User) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_MANAGER)


def find_manager_by_pin(db: Session, pin: str) -> User | None:
    managers = db.scalars(
        select(User).where(User.is_active.is_(True), User.role.in_((ROLE_ADMIN, ROLE_MANAGER)), User.pin_hash.is_not(None))
    )
    return next((m for m in managers if verify_secret(pin, m.pin_hash)), None)


def approve(db: Session, user: User, manager_pin: str | None) -> User:
    """Return the approving manager: the user themself if a manager, else whoever owns the PIN."""
    if is_manager(user):
        return user
    manager = find_manager_by_pin(db, manager_pin) if manager_pin else None
    if manager is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager approval required (invalid or missing manager PIN)")
    return manager


def audit(db: Session, user: User | None, action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, detail=detail))
