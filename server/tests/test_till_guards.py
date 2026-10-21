"""Guards on the till: the drawer never pays out more cash than it holds, the server's clock dates sales, and
text that is too long for its column is refused up front instead of failing the save."""

from datetime import datetime, timedelta

from tests.conftest import product_by_name


def drawer(client, headers):
    return client.get("/api/shifts/current", headers=headers).json()["expected_cash"]


def sell(client, headers, product, **extra):
    body = {"items": [{"product_id": product["id"], "qty": 1}], "payments": [{"method": "cash", "amount": 500}], **extra}
    return client.post("/api/sales", headers=headers, json=body)


def test_cash_out_and_drawer_expenses_stop_at_what_the_drawer_holds(client, manager):
    client.post("/api/shifts/open", headers=manager, json={"opening_cash": 1000})

    too_much = client.post("/api/shifts/current/cash", headers=manager, json={"amount": -1001, "reason": "Bank"})
    assert too_much.status_code == 400 and "Only $10.00 is in the cash drawer" in too_much.text
    assert client.post("/api/shifts/current/cash", headers=manager, json={"amount": -400, "reason": "Bank"}).status_code == 200
    assert drawer(client, manager) == 600

    today = datetime.now().date().isoformat()
    expense = {"spent_on": today, "category": "Ice", "amount": 700, "from_drawer": True}
    assert client.post("/api/expenses", headers=manager, json=expense).status_code == 400
    made = client.post("/api/expenses", headers=manager, json={**expense, "amount": 500}).json()
    assert drawer(client, manager) == 100

    # raising a drawer expense takes the extra from the drawer too; lowering it puts cash back
    assert client.put(f"/api/expenses/{made['id']}", headers=manager, json={**expense, "amount": 601}).status_code == 400
    assert client.put(f"/api/expenses/{made['id']}", headers=manager, json={**expense, "amount": 600}).status_code == 200
    assert drawer(client, manager) == 0
    assert client.put(f"/api/expenses/{made['id']}", headers=manager, json={**expense, "amount": 200}).status_code == 200
    assert drawer(client, manager) == 400

    # cash in is never limited
    assert client.post("/api/shifts/current/cash", headers=manager, json={"amount": 99999, "reason": "Float"}).status_code == 200


def test_a_cash_refund_needs_the_cash_in_the_drawer(client, cashier, manager):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    sale = sell(client, cashier, coke).json()
    kept = drawer(client, cashier)
    assert kept == sale["total"]

    # the drawer was emptied to the safe: the refund cannot be paid from it
    client.post("/api/shifts/current/cash", headers=cashier, json={"amount": -kept, "reason": "Safe"})
    refund = {"reason": "Broken", "manager_pin": "2222"}
    short = client.post(f"/api/sales/{sale['id']}/refund", headers=cashier, json=refund)
    assert short.status_code == 400 and "cash drawer" in short.text
    assert client.get(f"/api/sales/{sale['id']}", headers=cashier).json()["status"] == "completed"

    client.post("/api/shifts/current/cash", headers=cashier, json={"amount": kept, "reason": "Back from safe"})
    done = client.post(f"/api/sales/{sale['id']}/refund", headers=cashier, json=refund)
    assert done.status_code == 200 and drawer(client, cashier) == 0


def test_the_servers_clock_dates_a_sale(client, cashier):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    today = datetime.now().strftime("%Y%m%d")

    # online: the phone's clock is ignored
    online = sell(client, cashier, coke, created_at="2030-01-01T10:00:00", client_uuid="clock-1").json()
    assert online["receipt_no"].startswith(today) and online["created_at"].startswith(datetime.now().date().isoformat())

    # offline from a phone whose clock runs ahead: saved as now, and the log says so
    ahead = sell(client, cashier, coke, offline=True, created_at="2030-01-01T10:00:00", client_uuid="clock-2").json()
    assert ahead["receipt_no"].startswith(today) and ahead["shift_id"] == online["shift_id"]

    # a few minutes ahead is just clocks disagreeing, and kept
    soon = (datetime.now() + timedelta(minutes=3)).replace(microsecond=0)
    near = sell(client, cashier, coke, offline=True, created_at=soon.isoformat(), client_uuid="clock-3").json()
    assert near["created_at"] == soon.isoformat()


def test_the_phone_clock_is_logged(client, cashier, admin):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    sell(client, cashier, coke, offline=True, created_at="2030-01-01T10:00:00", client_uuid="clock-4")
    log = [a["detail"] for a in client.get("/api/audit", headers=admin).json() if a["action"] == "offline_sale"]
    assert any("2030-01-01 10:00 by the phone's clock" in d for d in log)


def test_too_long_text_is_refused_before_saving(client, cashier, manager, admin):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 0})
    long_note = {"items": [{"product_id": coke["id"], "qty": 1, "note": "x" * 201}], "payments": [{"method": "cash", "amount": 500}]}
    assert client.post("/api/sales", headers=cashier, json=long_note).status_code == 422
    for path, body in (("/api/inventory/adjust", {"product_id": coke["id"], "qty": 1, "note": "x" * 201}),
                       ("/api/inventory/count", {"product_id": coke["id"], "counted_qty": 5, "note": "x" * 201})):
        assert client.post(path, headers=admin, json=body).status_code == 422, path
    assert client.post("/api/shifts/current/close", headers=cashier, json={"note": "x" * 501}).status_code == 422

    # a drawer expense with a long category and note still fits the drawer's reason column
    client.post("/api/shifts/open", headers=manager, json={"opening_cash": 10000})
    expense = {"spent_on": datetime.now().date().isoformat(), "category": "c" * 50, "note": "n" * 200,
               "amount": 100, "from_drawer": True}
    assert client.post("/api/expenses", headers=manager, json=expense).status_code == 201


def test_a_register_needs_a_name(client, admin):
    assert client.post("/api/registers", headers=admin, json={"name": "   "}).status_code == 400
    first = client.get("/api/registers", headers=admin).json()[0]
    blank = client.patch(f"/api/registers/{first['id']}", headers=admin, json={"name": "  "})
    assert blank.status_code == 400 and "name" in blank.text
    # changing only the capitals of its own name is fine
    assert client.patch(f"/api/registers/{first['id']}", headers=admin, json={"name": "COUNTER 1"}).json()["name"] == "COUNTER 1"
