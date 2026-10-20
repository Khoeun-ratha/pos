from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import audit, get_current_user, require_admin
from ..images import InvalidImage, delete_logo, save_logo
from ..models import AuditLog, User
from ..schemas import AuditOut, SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api", tags=["admin"])


def _settings_out(values: dict[str, str]) -> SettingsOut:
    typed: dict = {}
    for key, value in values.items():
        if key in store_settings.INT_KEYS:
            typed[key] = int(value)
        elif key in store_settings.BOOL_KEYS:
            typed[key] = value.lower() == "true"
        else:
            typed[key] = value
    return SettingsOut(**typed)


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _settings_out(store_settings.load(db))


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    changes = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in body.model_dump(exclude_none=True).items()
    }
    store_settings.save(db, changes)
    audit(db, admin, "settings_update", ", ".join(f"{k}={v}" for k, v in changes.items()))
    db.commit()
    return _settings_out(store_settings.load(db))


@router.post("/settings/logo", response_model=SettingsOut)
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """JPG, PNG or WebP, up to 8 MB. Shown in the app and printed on receipts."""
    try:
        url = save_logo(await file.read())
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    old = store_settings.load(db)["logo_url"]
    store_settings.save(db, {"logo_url": url})
    audit(db, admin, "settings_update", "logo uploaded")
    db.commit()
    delete_logo(old)
    return _settings_out(store_settings.load(db))


@router.delete("/settings/logo", response_model=SettingsOut)
def remove_logo(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    old = store_settings.load(db)["logo_url"]
    store_settings.save(db, {"logo_url": ""})
    audit(db, admin, "settings_update", "logo removed")
    db.commit()
    delete_logo(old)
    return _settings_out(store_settings.load(db))


@router.get("/audit", response_model=list[AuditOut])
def audit_log(action: str | None = None, limit: int = Query(200, le=2000), offset: int = 0,
              db: Session = Depends(get_db), _: User = Depends(require_admin)):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    return db.scalars(query.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
