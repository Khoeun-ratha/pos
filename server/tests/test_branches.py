"""Branches sell: a register stands in a branch, its sales take the branch's stock, staff with a home branch work only
there, and the reports show each outlet."""

from datetime import date

from tests.conftest import product_by_name


def setup_branch(client, admin):
    """A branch with one register, stocked with 10 Coca-Cola from the main shop."""
    branch = client.post("/api/locations", headers=admin, json={"name": "Riverside", "kind": "branch"}).json()
    register = client.post("/api/registers", headers=admin, json={"name": "Riverside till", "location_id": branch["id"]}).json()
    coke = product_by_name(client, admin, "Coca-Cola 330ml")
    sent = client.post("/api/transfers", headers=admin, json={"to_location_id": branch["id"],
                                                               "items": [{"product_id": coke["id"], "qty": 10}]}).json()
    assert client.post(f"/api/transfers/{sent['id']}/receive", headers=admin).status_code == 200
    return branch, register, coke


def branch_stock(client, headers, branch, product):
    rows = client.get("/api/products", headers=headers, params={"location_id": branch["id"]}).json()
    return next(p["stock_qty"] for p in rows if p["id"] == product["id"])


def sell(client, headers, product, qty=1):
    return client.post("/api/sales", headers=headers, json={"items": [{"product_id": product["id"], "qty": qty}],
                                                            "payments": [{"method": "cash", "amount": 10000}]})


def test_a_register_stands_in_a_branch_not_a_warehouse(client, admin):
    branch, register, _ = setup_branch(client, admin)
    assert register["location_name"] == "Riverside"
    store = client.post("/api/locations", headers=admin, json={"name": "Back store", "kind": "warehouse"}).json()
    refused = client.post("/api/registers", headers=admin, json={"name": "Store till", "location_id": store["id"]})
    assert refused.status_code == 400 and "warehouse" in refused.text

    # moved back to the main shop (null), then to the branch again
    moved = client.patch(f"/api/registers/{register['id']}", headers=admin, json={"location_id": None}).json()
    assert moved["location_id"] is None
    # a rename alone does not move it
    renamed = client.patch(f"/api/registers/{register['id']}", headers=admin, json={"location_id": branch["id"]}).json()
    assert client.patch(f"/api/registers/{register['id']}", headers=admin, json={"name": "River 1"}).json()["location_id"] == branch["id"]
    assert renamed["location_name"] == "Riverside"


def test_a_branch_sale_takes_the_branch_stock_and_a_refund_puts_it_back(client, admin, cashier):
    branch, register, coke = setup_branch(client, admin)
    main_before = product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"]

    shift = client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 5000, "register_id": register["id"]}).json()
    assert shift["register_name"] == "Riverside till" and shift["location_name"] == "Riverside"
    sale = sell(client, cashier, coke, 3).json()
    assert sale["location_name"] == "Riverside"
    assert branch_stock(client, cashier, branch, coke) == 7
    assert product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"] == main_before  # the main shop's shelf is untouched

    client.put("/api/settings", headers=admin, json={"allow_negative_stock": False})
    too_many = sell(client, cashier, coke, 8)
    assert too_many.status_code == 400 and "at Riverside (have 7)" in too_many.text

    # refunded at the branch till: the cash comes out of its drawer
    refund = client.post(f"/api/sales/{sale['id']}/refund", headers=cashier,
                         json={"items": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}], "reason": "Dented", "manager_pin": "2222"})
    assert refund.status_code == 200
    assert branch_stock(client, cashier, branch, coke) == 8

    moves = client.get("/api/inventory/movements", headers=admin, params={"location": str(branch["id"])}).json()
    assert {m["kind"] for m in moves} >= {"sale", "refund"}


def test_staff_with_a_home_branch_work_only_there(client, admin, cashier):
    branch, register, coke = setup_branch(client, admin)
    staff = {s["username"]: s for s in client.get("/api/users/staff", headers=admin).json()}
    out = client.patch(f"/api/users/{staff['cashier2']['id']}", headers=admin, json={"location_id": branch["id"]}).json()
    assert out["location_name"] == "Riverside"
    token = client.post("/api/auth/login", json={"username": "cashier2", "password": "cashier123"}).json()["access_token"]
    river = {"Authorization": f"Bearer {token}"}

    main_till = next(r for r in client.get("/api/registers", headers=admin).json() if r["name"] == "Counter 1")
    elsewhere = client.post("/api/shifts/open", headers=river, json={"register_id": main_till["id"]})
    assert elsewhere.status_code == 400 and "works at Riverside" in elsewhere.text
    # no register asked for: the free one at their branch
    shift = client.post("/api/shifts/open", headers=river, json={"opening_cash": 0}).json()
    assert shift["register_name"] == "Riverside till"
    assert sell(client, river, coke).json()["location_name"] == "Riverside"
    # the branch's only till is busy: they are not sent to a main-shop till
    client.post("/api/shifts/current/close", headers=river, json={})
    client.post("/api/shifts/open", headers=cashier, json={"register_id": register["id"]})
    full = client.post("/api/shifts/open", headers=river, json={})
    assert full.status_code == 400 and "Every register at Riverside is in use" in full.text

    # the branch drawer can be handed only to someone who may work there
    me = staff["manager"]
    client.patch(f"/api/users/{me['id']}", headers=admin, json={"location_id": None})
    other = client.post("/api/locations", headers=admin, json={"name": "Hilltop", "kind": "branch"}).json()
    client.patch(f"/api/users/{staff['admin']['id']}", headers=admin, json={"location_id": other["id"]})
    wrong = client.post("/api/shifts/current/handover", headers=cashier,
                        json={"to_user_id": staff["admin"]["id"], "pin": "1111", "counted_usd": 0})
    assert wrong.status_code == 400 and "works at Hilltop" in wrong.text

    # a warehouse is not a place to work; a branch with staff or tills cannot be retired
    store = client.post("/api/locations", headers=admin, json={"name": "Back store", "kind": "warehouse"}).json()
    assert client.patch(f"/api/users/{staff['cashier']['id']}", headers=admin, json={"location_id": store["id"]}).status_code == 400
    retire = client.patch(f"/api/locations/{branch['id']}", headers=admin, json={"name": "Riverside", "kind": "branch", "is_active": False})
    assert retire.status_code == 400 and "move them first" in retire.text


def test_reports_by_outlet(client, admin, cashier, manager):
    branch, register, coke = setup_branch(client, admin)
    client.post("/api/shifts/open", headers=cashier, json={"register_id": register["id"]})
    at_branch = sell(client, cashier, coke, 2).json()
    client.post("/api/shifts/open", headers=manager, json={})  # a main-shop till
    at_main = sell(client, manager, coke, 1).json()
    client.post("/api/expenses", headers=admin, json={"spent_on": date.today().isoformat(), "category": "Rent", "amount": 5000})

    everything = client.get("/api/reports/summary", headers=admin).json()
    by_branch = {r["name"]: r["amount"] for r in everything["by_branch"]}
    assert by_branch == {"RATHA MART": at_main["total"], "Riverside": at_branch["total"]}
    assert everything["net_sales"] == at_main["total"] + at_branch["total"] and everything["expenses"] == 5000

    river = client.get("/api/reports/summary", headers=admin, params={"location": str(branch["id"])}).json()
    assert river["location_name"] == "Riverside" and river["sales_count"] == 1 and river["net_sales"] == at_branch["total"]
    assert river["expenses"] == 0  # expenses belong to the whole business
    assert river["stock_value"] == 8 * coke["cost"]

    main = client.get("/api/reports/summary", headers=admin, params={"location": "main"}).json()
    assert main["sales_count"] == 1 and main["net_sales"] == at_main["total"]
    assert client.get("/api/reports/summary", headers=admin, params={"location": "nowhere"}).status_code == 400

    xlsx = client.get("/api/reports/export", headers=admin, params={"location": str(branch["id"])})
    assert xlsx.status_code == 200 and "riverside" in xlsx.headers["content-disposition"]


# ---------- a day of the branch's own staff ----------

def pin_login(client, username, pin):
    token = client.post("/api/auth/pin-login", json={"username": username, "pin": pin}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def branch_staff(client, admin, branch):
    """A cashier and a manager who work at the branch, signed in with their PIN."""
    for username, role, pin in (("rivercash", "cashier", "5151"), ("riverboss", "manager", "6161")):
        made = client.post("/api/users", headers=admin, json={"username": username, "password": "secret1", "pin": pin,
                                                              "role": role, "location_id": branch["id"]})
        assert made.status_code == 201 and made.json()["location_name"] == "Riverside"
    return pin_login(client, "rivercash", "5151"), pin_login(client, "riverboss", "6161")


def test_a_branch_receipt_shows_the_branch(client, admin):
    branch, register, coke = setup_branch(client, admin)
    client.patch(f"/api/locations/{branch['id']}", headers=admin, json={"name": "Riverside", "kind": "branch", "address": "Sisowath Quay"})
    client.put("/api/settings", headers=admin, json={"store_address": "St 271, Phnom Penh"})
    client.post("/api/shifts/open", headers=admin, json={"register_id": register["id"]})
    receipt = client.get(f"/api/sales/{sell(client, admin, coke).json()['id']}/receipt", headers=admin).text
    assert "Riverside branch" in receipt and "Sisowath Quay" in receipt and "St 271" not in receipt


def test_held_orders_stay_at_their_outlet(client, admin, cashier):
    branch, register, coke = setup_branch(client, admin)
    river, _ = branch_staff(client, admin, branch)
    client.post("/api/shifts/open", headers=river, json={})
    held = client.post("/api/parked", headers=river, json={"items": [{"product_id": coke["id"], "qty": 1}], "label": "Table 2"}).json()

    client.post("/api/shifts/open", headers=cashier, json={})  # the main shop
    assert client.get("/api/parked", headers=cashier).json() == []
    assert client.post(f"/api/parked/{held['id']}/resume", headers=cashier).status_code == 404
    # it cannot be sent to someone who works at another branch
    staff = {s["username"]: s for s in client.get("/api/users/staff", headers=admin).json()}
    hill = client.post("/api/locations", headers=admin, json={"name": "Hilltop", "kind": "branch"}).json()
    client.patch(f"/api/users/{staff['cashier2']['id']}", headers=admin, json={"location_id": hill["id"]})
    sent = client.post(f"/api/parked/{held['id']}/assign", headers=river, json={"assigned_to_id": staff["cashier2"]["id"]})
    assert sent.status_code == 400 and "works at Hilltop" in sent.text

    assert [o["id"] for o in client.get("/api/parked", headers=river).json()] == [held["id"]]
    assert client.post(f"/api/parked/{held['id']}/resume", headers=river).status_code == 200


def test_goods_returned_at_a_branch_go_on_its_shelf(client, admin, cashier):
    branch, register, coke = setup_branch(client, admin)
    river, _ = branch_staff(client, admin, branch)
    client.post("/api/shifts/open", headers=cashier, json={})
    bought = sell(client, cashier, coke, 2).json()  # at the main shop
    main_after_sale = product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"]

    client.post("/api/shifts/open", headers=river, json={"opening_cash": 5000})
    back = client.post(f"/api/sales/{bought['id']}/refund", headers=river, json={"reason": "Wrong drink", "manager_pin": "6161"})
    assert back.status_code == 200
    assert branch_stock(client, admin, branch, coke) == 12  # the customer handed them in at Riverside
    assert product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"] == main_after_sale


def test_a_branch_manager_sees_and_runs_their_branch_only(client, admin, cashier):
    branch, register, coke = setup_branch(client, admin)
    river, boss = branch_staff(client, admin, branch)
    client.post("/api/shifts/open", headers=cashier, json={})
    main_sale = sell(client, cashier, coke).json()
    client.post("/api/shifts/open", headers=river, json={})
    river_sale = sell(client, river, coke, 2).json()

    # sales, receipts, shifts
    assert [s["id"] for s in client.get("/api/sales", headers=boss).json()] == [river_sale["id"]]
    assert client.get(f"/api/sales/{main_sale['id']}", headers=boss).status_code == 404
    assert [s["location_name"] for s in client.get("/api/shifts", headers=boss).json()] == ["Riverside"]
    main_shift = client.get("/api/shifts/current", headers=cashier).json()
    assert client.post(f"/api/shifts/{main_shift['id']}/close", headers=boss, json={}).status_code == 404
    river_shift = client.get("/api/shifts/current", headers=river).json()
    assert client.post(f"/api/shifts/{river_shift['id']}/close", headers=boss, json={}).status_code == 200

    # reports: always their branch; asking for another outlet is refused
    summary = client.get("/api/reports/summary", headers=boss).json()
    assert summary["location_name"] == "Riverside" and summary["net_sales"] == river_sale["total"]
    assert client.get("/api/reports/summary", headers=boss, params={"location": "main"}).status_code == 403
    products = client.get("/api/reports/products", headers=boss).json()
    assert [(r["name"], r["qty"]) for r in products] == [("Coca-Cola 330ml", 2)]
    assert [s["cashier_name"] for s in client.get("/api/reports/shifts", headers=boss).json()] == ["rivercash"]
    assert [p["name"] for p in client.get("/api/reports/stock", headers=boss).json()["places"]] == ["Riverside"]
    # the owner still sees everything, and can look at one outlet in every report
    assert len(client.get("/api/reports/shifts", headers=admin).json()) == 2
    assert [r["qty"] for r in client.get("/api/reports/products", headers=admin, params={"location": "main"}).json()] == [1]

    # low stock: the branch's own shelf (products never sent there count as 0)
    low = {p["name"]: p["stock_qty"] for p in client.get("/api/inventory/low-stock", headers=boss).json()}
    assert low and "Coca-Cola 330ml" not in low and set(low.values()) == {0}


def test_a_branch_manager_works_on_the_branch_stock(client, admin):
    branch, register, coke = setup_branch(client, admin)
    _, boss = branch_staff(client, admin, branch)
    main_before = product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"]

    received = client.post("/api/inventory/stock-in", headers=boss, json={"product_id": coke["id"], "qty": 6})
    assert received.status_code == 200 and received.json()["stock_qty"] == 16  # no place given: their branch
    counted = client.post("/api/inventory/count", headers=boss, json={"product_id": coke["id"], "counted_qty": 15})
    assert counted.json()["stock_qty"] == 15
    off = client.post("/api/inventory/write-off", headers=boss, json={"product_id": coke["id"], "qty": 1, "reason": "damaged",
                                                                      "location_id": branch["id"]})
    assert off.json()["stock_qty"] == 14
    other = client.post("/api/locations", headers=admin, json={"name": "Back store", "kind": "warehouse"}).json()
    elsewhere = client.post("/api/inventory/adjust", headers=boss, json={"product_id": coke["id"], "qty": -1, "location_id": other["id"]})
    assert elsewhere.status_code == 403 and "only its stock" in elsewhere.text
    assert product_by_name(client, admin, "Coca-Cola 330ml")["stock_qty"] == main_before
    assert {m["location_name"] for m in client.get("/api/inventory/movements", headers=boss).json()} == {"Riverside"}

    # transfers: send from the branch, receive what comes to it; never take from the main shop
    take = client.post("/api/transfers", headers=boss, json={"to_location_id": branch["id"], "items": [{"product_id": coke["id"], "qty": 1}]})
    assert take.status_code == 403
    back = client.post("/api/transfers", headers=boss, json={"from_location_id": branch["id"], "items": [{"product_id": coke["id"], "qty": 4}]})
    assert back.status_code == 201
    assert client.post(f"/api/transfers/{back.json()['id']}/receive", headers=boss).status_code == 403  # the main shop receives it
    incoming = client.post("/api/transfers", headers=admin, json={"to_location_id": branch["id"],
                                                                  "items": [{"product_id": coke["id"], "qty": 2}]}).json()
    assert client.post(f"/api/transfers/{incoming['id']}/cancel", headers=boss).status_code == 403  # the sender cancels
    assert client.post(f"/api/transfers/{incoming['id']}/receive", headers=boss).status_code == 200
    assert branch_stock(client, admin, branch, coke) == 12
    unrelated = client.post("/api/transfers", headers=admin, json={"to_location_id": other["id"],
                                                                   "items": [{"product_id": coke["id"], "qty": 1}]}).json()
    assert unrelated["id"] not in [t["id"] for t in client.get("/api/transfers", headers=boss).json()]
