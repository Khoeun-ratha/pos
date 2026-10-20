import csv
import io
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import audit, get_current_user, require_perm
from ..images import InvalidImage, delete_product_image, save_product_image
from ..models import Category, Product, StockMovement, User
from ..schemas import CategoryIn, CategoryOut, ImportResult, ProductCreate, ProductIn, ProductOut

router = APIRouter(prefix="/api", tags=["catalog"])

CSV_COLUMNS = ["name", "sku", "barcode", "category", "price", "cost", "stock_qty", "low_stock_threshold", "track_stock", "is_active"]


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Name, SKU or barcode already used by another record")


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _cents(value: str | None, field: str) -> int:
    """'1.25', '$1.25' or '1,250.00' -> cents."""
    text = (value or "").strip().replace("$", "").replace(",", "") or "0"
    try:
        cents = int((Decimal(text) * 100).quantize(Decimal(1)))
    except InvalidOperation:
        raise ValueError(f"{field} '{value}' is not a number")
    if cents < 0:
        raise ValueError(f"{field} cannot be negative")
    return cents


def _whole(value: str | None, field: str, default: int) -> int:
    text = (value or "").strip()
    if not text:
        return default
    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"{field} '{value}' must be a whole number")
    if number < 0:
        raise ValueError(f"{field} cannot be negative")
    return number


def _csv_safe(value: str) -> str:
    """Stops spreadsheet programs from running a name like '=HYPERLINK(...)' as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


# ---------- categories ----------

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Category).order_by(Category.sort_order, Category.name)).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    category = Category(**body.model_dump())
    db.add(category)
    audit(db, user, "category_create", body.name)
    _commit_or_conflict(db)
    return category


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    category.name, category.sort_order = body.name, body.sort_order
    audit(db, user, "category_update", body.name)
    _commit_or_conflict(db)
    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    db.delete(category)
    audit(db, user, "category_delete", category.name)
    db.commit()


# ---------- products ----------

@router.get("/products", response_model=list[ProductOut])
def list_products(
    q: str | None = None,
    category_id: int | None = None,
    include_inactive: bool = False,
    limit: int = Query(500, le=5000),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Product)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode == q))
    if category_id:
        query = query.where(Product.category_id == category_id)
    if not include_inactive:
        query = query.where(Product.is_active.is_(True))
    return db.scalars(query.order_by(Product.name).limit(limit).offset(offset)).all()


def barcode_variants(code: str) -> list[str]:
    """A scanner may read UPC-A (12 digits) for a product saved as EAN-13 with a leading 0, or the other way round."""
    code = code.strip()
    if len(code) == 12 and code.isdigit():
        return [code, "0" + code]
    if len(code) == 13 and code.isdigit() and code.startswith("0"):
        return [code, code[1:]]
    return [code]


@router.get("/products/barcode/{code}", response_model=ProductOut)
def product_by_barcode(code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    code = code.strip()
    product = db.scalar(
        select(Product).where(or_(Product.barcode.in_(barcode_variants(code)), Product.sku == code)).order_by(Product.is_active.desc())
    )
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No product with barcode {code}")
    return product


@router.get("/products/export")
def export_products(db: Session = Depends(get_db), _: User = Depends(require_perm("products"))):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for p in db.scalars(select(Product).order_by(Product.name)):
        writer.writerow([
            _csv_safe(p.name), _csv_safe(p.sku or ""), _csv_safe(p.barcode or ""), _csv_safe(p.category_name or ""),
            f"{p.price / 100:.2f}", f"{p.cost / 100:.2f}", p.stock_qty, p.low_stock_threshold,
            str(p.track_stock).lower(), str(p.is_active).lower(),
        ])
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


@router.post("/products/import", response_model=ImportResult)
async def import_products(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    """CSV with the same columns as the export. Prices in dollars (e.g. 1.25). Matches existing rows by SKU, then barcode."""
    text = (await file.read()).decode("utf-8-sig")
    created = updated = 0
    errors: list[str] = []
    categories = {c.name.lower(): c for c in db.scalars(select(Category))}

    for line_no, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            name = _clean(row.get("name"))
            if not name:
                raise ValueError("name is required")
            sku, barcode = _clean(row.get("sku")), _clean(row.get("barcode"))
            price, cost = _cents(row.get("price"), "price"), _cents(row.get("cost"), "cost")
            threshold = _whole(row.get("low_stock_threshold"), "low_stock_threshold", 5)
            stock = _whole(row.get("stock_qty"), "stock_qty", 0)
            product = None
            if sku:
                product = db.scalar(select(Product).where(Product.sku == sku))
            if product is None and barcode:
                product = db.scalar(select(Product).where(Product.barcode == barcode))

            category = None
            category_name = _clean(row.get("category"))
            if category_name:
                category = categories.get(category_name.lower())
                if category is None:
                    category = Category(name=category_name)
                    db.add(category)
                    db.flush()
                    categories[category_name.lower()] = category

            fields = {
                "name": name,
                "sku": sku,
                "barcode": barcode,
                "category_id": category.id if category else None,
                "price": price,
                "cost": cost,
                "low_stock_threshold": threshold,
                "track_stock": (row.get("track_stock") or "true").strip().lower() != "false",
                "is_active": (row.get("is_active") or "true").strip().lower() != "false",
            }

            with db.begin_nested():
                if product is None:
                    product = Product(**fields, stock_qty=stock)
                    db.add(product)
                    db.flush()
                    if stock:
                        db.add(StockMovement(product_id=product.id, change=stock, balance=stock, kind="stock_in", note="CSV import", user_id=user.id))
                    created += 1
                else:
                    for key, value in fields.items():
                        setattr(product, key, value)
                    updated += 1
        except ValueError as exc:
            errors.append(f"Line {line_no}: {exc}")
        except IntegrityError:
            errors.append(f"Line {line_no}: SKU or barcode already used by another product")

    audit(db, user, "product_import", f"created={created} updated={updated} errors={len(errors)}")
    db.commit()
    return ImportResult(created=created, updated=updated, errors=errors)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    data = body.model_dump()
    data["sku"], data["barcode"] = _clean(data["sku"]), _clean(data["barcode"])
    product = Product(**data)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "SKU or barcode already used by another product")
    if product.stock_qty:
        db.add(StockMovement(product_id=product.id, change=product.stock_qty, balance=product.stock_qty, kind="stock_in", note="Opening stock", user_id=user.id))
    audit(db, user, "product_create", product.name)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    """Stock is not edited here: use the inventory endpoints so every change is recorded."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    changes = []
    for key, value in body.model_dump().items():
        if key in ("sku", "barcode"):
            value = _clean(value)
        if getattr(product, key) != value:
            changes.append(f"{key}: {getattr(product, key)} -> {value}")
            setattr(product, key, value)
    audit(db, user, "product_update", f"{product.name}: " + "; ".join(changes))
    _commit_or_conflict(db)
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def deactivate_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    """Products are deactivated, never deleted, so old receipts and reports stay correct."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product.is_active = False
    audit(db, user, "product_deactivate", product.name)
    db.commit()


@router.post("/products/{product_id}/image", response_model=ProductOut)
async def upload_product_image(product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    """JPG, PNG or WebP photo, up to 8 MB. Stored shrunk to 800 px; replaces any previous photo."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    try:
        url = save_product_image(product.id, await file.read())
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    old = product.image_url
    product.image_url = url
    audit(db, user, "product_image", product.name)
    db.commit()
    delete_product_image(old)
    db.refresh(product)
    return product


@router.delete("/products/{product_id}/image", response_model=ProductOut)
def remove_product_image(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_perm("products"))):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    old, product.image_url = product.image_url, None
    audit(db, user, "product_image", f"{product.name}: removed")
    db.commit()
    delete_product_image(old)
    db.refresh(product)
    return product
