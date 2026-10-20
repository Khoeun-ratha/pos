import io

import pytest
from PIL import Image

from app import images
from tests.conftest import product_by_name


@pytest.fixture(autouse=True)
def temp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "PRODUCT_DIR", tmp_path / "products")
    return tmp_path / "products"


def photo(width=1600, height=1200, fmt="JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 40, 40)).save(buffer, fmt)
    return buffer.getvalue()


def upload(client, headers, product_id, data, name="coke.jpg", content_type="image/jpeg"):
    return client.post(f"/api/products/{product_id}/image", headers=headers, files={"file": (name, data, content_type)})


def test_upload_replace_and_remove(client, manager, temp_uploads):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")

    first = upload(client, manager, coke["id"], photo())
    assert first.status_code == 200, first.text
    url = first.json()["image_url"]
    assert url.startswith("/uploads/products/") and url.endswith(".webp")
    stored = temp_uploads / url.rsplit("/", 1)[1]
    with Image.open(stored) as image:
        assert max(image.size) == images.MAX_SIDE  # 1600x1200 shrunk to 800x600
    assert product_by_name(client, manager, "Coca-Cola 330ml")["image_url"] == url

    second = upload(client, manager, coke["id"], photo(300, 300, "PNG"), "coke.png", "image/png").json()["image_url"]
    assert second != url
    assert not stored.exists()  # the old photo is cleaned up

    removed = client.delete(f"/api/products/{coke['id']}/image", headers=manager)
    assert removed.json()["image_url"] is None
    assert list(temp_uploads.iterdir()) == []


def test_rejects_files_that_are_not_photos(client, manager):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    response = upload(client, manager, coke["id"], b"%PDF-1.7 not a photo", "menu.pdf", "application/pdf")
    assert response.status_code == 400
    assert "not a photo" in response.json()["detail"]


def test_cashier_cannot_change_photos(client, cashier):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    assert upload(client, cashier, coke["id"], photo()).status_code == 403
