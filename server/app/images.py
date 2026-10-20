"""Product photos: checked, shrunk to a square-ish thumbnail and stored as WebP under server/uploads."""

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import UPLOAD_DIR

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 800  # pixels; plenty for product cards, small files for phones
PRODUCT_DIR = UPLOAD_DIR / "products"
LOGO_DIR = UPLOAD_DIR / "logo"
LOGO_SIDE = 512


class InvalidImage(ValueError):
    pass


def _open(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImage("Photo is too large (max 8 MB)")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise InvalidImage("This file is not a photo (use JPG, PNG or WebP)")
    return ImageOps.exif_transpose(image)  # phone photos: respect the camera's rotation


def save_logo(data: bytes) -> str:
    """Shop logo, kept as PNG so a transparent background stays transparent on screens and receipts."""
    image = _open(data)
    image.thumbnail((LOGO_SIDE, LOGO_SIDE))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"logo-{secrets.token_hex(4)}.png"
    image.save(LOGO_DIR / name, "PNG", optimize=True)
    return f"/uploads/logo/{name}"


def delete_logo(url: str | None) -> None:
    if url and url.startswith("/uploads/logo/"):
        (LOGO_DIR / Path(url).name).unlink(missing_ok=True)


def save_product_image(product_id: int, data: bytes) -> str:
    """Returns the public URL of the stored image."""
    image = _open(data)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    # a new name each time, so browsers and phones never show an old cached photo
    name = f"{product_id}-{secrets.token_hex(4)}.webp"
    image.save(PRODUCT_DIR / name, "WEBP", quality=85, method=4)
    return f"/uploads/products/{name}"


def delete_product_image(url: str | None) -> None:
    if not url or not url.startswith("/uploads/products/"):
        return
    path = PRODUCT_DIR / Path(url).name  # .name: never leave the uploads folder
    path.unlink(missing_ok=True)
