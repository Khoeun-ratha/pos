from conftest import product_by_name


def set_permissions(client, admin, manager: list[str], cashier: list[str]):
    response = client.put("/api/permissions", json={"manager": manager, "cashier": cashier}, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def test_defaults_match_the_roles(client, admin, manager, cashier):
    body = client.get("/api/permissions", headers=cashier).json()
    assert body["mine"] == []
    assert set(body["roles"]["manager"]) == {p["key"] for p in body["permissions"]}
    assert body["roles"]["admin"] == body["roles"]["manager"]
    assert client.get("/api/permissions", headers=manager).json()["mine"] == body["roles"]["manager"]


def test_only_admin_changes_permissions(client, manager):
    response = client.put("/api/permissions", json={"manager": [], "cashier": []}, headers=manager)
    assert response.status_code == 403


def test_unknown_permission_is_refused(client, admin):
    response = client.put("/api/permissions", json={"manager": ["fly"], "cashier": []}, headers=admin)
    assert response.status_code == 400


def test_cashier_given_inventory_can_receive_stock(client, admin, cashier):
    cola = product_by_name(client, cashier, "Coca-Cola 330ml")
    receive = {"product_id": cola["id"], "qty": 5}
    assert client.post("/api/inventory/stock-in", json=receive, headers=cashier).status_code == 403

    set_permissions(client, admin, manager=["reports"], cashier=["inventory"])
    response = client.post("/api/inventory/stock-in", json=receive, headers=cashier)
    assert response.status_code == 200, response.text
    assert response.json()["stock_qty"] == cola["stock_qty"] + 5
    # still not products or reports
    assert client.post("/api/categories", json={"name": "New"}, headers=cashier).status_code == 403
    assert client.get("/api/reports/summary", headers=cashier).status_code == 403


def test_manager_without_inventory_is_refused(client, admin, manager):
    cola = product_by_name(client, manager, "Coca-Cola 330ml")
    set_permissions(client, admin, manager=["reports", "products"], cashier=[])
    response = client.post("/api/inventory/count", json={"product_id": cola["id"], "counted_qty": 1}, headers=manager)
    assert response.status_code == 403
    # admin always keeps everything
    response = client.post("/api/inventory/count", json={"product_id": cola["id"], "counted_qty": 1}, headers=admin)
    assert response.status_code == 200


def test_approve_permission_controls_the_manager_pin(client, admin, cashier):
    void = {"kind": "line", "items": [{"name": "Coca-Cola 330ml", "qty": 1, "amount": 75}]}
    # seed: manager PIN 2222
    ok = client.post("/api/sales/void", json={**void, "manager_pin": "2222"}, headers=cashier)
    assert ok.status_code == 204, ok.text

    set_permissions(client, admin, manager=["reports"], cashier=[])
    refused = client.post("/api/sales/void", json={**void, "manager_pin": "2222"}, headers=cashier)
    assert refused.status_code == 403

    set_permissions(client, admin, manager=["approve"], cashier=["approve"])
    # a cashier allowed to approve needs no PIN
    assert client.post("/api/sales/void", json=void, headers=cashier).status_code == 204


def test_permission_change_is_logged(client, admin):
    set_permissions(client, admin, manager=["reports"], cashier=["inventory"])
    log = client.get("/api/audit", params={"action": "permissions_update"}, headers=admin).json()
    assert log and "cashier: inventory" in log[0]["detail"]


def test_old_pin_hash_is_made_quicker_when_used(client, cashier):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User
    from app.security import PIN_ROUNDS, hash_secret

    with SessionLocal() as db:  # a PIN saved before PINs had their own cost
        db.scalar(select(User).where(User.username == "manager")).pin_hash = hash_secret("2222", 12)
        db.commit()
    assert client.post("/api/auth/verify-manager-pin", json={"pin": "2222"}, headers=cashier).status_code == 200
    with SessionLocal() as db:
        saved = db.scalar(select(User).where(User.username == "manager")).pin_hash
    assert saved.split("$")[2] == f"{PIN_ROUNDS:02d}"
    # and the PIN still works
    assert client.post("/api/auth/verify-manager-pin", json={"pin": "2222"}, headers=cashier).status_code == 200
    assert client.post("/api/auth/verify-manager-pin", json={"pin": "9999"}, headers=cashier).status_code == 403
