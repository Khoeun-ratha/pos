from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, require_manager
from ..models import Product, StockMovement, Supplier, User
from ..pricing import div_round
from ..schemas import ProductOut, StockChangeIn, StockCountIn, StockInIn, StockMovementOut, WriteOffIn

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


REASONS = {"damaged": "Damaged", "expired": "Expired", "lost": "Lost", "own_use": "Own use"}


def move_stock(db: Session, product: Product, change: int, kind: str, user: User | None,
               reference: str | None = None, note: str | None = None,
               unit_cost: int | None = None, supplier_id: int | None = None) -> None:
    """The only place stock levels change, so every change has a history row."""
    product.stock_qty += change
    db.add(StockMovement(
        product_id=product.id, change=change, balance=product.stock_qty, kind=kind,
        reference=reference, note=note, unit_cost=unit_cost, supplier_id=supplier_id, user_id=user.id if user else None,
    ))


def _not_below_zero(product: Product, take: int) -> None:
    if product.stock_qty - take < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {max(product.stock_qty, 0)} of {product.name} in stock")


def _tracked_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if not product.track_stock:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{product.name} does not track stock")
    return product


@router.post("/stock-in", response_model=ProductOut)
def stock_in(body: StockInIn, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """Goods received. With `unit_cost`, the product's cost becomes the average of the stock on hand
    and the new delivery, so profit stays right when the supplier changes the price."""
    product = _tracked_product(db, body.product_id)
    supplier = None
    if body.supplier_id is not None:
        supplier = db.get(Supplier, body.supplier_id)
        if supplier is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Supplier not found")
    detail = f"{product.name} +{body.qty}"
    if body.unit_cost is not None:
        on_hand = max(product.stock_qty, 0)
        old_cost = product.cost
        product.cost = div_round(on_hand * product.cost + body.qty * body.unit_cost, on_hand + body.qty)
        detail += f" at ${body.unit_cost / 100:.2f} (cost ${old_cost / 100:.2f} -> ${product.cost / 100:.2f})"
    if supplier:
        detail += f" from {supplier.name}"
    move_stock(db, product, body.qty, "stock_in", user, note=body.note, unit_cost=body.unit_cost,
               supplier_id=supplier.id if supplier else None)
    audit(db, user, "stock_in", detail)
    db.commit()
    return product


@router.post("/write-off", response_model=ProductOut)
def write_off(body: WriteOffIn, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """Damaged, expired, lost or taken for own use. The cost is kept so reports show what was lost."""
    product = _tracked_product(db, body.product_id)
    _not_below_zero(product, body.qty)
    reason = REASONS[body.reason]
    note = f"{reason}: {body.note}" if body.note else reason
    move_stock(db, product, -body.qty, "write_off", user, note=note, unit_cost=product.cost)
    audit(db, user, "stock_write_off", f"{product.name} -{body.qty} ({note}), ${product.cost * body.qty / 100:.2f}")
    db.commit()
    return product


@router.post("/adjust", response_model=ProductOut)
def adjust(body: StockChangeIn, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """Damaged, expired, lost... `qty` is the signed change."""
    if body.qty == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Change cannot be 0")
    product = _tracked_product(db, body.product_id)
    _not_below_zero(product, -body.qty)
    move_stock(db, product, body.qty, "adjustment", user, note=body.note)
    audit(db, user, "stock_adjust", f"{product.name} {body.qty:+d} ({body.note or ''})")
    db.commit()
    return product


@router.post("/count", response_model=ProductOut)
def count(body: StockCountIn, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """Stock take: set the level to what was physically counted."""
    product = _tracked_product(db, body.product_id)
    change = body.counted_qty - product.stock_qty
    if change:
        move_stock(db, product, change, "count", user, note=body.note or "Stock count")
        audit(db, user, "stock_count", f"{product.name} {change:+d}")
    db.commit()
    return product


@router.get("/low-stock", response_model=list[ProductOut])
def low_stock(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    return db.scalars(
        select(Product)
        .where(Product.is_active.is_(True), Product.track_stock.is_(True), Product.stock_qty <= Product.low_stock_threshold)
        .order_by(Product.stock_qty)
    ).all()


@router.get("/movements", response_model=list[StockMovementOut])
def movements(
    product_id: int | None = None,
    kind: str | None = None,
    supplier_id: int | None = None,
    limit: int = Query(200, le=2000),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    query = select(StockMovement)
    if product_id:
        query = query.where(StockMovement.product_id == product_id)
    if kind:
        query = query.where(StockMovement.kind == kind)
    if supplier_id:
        query = query.where(StockMovement.supplier_id == supplier_id)
    return db.scalars(query.order_by(StockMovement.id.desc()).limit(limit).offset(offset)).all()
