"""Registers: every shift opens on a till, one open shift per till, the handover keeps the till, the admin manages them."""

from tests.conftest import product_by_name


def registers(client, headers):
    return {r["name"]: r for r in client.get("/api/registers", headers=headers).json()}


def open_shift(client, headers, **body):
    return client.post("/api/shifts/open", headers=headers, json={"opening_cash": 0, **body})


def test_a_shift_opens_on_a_free_register_and_the_receipt_says_which(client, cashier, manager):
    shift = open_shift(client, cashier).json()
    assert shift["register_name"] == "Counter 1"
    assert registers(client, manager)["Counter 1"]["open_by"] == "Cashier 1"

    # the next person gets the next free till; asking for a busy one is refused with who has it
    busy = open_shift(client, manager, register_id=shift["register_id"])
    assert busy.status_code == 400 and "Counter 1 is already open (Cashier 1)" in busy.text
    assert open_shift(client, manager).json()["register_name"] == "Counter 2"

    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    sale = client.post("/api/sales", headers=cashier, json={"items": [{"product_id": coke["id"], "qty": 1}],
                                                             "payments": [{"method": "cash", "amount": 500}]}).json()
    assert sale["register_name"] == "Counter 1"
    assert "Register: Counter 1" in client.get(f"/api/sales/{sale['id']}/receipt", headers=cashier).text

    # closing frees the till
    client.post("/api/shifts/current/close", headers=cashier, json={"counted_usd": 0})
    assert registers(client, manager)["Counter 1"]["open_by"] is None


def test_every_register_in_use(client, cashier, manager, admin):
    for name in ("Counter 3", "Counter 4", "Counter 5"):
        r = registers(client, admin)[name]
        assert client.patch(f"/api/registers/{r['id']}", headers=admin, json={"is_active": False}).status_code == 200
    open_shift(client, cashier)
    open_shift(client, manager)
    full = open_shift(client, admin)
    assert full.status_code == 400 and "Every register is in use" in full.text
    retired = registers(client, admin)["Counter 5"]
    assert open_shift(client, admin, register_id=retired["id"]).status_code == 400


def test_the_handover_keeps_the_register(client, cashier, manager):
    shift = open_shift(client, cashier, register_id=registers(client, manager)["Counter 3"]["id"]).json()
    assert shift["register_name"] == "Counter 3"
    staff = {s["username"]: s for s in client.get("/api/users/staff", headers=cashier).json()}
    out = client.post("/api/shifts/current/handover", headers=cashier,
                      json={"to_user_id": staff["cashier2"]["id"], "pin": "4444", "counted_usd": 0}).json()
    assert out["closed"]["register_name"] == out["opened"]["register_name"] == "Counter 3"
    assert registers(client, manager)["Counter 3"]["open_by"] == "Cashier 2"


def test_the_admin_manages_registers(client, cashier, manager, admin):
    assert client.post("/api/registers", headers=manager, json={"name": "Counter 9"}).status_code == 403
    made = client.post("/api/registers", headers=admin, json={"name": " Drinks bar "})
    assert made.status_code == 201 and made.json()["name"] == "Drinks bar"
    assert client.post("/api/registers", headers=admin, json={"name": "drinks BAR"}).status_code == 409

    bar = made.json()["id"]
    renamed = client.patch(f"/api/registers/{bar}", headers=admin, json={"name": "Coffee bar"}).json()
    assert renamed["name"] == "Coffee bar"

    # a till with an open drawer stays; so does the last one in use
    open_shift(client, cashier, register_id=bar)
    refused = client.patch(f"/api/registers/{bar}", headers=admin, json={"is_active": False})
    assert refused.status_code == 400 and "open shift" in refused.text
    client.post("/api/shifts/current/close", headers=cashier, json={"counted_usd": 0})
    for r in registers(client, admin).values():
        if r["name"] != "Counter 1":
            assert client.patch(f"/api/registers/{r['id']}", headers=admin, json={"is_active": False}).status_code == 200
    last = registers(client, admin)["Counter 1"]
    assert client.patch(f"/api/registers/{last['id']}", headers=admin, json={"is_active": False}).status_code == 400
    back = client.patch(f"/api/registers/{bar}", headers=admin, json={"is_active": True}).json()
    assert back["is_active"] is True

    actions = [a["action"] for a in client.get("/api/audit", headers=admin).json()]
    assert "register_create" in actions and "register_update" in actions


def test_shift_reports_show_the_register(client, cashier, manager):
    open_shift(client, cashier)
    client.post("/api/shifts/current/close", headers=cashier, json={"counted_usd": 0})
    rows = client.get("/api/reports/shifts", headers=manager).json()
    assert rows and rows[0]["register_name"] == "Counter 1"
