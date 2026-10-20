from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, require_perm
from ..models import Location, LocationStock, Product, StockMovement, Supplier, User
from ..pricing import div_round
from ..schemas import ProductOut, StockChangeIn, StockCountIn, StockInIn, StockMovementOut, WriteOffIn

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


REASONS = {"damaged": "Damaged", "expired": "Expired", "lost": "Lost", "own_use": "Own use"}


def get_location(db: Session, location_id: int | None) -> Location | None:
    """The branch / warehouse, or None for the main shop."""
    if location_id is None:
        return None
    location = db.get(Location, location_id)
    if location is None or not location.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Location not found")
    return location


def qty_at(db: Session, product: Product, location: Location | None) -> int:
    if location is None:
        return product.stock_qty
    row = db.get(LocationStock, (location.id, product.id))
    return row.qty if row else 0


def total_qty(db: Session, product: Product) -> int:
    """Stock in the main shop and every branch / warehouse together."""
    elsewhere = db.scalar(select(func.coalesce(func.sum(LocationStock.qty), 0)).where(LocationStock.product_id == product.id))
    return product.stock_qty + int(elsewhere)


def move_stock(db: Session, product: Product, change: int, kind: str, user: User | None,
               reference: str | None = None, note: str | None = None,
               unit_cost: int | None = None, supplier_id: int | None = None, location: Location | None = None) -> None:
    """The only place stock levels change, so every change has a history row."""
    if location is None:
        product.stock_qty += change
        balance = product.stock_qty
    else:
        row = db.get(LocationStock, (location.id, product.id))
        if row is None:
            row = LocationStock(location_id=location.id, product_id=product.id, qty=0)
            db.add(row)
            db.flush()
        row.qty += change
        balance = row.qty
    db.add(StockMovement(
        product_id=product.id, change=change, balance=balance, kind=kind, reference=reference, note=note,
        unit_cost=unit_cost, supplier_id=supplier_id, user_id=user.id if user else None,
        location_id=location.id if location else None,
    ))


def not_below_zero(db: Session, product: Product, take: int, location: Location | None = None) -> None:
    have = qty_at(db, product, location)
    if have - take < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {max(have, 0)} of {product.name} in stock{_where(location)}")


def _where(location: Location | None) -> str:
    return f" at {location.name}" if location else ""


def _tracked_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if not product.track_stock:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{product.name} does not track stock")
    return product


@router.post("/stock-in", response_model=ProductOut)
def stock_in(body: StockInIn, db: Session = Depends(get_db), user: User = Depends(require_perm("inventory"))):
    """Goods received. With `unit_cost`, the product's cost becomes the average of the stock on hand
    and the new delivery, so profit stays right when the supplier changes the price."""
    product = _tracked_product(db, body.product_id)
    location = get_location(db, body.location_id)
    supplier = None
    if body.supplier_id is not None:
        supplier = db.get(Supplier, body.supplier_id)
        if supplier is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Supplier not found")
    detail = f"{product.name} +{body.qty}{_where(location)}"
    if body.unit_cost is not None:
        on_hand = max(total_qty(db, product), 0)
        old_cost = product.cost
        product.cost = div_round(on_hand * product.cost + body.qty * body.unit_cost, on_hand + body.qty)
        detail += f" at ${body.unit_cost / 100:.2f} (cost ${old_cost / 100:.2f} -> ${product.cost / 100:.2f})"
    if supplier:
        detail += f" from {supplier.name}"
    move_stock(db, product, body.qty, "stock_in", user, note=body.note, unit_cost=body.unit_cost,
               supplier_id=supplier.id if supplier else None, location=location)
    audit(db, user, "stock_in", detail)
    db.commit()
    return product


@router.post("/write-off", response_model=ProductOut)
def write_off(body: WriteOffIn, db: Session = Depends(get_db), user: User = Depends(require_perm("inventory"))):
    """Damaged, expired, lost or taken for own use. The cost is kept so reports show what was lost."""
    product = _tracked_product(db, body.product_id)
    location = get_location(db, body.location_id)
    not_below_zero(db, product, body.qty, location)
    reason = REASONS[body.reason]
    note = f"{reason}: {body.note}" if body.note else reason
    move_stock(db, product, -body.qty, "write_off", user, note=note, unit_cost=product.cost, location=location)
    audit(db, user, "stock_write_off",
          f"{product.name} -{body.qty}{_where(location)} ({note}), ${product.cost * body.qty / 100:.2f}")
    db.commit()
    return product


@router.post("/adjust", response_model=ProductOut)
def adjust(body: StockChangeIn, db: Session = Depends(get_db), user: User = Depends(require_perm("inventory"))):
    """Damaged, expired, lost... `qty` is the signed change."""
    if body.qty == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Change cannot be 0")
    product = _tracked_product(db, body.product_id)
    location = get_location(db, body.location_id)
    not_below_zero(db, product, -body.qty, location)
    move_stock(db, product, body.qty, "adjustment", user, note=body.note, location=location)
    audit(db, user, "stock_adjust", f"{product.name} {body.qty:+d}{_where(location)} ({body.note or ''})")
    db.commit()
    return product


@router.post("/count", response_model=ProductOut)
def count(body: StockCountIn, db: Session = Depends(get_db), user: User = Depends(require_perm("inventory"))):
    """Stock take: set the level to what was physically counted."""
    product = _tracked_product(db, body.product_id)
    location = get_location(db, body.location_id)
    change = body.counted_qty - qty_at(db, product, location)
    if change:
        move_stock(db, product, change, "count", user, note=body.note or "Stock count", location=location)
        audit(db, user, "stock_count", f"{product.name} {change:+d}{_where(location)}")
    db.commit()
    return product


@router.get("/low-stock", response_model=list[ProductOut])
def low_stock(db: Session = Depends(get_db), _: User = Depends(require_perm("inventory", "reports"))):
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
    location: str | None = Query(None, description='"main" for the main shop, or a location id; empty = everywhere'),
    reference: str | None = None,
    limit: int = Query(200, le=2000),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_perm("inventory")),
):
    query = select(StockMovement)
    if product_id:
        query = query.where(StockMovement.product_id == product_id)
    if kind:
        query = query.where(StockMovement.kind == kind)
    if supplier_id:
        query = query.where(StockMovement.supplier_id == supplier_id)
    if location == "main":
        query = query.where(StockMovement.location_id.is_(None))
    elif location:
        if not location.isdigit():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'location must be "main" or a location id')
        query = query.where(StockMovement.location_id == int(location))
    if reference:
        query = query.where(StockMovement.reference == reference)
    return db.scalars(query.order_by(StockMovement.id.desc()).limit(limit).offset(offset)).all()
