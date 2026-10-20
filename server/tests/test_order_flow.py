"""The order flow of a standard till: shift first, held orders, voids, reprints, payment references, offline sync."""

from datetime import datetime, timedelta

from tests.conftest import product_by_name
from tests.test_api import checkout


def sell(client, headers, body):
    return client.post("/api/sales", headers=headers, json=body)


def audit_actions(client, admin, action):
    return [a["detail"] for a in client.get("/api/audit", headers=admin, params={"action": action}).json()]


def test_no_selling_without_an_open_shift(client, cashier):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    body = {"items": [{"product_id": coke["id"], "qty": 1}], "payments": [{"method": "cash", "amount": 100}]}
    response = sell(client, cashier, body)
    assert response.status_code == 400 and "Open a shift" in response.json()["detail"]
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    assert sell(client, cashier, body).status_code == 201


def test_offline_sale_keeps_the_phone_prices_and_is_never_refused(client, cashier, admin, manager):
    client.put("/api/settings", headers=admin, json={"allow_negative_stock": False})
    eggs = product_by_name(client, cashier, "Eggs (10 pcs)")  # $1.60, 3 in stock
    client.put(f"/api/products/{eggs['id']}", headers=manager, json={**{k: eggs[k] for k in (
        "name", "sku", "barcode", "category_id", "cost", "track_stock", "low_stock_threshold")}, "price": 180, "is_active": False})

    # the phone sold 5 at the old price $1.60 with 4,000 riel to the dollar, no shift open, while offline
    body = {
        "items": [{"product_id": eggs["id"], "qty": 5, "unit_price": 160}],
        "payments": [{"method": "cash", "currency": "KHR", "amount": 36000}],
        "offline": True, "exchange_rate": 4000, "client_uuid": "phone-1",
        "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
    }
    response = sell(client, cashier, body)
    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["total"] == 880 and sale["exchange_rate"] == 4000 and sale["shift_id"] is None
    assert sale["items"][0]["unit_price"] == 160
    assert any("synced with the phone's prices" in d and "$1.60 (now $1.80)" in d for d in audit_actions(client, admin, "offline_sale"))

    # sending it again (phone retried) does not sell it twice
    assert sell(client, cashier, body).status_code == 200


def test_offline_sale_goes_to_the_shift_open_at_that_time(client, cashier):
    shift = client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0}).json()
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    made_at = datetime.now().replace(microsecond=0)
    client.post("/api/shifts/current/close", headers=cashier, json={"counted_usd": 0, "counted_khr": 0})
    body = {"items": [{"product_id": coke["id"], "qty": 1, "unit_price": 75}], "payments": [{"method": "cash", "amount": 100}],
            "offline": True, "created_at": made_at.isoformat(), "client_uuid": "phone-2"}
    assert sell(client, cashier, body).json()["shift_id"] == shift["id"]


def test_payment_reference_is_kept_and_printed(client, cashier):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    payments = [{"method": "khqr", "amount": 715, "reference": " ABA-778812 "}]
    sale = checkout(client, cashier, [{"product_id": rice["id"], "qty": 1}], payments).json()
    assert sale["payments"][0]["reference"] == "ABA-778812"
    assert "Ref: ABA-778812" in client.get(f"/api/sales/{sale['id']}/receipt", headers=cashier).text


def test_reprint_is_marked_and_logged(client, cashier, admin):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    sale = checkout(client, cashier, [{"product_id": coke["id"], "qty": 1}], [{"method": "cash", "amount": 100}]).json()
    original = client.get(f"/api/sales/{sale['id']}/receipt", headers=cashier).text
    copy = client.get(f"/api/sales/{sale['id']}/receipt?reprint=true", headers=cashier).text
    assert "REPRINT" not in original and "*** REPRINT / COPY ***" in copy
    assert audit_actions(client, admin, "receipt_reprint") == [sale["receipt_no"]]


def test_voids_need_a_manager_and_are_logged(client, cashier, admin):
    body = {"kind": "line", "items": [{"name": "Coca-Cola 330ml", "qty": 2, "amount": 150}]}
    assert client.post("/api/sales/void", headers=cashier, json=body).status_code == 403
    assert client.post("/api/sales/void", headers=cashier, json={**body, "manager_pin": "2222"}).status_code == 204
    assert audit_actions(client, admin, "void") == ["Item voided: 2 x Coca-Cola 330ml ($1.50), approved by manager"]


def test_held_orders_live_on_the_server(client, cashier, manager, admin):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    cart = {"items": [{"product_id": rice["id"], "qty": 2}], "discount_type": None, "discount_value": 0}
    held = client.post("/api/parked", headers=cashier, json={**cart, "label": "Lady in red"})
    assert held.status_code == 201 and held.json()["total"] == 1430

    # another till sees it and finishes it; then it is gone for everyone
    listed = client.get("/api/parked", headers=manager).json()
    assert [(o["label"], o["cashier_name"]) for o in listed] == [("Lady in red", "Cashier 1")]
    resumed = client.post(f"/api/parked/{held.json()['id']}/resume", headers=manager).json()
    assert resumed["cart"]["items"] == [{"product_id": rice["id"], "qty": 2, "discount_type": None, "discount_value": 0,
                                        "note": None, "unit_price": None}]
    assert client.get("/api/parked", headers=cashier).json() == []
    assert client.post(f"/api/parked/{held.json()['id']}/resume", headers=cashier).status_code == 404

    # throwing one away is a void
    other = client.post("/api/parked", headers=cashier, json=cart).json()
    assert client.post(f"/api/parked/{other['id']}/discard", headers=cashier, json={}).status_code == 403
    assert client.post(f"/api/parked/{other['id']}/discard", headers=cashier, json={"manager_pin": "2222"}).status_code == 204
    assert audit_actions(client, admin, "void") == ["Held order discarded: 1 line(s) ($14.30), approved by manager"]
