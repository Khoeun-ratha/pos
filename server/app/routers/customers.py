from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, get_current_user
from ..models import Customer, Sale, User
from ..schemas import CustomerIn, CustomerOut, SaleSummaryOut

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already belongs to another customer")


@router.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, limit: int = Query(100, le=1000), offset: int = 0,
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = select(Customer)
    if q:
        query = query.where(or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
    return db.scalars(query.order_by(Customer.name).limit(limit).offset(offset)).all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    customer = Customer(name=body.name, phone=(body.phone or "").strip() or None, email=body.email)
    db.add(customer)
    audit(db, user, "customer_create", body.name)
    _save(db)
    return customer


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, body: CustomerIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    customer.name, customer.phone, customer.email = body.name, (body.phone or "").strip() or None, body.email
    audit(db, user, "customer_update", body.name)
    _save(db)
    return customer


@router.get("/{customer_id}/sales", response_model=list[SaleSummaryOut])
def customer_sales(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Sale).where(Sale.customer_id == customer_id).order_by(Sale.id.desc()).limit(200)).all()
