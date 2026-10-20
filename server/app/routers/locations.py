"""Branches / warehouses and stock transfers between them and the main shop.

The main shop is where the tills sell; its stock is Product.stock_qty and it is location None here.
A transfer is sent (the stock leaves the source at once: it is on the road), then received at the
destination, or cancelled before that (the stock goes back to the source)."""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import store_settings
from ..database import get_db
from ..deps import audit, require_perm
from ..models import Location, LocationStock, Product, StockTransfer, StockTransferItem, User, now
from ..schemas import LocationIn, LocationOut, LocationStockOut, TransferIn, TransferOut
from .inventory import get_location, move_stock, not_below_zero

router = APIRouter(prefix="/api", tags=["inventory"])
inventory = require_perm("inventory")


def _name(user: User | None) -> str | None:
    return (user.full_name or user.username) if user else None


def transfer_out(db: Session, transfer: StockTransfer) -> TransferOut:
    main = store_settings.load(db)["store_name"]
    return TransferOut(
        id=transfer.id,
        transfer_no=transfer.transfer_no,
        from_location_id=transfer.from_location_id,
        from_name=transfer.from_location.name if transfer.from_location else main,
        to_location_id=transfer.to_location_id,
        to_name=transfer.to_location.name if transfer.to_location else main,
        status=transfer.status,
        note=transfer.note,
        created_by=_name(transfer.created_by),
        created_at=transfer.created_at,
        closed_by=_name(transfer.closed_by),
        closed_at=transfer.closed_at,
        items=transfer.items,
        total_qty=sum(i.qty for i in transfer.items),
        total_cost=sum(i.qty * i.unit_cost for i in transfer.items),
    )


# ---------- locations ----------

@router.get("/locations", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db), _: User = Depends(inventory)):
    return db.scalars(select(Location).order_by(Location.name)).all()


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(body: LocationIn, db: Session = Depends(get_db), user: User = Depends(inventory)):
    if db.scalar(select(Location).where(Location.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "A location with this name already exists")
    location = Location(**{**body.model_dump(), "name": body.name.strip()})
    db.add(location)
    audit(db, user, "location_create", f"{location.name} ({location.kind})")
    db.commit()
    return location


@router.patch("/locations/{location_id}", response_model=LocationOut)
def update_location(location_id: int, body: LocationIn, db: Session = Depends(get_db), user: User = Depends(inventory)):
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    name = body.name.strip()
    if name != location.name and db.scalar(select(Location).where(Location.name == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A location with this name already exists")
    if not body.is_active and location.is_active:
        on_road = db.scalar(select(func.count()).select_from(StockTransfer).where(
            StockTransfer.status == "in_transit",
            (StockTransfer.from_location_id == location.id) | (StockTransfer.to_location_id == location.id),
        ))
        if on_road:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Receive or cancel the transfers of this location first")
    location.name, location.kind, location.address, location.is_active = name, body.kind, body.address, body.is_active
    audit(db, user, "location_update", location.name)
    db.commit()
    return location


@router.get("/locations/{location_id}/stock", response_model=list[LocationStockOut])
def location_stock(location_id: int, db: Session = Depends(get_db), _: User = Depends(inventory)):
    """Stock of every product at this branch / warehouse (products never stocked there are left out)."""
    if db.get(Location, location_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    rows = db.scalars(select(LocationStock).where(LocationStock.location_id == location_id))
    return [LocationStockOut(product_id=r.product_id, qty=r.qty) for r in rows]


# ---------- transfers ----------

@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(inventory),
):
    query = select(StockTransfer)
    if status_:
        query = query.where(StockTransfer.status == status_)
    return [transfer_out(db, t) for t in db.scalars(query.order_by(StockTransfer.id.desc()).limit(limit))]


def _get_transfer(db: Session, transfer_id: int) -> StockTransfer:
    transfer = db.get(StockTransfer, transfer_id)
    if transfer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    return transfer


@router.get("/transfers/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: int, db: Session = Depends(get_db), _: User = Depends(inventory)):
    return transfer_out(db, _get_transfer(db, transfer_id))


@router.post("/transfers", response_model=TransferOut, status_code=201)
def send_transfer(body: TransferIn, db: Session = Depends(get_db), user: User = Depends(inventory)):
    if body.from_location_id == body.to_location_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose two different places")
    source = get_location(db, body.from_location_id)
    destination = get_location(db, body.to_location_id)

    wanted = Counter()
    for item in body.items:
        wanted[item.product_id] += item.qty
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(wanted)))}
    for product_id in wanted:
        product = products.get(product_id)
        if product is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Product {product_id} does not exist")
        if not product.track_stock:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{product.name} does not track stock")
        # goods on a truck are real: never send more than the source has, whatever the till allows
        not_below_zero(db, product, wanted[product_id], source)

    prefix = f"TR{now():%Y%m%d}"
    count_today = db.scalar(select(func.count()).select_from(StockTransfer).where(StockTransfer.transfer_no.like(f"{prefix}-%")))
    transfer = StockTransfer(
        from_location_id=source.id if source else None,
        to_location_id=destination.id if destination else None,
        note=(body.note or "").strip() or None,
        created_by_id=user.id,
        items=[StockTransferItem(product_id=pid, qty=qty, unit_cost=products[pid].cost) for pid, qty in wanted.items()],
    )
    for attempt in range(5):  # two people sending at the same moment can pick the same number
        transfer.transfer_no = f"{prefix}-{count_today + 1 + attempt:04d}"
        try:
            with db.begin_nested():
                db.add(transfer)
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not save the transfer, please try again")

    out = transfer_out(db, transfer)
    for pid, qty in wanted.items():
        move_stock(db, products[pid], -qty, "transfer_out", user, reference=transfer.transfer_no,
                   note=f"To {out.to_name}", location=source)
    audit(db, user, "transfer_send", f"{transfer.transfer_no}: {out.total_qty} item(s) {out.from_name} -> {out.to_name}")
    db.commit()
    db.refresh(transfer)
    return transfer_out(db, transfer)


def _close(db: Session, transfer_id: int, user: User, received: bool) -> TransferOut:
    transfer = _get_transfer(db, transfer_id)
    if transfer.status != "in_transit":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Transfer {transfer.transfer_no} is already {transfer.status.replace('_', ' ')}")
    out = transfer_out(db, transfer)
    # receiving puts the goods on the destination; cancelling puts them back where they came from
    target = transfer.to_location if received else transfer.from_location
    for item in transfer.items:
        move_stock(db, item.product, item.qty, "transfer_in", user, reference=transfer.transfer_no,
                   note=f"From {out.from_name}" if received else "Transfer cancelled", location=target)
    transfer.status = "received" if received else "cancelled"
    transfer.closed_by_id = user.id
    transfer.closed_at = now()
    audit(db, user, "transfer_receive" if received else "transfer_cancel",
          f"{transfer.transfer_no}: {out.total_qty} item(s) {out.from_name} -> {out.to_name}")
    db.commit()
    db.refresh(transfer)
    return transfer_out(db, transfer)


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
def receive_transfer(transfer_id: int, db: Session = Depends(get_db), user: User = Depends(inventory)):
    return _close(db, transfer_id, user, received=True)


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferOut)
def cancel_transfer(transfer_id: int, db: Session = Depends(get_db), user: User = Depends(inventory)):
    return _close(db, transfer_id, user, received=False)
