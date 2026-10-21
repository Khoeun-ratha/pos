"""Branches / warehouses and stock transfers between them and the main shop."""

from tests.conftest import product_by_name


def make_location(client, headers, name="Warehouse", kind="warehouse"):
    response = client.post("/api/locations", headers=headers, json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


def stock_at(client, headers, location_id, product_id):
    rows = client.get(f"/api/locations/{location_id}/stock", headers=headers).json()
    return next((r["qty"] for r in rows if r["product_id"] == product_id), 0)


def test_send_and_receive_moves_stock(client, manager):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    store = make_location(client, manager)
    # the warehouse gets a delivery
    received = client.post("/api/inventory/stock-in", headers=manager,
                           json={"product_id": coke["id"], "qty": 100, "location_id": store["id"]})
    assert received.status_code == 200, received.text
    assert received.json()["stock_qty"] == 100  # the reply shows the stock where it arrived
    assert product_by_name(client, manager, "Coca-Cola 330ml")["stock_qty"] == coke["stock_qty"]  # the shop's is untouched
    assert stock_at(client, manager, store["id"], coke["id"]) == 100

    # warehouse -> main shop: leaves the warehouse when sent, arrives when received
    sent = client.post("/api/transfers", headers=manager, json={
        "from_location_id": store["id"], "to_location_id": None, "items": [{"product_id": coke["id"], "qty": 30}],
    })
    assert sent.status_code == 201, sent.text
    transfer = sent.json()
    assert transfer["status"] == "in_transit" and transfer["from_name"] == "Warehouse" and transfer["to_name"] == "RATHA MART"
    assert transfer["transfer_no"].startswith("TR") and transfer["total_qty"] == 30
    assert stock_at(client, manager, store["id"], coke["id"]) == 70
    assert product_by_name(client, manager, "Coca-Cola 330ml")["stock_qty"] == coke["stock_qty"]

    done = client.post(f"/api/transfers/{transfer['id']}/receive", headers=manager)
    assert done.status_code == 200 and done.json()["status"] == "received" and done.json()["closed_by"] == "Store Manager"
    assert product_by_name(client, manager, "Coca-Cola 330ml")["stock_qty"] == coke["stock_qty"] + 30
    # only once
    assert client.post(f"/api/transfers/{transfer['id']}/receive", headers=manager).status_code == 400

    # history: the shop sees "transfer_in", the warehouse "transfer_out", both with the transfer number
    main = client.get("/api/inventory/movements", headers=manager,
                      params={"location": "main", "reference": transfer["transfer_no"]}).json()
    assert [(m["kind"], m["change"], m["location_name"]) for m in main] == [("transfer_in", 30, None)]
    away = client.get("/api/inventory/movements", headers=manager, params={"location": store["id"], "product_id": coke["id"]}).json()
    assert [(m["kind"], m["change"], m["balance"]) for m in away] == [("transfer_out", -30, 70), ("stock_in", 100, 100)]


def test_cancel_puts_the_stock_back(client, manager):
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")
    branch = make_location(client, manager, "Toul Kork branch", "branch")
    transfer = client.post("/api/transfers", headers=manager, json={
        "to_location_id": branch["id"], "items": [{"product_id": rice["id"], "qty": 2}, {"product_id": rice["id"], "qty": 1}],
    }).json()
    assert [(i["product_name"], i["qty"]) for i in transfer["items"]] == [("Jasmine Rice 5kg", 3)]  # same product added up
    assert product_by_name(client, manager, "Jasmine Rice 5kg")["stock_qty"] == rice["stock_qty"] - 3

    cancelled = client.post(f"/api/transfers/{transfer['id']}/cancel", headers=manager).json()
    assert cancelled["status"] == "cancelled"
    assert product_by_name(client, manager, "Jasmine Rice 5kg")["stock_qty"] == rice["stock_qty"]
    assert stock_at(client, manager, branch["id"], rice["id"]) == 0
    assert client.post(f"/api/transfers/{transfer['id']}/receive", headers=manager).status_code == 400


def test_cannot_send_what_is_not_there(client, manager, admin):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    store = make_location(client, manager)
    # even when the till may sell into negative stock, a truck cannot carry what is not there
    client.put("/api/settings", headers=admin, json={"allow_negative_stock": True})
    too_many = client.post("/api/transfers", headers=manager, json={
        "to_location_id": store["id"], "items": [{"product_id": coke["id"], "qty": coke["stock_qty"] + 1}],
    })
    assert too_many.status_code == 400 and "Only" in too_many.json()["detail"]
    empty = client.post("/api/transfers", headers=manager, json={
        "from_location_id": store["id"], "items": [{"product_id": coke["id"], "qty": 1}],
    })
    assert empty.status_code == 400 and "at Warehouse" in empty.json()["detail"]
    same = client.post("/api/transfers", headers=manager, json={"items": [{"product_id": coke["id"], "qty": 1}]})
    assert same.status_code == 400


def test_counts_and_write_offs_at_a_warehouse(client, manager):
    oil = product_by_name(client, manager, "Cooking Oil 1L")
    store = make_location(client, manager)
    client.post("/api/inventory/count", headers=manager, json={"product_id": oil["id"], "counted_qty": 12, "location_id": store["id"]})
    assert stock_at(client, manager, store["id"], oil["id"]) == 12
    lost = client.post("/api/inventory/write-off", headers=manager,
                       json={"product_id": oil["id"], "qty": 13, "reason": "damaged", "location_id": store["id"]})
    assert lost.status_code == 400
    client.post("/api/inventory/write-off", headers=manager,
                json={"product_id": oil["id"], "qty": 2, "reason": "damaged", "location_id": store["id"]})
    assert stock_at(client, manager, store["id"], oil["id"]) == 10
    assert product_by_name(client, manager, "Cooking Oil 1L")["stock_qty"] == oil["stock_qty"]


def test_stock_value_counts_every_place_and_the_road(client, manager):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    before = client.get("/api/reports/summary", headers=manager).json()["stock_value"]
    store = make_location(client, manager)
    client.post("/api/inventory/stock-in", headers=manager, json={"product_id": coke["id"], "qty": 10, "location_id": store["id"]})
    after_delivery = client.get("/api/reports/summary", headers=manager).json()["stock_value"]
    assert after_delivery == before + 10 * coke["cost"]
    client.post("/api/transfers", headers=manager, json={"from_location_id": store["id"], "items": [{"product_id": coke["id"], "qty": 4}]})
    assert client.get("/api/reports/summary", headers=manager).json()["stock_value"] == after_delivery  # on the road still counts


def test_location_with_open_transfers_cannot_be_closed(client, manager):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    store = make_location(client, manager)
    client.post("/api/transfers", headers=manager, json={"to_location_id": store["id"], "items": [{"product_id": coke["id"], "qty": 1}]})
    closed = client.patch(f"/api/locations/{store['id']}", headers=manager, json={"name": "Warehouse", "is_active": False})
    assert closed.status_code == 400
    assert client.post("/api/locations", headers=manager, json={"name": "Warehouse"}).status_code == 409


def test_transfers_need_the_inventory_permission(client, cashier):
    assert client.get("/api/transfers", headers=cashier).status_code == 403
    assert client.post("/api/locations", headers=cashier, json={"name": "X"}).status_code == 403
