from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, require_perm
from ..models import Supplier, User
from ..schemas import SupplierIn, SupplierOut

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A supplier with this name already exists")


def _clean(body: SupplierIn) -> dict:
    data = body.model_dump()
    data["name"] = data["name"].strip()
    for key in ("phone", "note"):
        data[key] = (data[key] or "").strip() or None
    if not data["name"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is required")
    return data


@router.get("", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), _: User = Depends(require_perm("suppliers", "inventory"))):
    return db.scalars(select(Supplier).order_by(Supplier.is_active.desc(), Supplier.name)).all()


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(require_perm("suppliers"))):
    supplier = Supplier(**_clean(body))
    db.add(supplier)
    audit(db, user, "supplier_create", supplier.name)
    _save(db)
    return supplier


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(require_perm("suppliers"))):
    """Suppliers are never deleted (stock history points at them); set is_active to false instead."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    for key, value in _clean(body).items():
        setattr(supplier, key, value)
    audit(db, user, "supplier_update", supplier.name)
    _save(db)
    return supplier
