"""Cashier changes: handing the drawer over, sending held orders to a till, closing a shift left open."""

from tests.conftest import product_by_name
from tests.test_api import checkout


def test_handover_moves_the_counted_cash_to_the_next_cashier(client, cashier, admin):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 2000})
    checkout(client, cashier, [{"product_id": coke["id"], "qty": 4}], [{"method": "cash", "amount": 500}])
    expected = client.get("/api/shifts/current", headers=cashier).json()["expected_cash"]
    staff = {u["username"]: u for u in client.get("/api/users/staff", headers=cashier).json()}
    nxt = staff["cashier2"]
    body = {"to_user_id": nxt["id"], "pin": "0000", "counted_usd": expected - 25, "counted_khr": 0}

    assert client.post("/api/shifts/current/handover", headers=cashier, json=body).status_code == 403  # wrong PIN
    assert client.post("/api/shifts/current/handover", headers=cashier, json={**body, "to_user_id": staff["cashier"]["id"], "pin": "3333"}).status_code == 400

    done = client.post("/api/shifts/current/handover", headers=cashier, json={**body, "pin": "4444"})
    assert done.status_code == 200, done.text
    closed, opened = done.json()["closed"], done.json()["opened"]
    assert not closed["is_open"] and closed["variance"] == -25 and closed["handed_to_name"] == "Cashier 2"
    assert opened["is_open"] and opened["opening_cash"] == expected - 25 and opened["handed_from_name"] == "Cashier 1"

    # the outgoing cashier has no drawer now; the next one sells straight away
    assert client.get("/api/shifts/current", headers=cashier).json() is None
    token = client.post("/api/auth/login", json={"username": "cashier2", "password": "cashier123"}).json()["access_token"]
    cashier2 = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/shifts/current", headers=cashier2).json()["id"] == opened["id"]
    # and cannot be handed a second drawer
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    again = client.post("/api/shifts/current/handover", headers=cashier, json={**body, "pin": "4444"})
    assert again.status_code == 400 and "already has an open shift" in again.json()["detail"]
    log = client.get("/api/audit", headers=admin, params={"action": "shift_handover"}).json()
    assert log and log[0]["detail"].startswith("to cashier2")


def test_cashier_sees_own_shifts_only(client, cashier, manager):
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    client.post("/api/shifts/open", headers=manager, json={"opening_cash": 0})
    mine = client.get("/api/shifts", headers=cashier).json()
    assert [s["cashier_name"] for s in mine] == ["Cashier 1"]
    assert len(client.get("/api/shifts", headers=manager).json()) == 2


def test_manager_closes_a_shift_left_open(client, cashier, manager):
    shift = client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 1000}).json()
    assert client.post(f"/api/shifts/{shift['id']}/close", headers=cashier, json={"counted_usd": 1000}).status_code == 403
    closed = client.post(f"/api/shifts/{shift['id']}/close", headers=manager, json={"counted_usd": 1000})
    assert closed.status_code == 200 and closed.json()["variance"] == 0 and closed.json()["note"] == "Closed by Store Manager"
    assert client.get("/api/shifts/current", headers=cashier).json() is None
    assert client.post(f"/api/shifts/{shift['id']}/close", headers=manager, json={}).status_code == 400


def test_held_order_sent_to_another_till(client, cashier, manager, admin):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    staff = {u["username"]: u["id"] for u in client.get("/api/users/staff", headers=cashier).json()}
    cart = {"items": [{"product_id": rice["id"], "qty": 1}], "label": "Table 4", "assigned_to_id": staff["cashier2"]}
    held = client.post("/api/parked", headers=cashier, json=cart).json()
    assert held["assigned_to_name"] == "Cashier 2"

    moved = client.post(f"/api/parked/{held['id']}/assign", headers=manager, json={"assigned_to_id": staff["manager"]}).json()
    assert moved["assigned_to_name"] == "Store Manager"
    anyone = client.post(f"/api/parked/{held['id']}/assign", headers=manager, json={"assigned_to_id": None}).json()
    assert anyone["assigned_to_id"] is None
    assert client.post(f"/api/parked/{held['id']}/assign", headers=manager, json={"assigned_to_id": 999}).status_code == 400
    log = [a["detail"] for a in client.get("/api/audit", headers=admin, params={"action": "order_transfer"}).json()]
    assert log == ["Held order ($7.15) sent to any till", "Held order ($7.15) sent to manager", "Held order ($7.15) sent to cashier2"]
