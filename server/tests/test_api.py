from tests.conftest import login, product_by_name


def checkout(client, headers, items, payments, **extra):
    # selling needs an open shift (the service answers 400 when one is already open, which is fine here)
    client.post("/api/shifts/open", headers=headers, json={"opening_cash": 0})
    return client.post("/api/sales", headers=headers, json={"items": items, "payments": payments, **extra})


def test_login_and_me(client, cashier):
    me = client.get("/api/auth/me", headers=cashier).json()
    assert me["username"] == "cashier" and me["role"] == "cashier"
    assert client.post("/api/auth/login", json={"username": "cashier", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/pin-login", json={"username": "cashier", "pin": "3333"}).status_code == 200


def test_cashier_cannot_manage_products(client, cashier):
    response = client.post("/api/products", headers=cashier, json={"name": "X", "price": 100})
    assert response.status_code == 403


def test_full_sale_flow(client, cashier, manager):
    shift = client.post("/api/shifts/open", headers=cashier, json={"opening_cash": 5000})
    assert shift.status_code == 201

    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    items = [{"product_id": coke["id"], "qty": 2}]

    quote = client.post("/api/sales/quote", headers=cashier, json={"items": items}).json()
    assert quote["subtotal"] == 150 and quote["tax_total"] == 15 and quote["total"] == 165

    response = checkout(client, cashier, items, [{"method": "cash", "currency": "USD", "amount": 500}], client_uuid="abc-1")
    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["change_due"] == 335
    assert sale["change_due_khr"] == 13700

    # retrying the same offline sale returns the original instead of a duplicate
    again = checkout(client, cashier, items, [{"method": "cash", "currency": "USD", "amount": 500}], client_uuid="abc-1")
    assert again.status_code == 200 and again.json()["id"] == sale["id"]

    assert product_by_name(client, cashier, "Coca-Cola 330ml")["stock_qty"] == coke["stock_qty"] - 2

    receipt = client.get(f"/api/sales/{sale['id']}/receipt", headers=cashier).text
    assert sale["receipt_no"] in receipt and "TOTAL" in receipt

    # refund one can: cashier needs a manager PIN
    item_id = sale["items"][0]["id"]
    body = {"items": [{"sale_item_id": item_id, "qty": 1}], "reason": "Damaged"}
    assert client.post(f"/api/sales/{sale['id']}/refund", headers=cashier, json=body).status_code == 403
    refund = client.post(f"/api/sales/{sale['id']}/refund", headers=cashier, json={**body, "manager_pin": "2222"})
    assert refund.status_code == 200, refund.text
    assert refund.json()["amount"] == 83  # half of 165, rounded
    assert refund.json()["sale"]["status"] == "partially_refunded"

    # refunding the rest gives back exactly what is left
    rest = client.post(f"/api/sales/{sale['id']}/refund", headers=cashier, json={"reason": "Changed mind", "manager_pin": "2222"})
    assert rest.json()["amount"] == 82
    assert rest.json()["sale"]["status"] == "refunded"

    closed = client.post("/api/shifts/current/close", headers=cashier, json={"counted_usd": 5000, "counted_khr": 0})
    report = closed.json()
    assert report["cash_sales"] == 165
    assert report["cash_refunds"] == 165
    assert report["expected_cash"] == 5000
    assert report["variance"] == 0


def test_khr_payment_with_rounding(client, cashier):
    noodles = product_by_name(client, cashier, "Mama Instant Noodles")  # $0.25 + 10% = $0.28 = 1,148 riel
    items = [{"product_id": noodles["id"], "qty": 1}]
    response = checkout(client, cashier, items, [{"method": "cash", "currency": "KHR", "amount": 1100}])
    assert response.status_code == 201, response.text
    too_little = checkout(client, cashier, items, [{"method": "cash", "currency": "KHR", "amount": 1000}])
    assert too_little.status_code == 400


def test_card_cannot_overpay(client, cashier):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    response = checkout(client, cashier, [{"product_id": rice["id"], "qty": 1}], [{"method": "card", "amount": 10000}])
    assert response.status_code == 400


def test_split_payment(client, cashier):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")  # 650 + 65 = 715
    payments = [{"method": "card", "currency": "USD", "amount": 500}, {"method": "cash", "currency": "KHR", "amount": 10000}]
    sale = checkout(client, cashier, [{"product_id": rice["id"], "qty": 1}], payments).json()
    assert sale["total"] == 715
    assert sale["change_due"] == 29  # 10,000 riel = 244 cents against 215 still due


def test_cashier_discount_needs_manager_pin(client, cashier):
    oreo = product_by_name(client, cashier, "Oreo 133g")
    items = [{"product_id": oreo["id"], "qty": 1, "discount_type": "percent", "discount_value": 1000}]
    pay = [{"method": "cash", "amount": 1000}]
    assert checkout(client, cashier, items, pay).status_code == 403
    assert checkout(client, cashier, items, pay, manager_pin="9999").status_code == 403
    assert checkout(client, cashier, items, pay, manager_pin="2222").status_code == 201


def test_inventory_and_low_stock(client, manager):
    eggs = product_by_name(client, manager, "Eggs (10 pcs)")
    low = [p["name"] for p in client.get("/api/inventory/low-stock", headers=manager).json()]
    assert "Eggs (10 pcs)" in low

    updated = client.post("/api/inventory/stock-in", headers=manager, json={"product_id": eggs["id"], "qty": 20}).json()
    assert updated["stock_qty"] == eggs["stock_qty"] + 20
    counted = client.post("/api/inventory/count", headers=manager, json={"product_id": eggs["id"], "counted_qty": 10}).json()
    assert counted["stock_qty"] == 10
    moves = client.get(f"/api/inventory/movements?product_id={eggs['id']}", headers=manager).json()
    assert [m["kind"] for m in moves][:2] == ["count", "stock_in"]


def test_negative_stock_can_be_blocked(client, admin, cashier):
    client.put("/api/settings", headers=admin, json={"allow_negative_stock": False})
    eggs = product_by_name(client, cashier, "Eggs (10 pcs)")
    response = checkout(client, cashier, [{"product_id": eggs["id"], "qty": 99}], [{"method": "cash", "amount": 100000}])
    assert response.status_code == 400
    assert "Not enough stock" in response.json()["detail"]


def test_customer_points_and_report(client, cashier, manager):
    customer = client.post("/api/customers", headers=cashier, json={"name": "Dara", "phone": "012345678"}).json()
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    checkout(client, cashier, [{"product_id": rice["id"], "qty": 2}], [{"method": "cash", "amount": 2000}], customer_id=customer["id"])
    customers = client.get("/api/customers?q=Dara", headers=cashier).json()
    assert customers[0]["points"] == 14  # $14.30 -> 14 points

    report = client.get("/api/reports/summary", headers=manager).json()
    assert report["sales_count"] == 1
    assert report["gross_sales"] == 1430
    assert report["profit"] == 2 * (650 - 520)
    assert report["top_products"][0]["name"] == "Jasmine Rice 5kg"
    assert len(report["by_hour"]) == 24
    assert sum(h["amount"] for h in report["by_hour"]) == report["gross_sales"]
    assert sum(h["count"] for h in report["by_hour"]) == 1
    assert client.get("/api/reports/summary", headers=cashier).status_code == 403


def test_csv_round_trip(client, manager):
    csv_text = client.get("/api/products/export", headers=manager).text
    assert csv_text.startswith("name,sku,barcode")
    new_row = "Durian Candy,,8888000000001,Snacks,0.50,0.30,40,5,true,true\n"
    result = client.post(
        "/api/products/import", headers=manager,
        files={"file": ("products.csv", csv_text + new_row, "text/csv")},
    ).json()
    assert result["created"] == 1 and result["errors"] == []
    assert client.get("/api/products/barcode/8888000000001", headers=manager).json()["price"] == 50


def test_admin_user_management(client, admin):
    created = client.post("/api/users", headers=admin, json={"username": "sokha", "password": "secret1", "pin": "4444", "role": "cashier"})
    assert created.status_code == 201
    assert login(client, "admin")
    assert client.post("/api/auth/pin-login", json={"username": "sokha", "pin": "4444"}).status_code == 200
    audit = client.get("/api/audit?action=user_create", headers=admin).json()
    assert audit[0]["detail"].startswith("sokha")


def test_barcode_lookup_accepts_upc_and_ean(client, manager, cashier):
    client.post("/api/products", headers=manager, json={"name": "Imported Biscuits", "price": 150, "barcode": "0012345678905", "sku": "BIS-01"})
    client.post("/api/products", headers=manager, json={"name": "Local Soap", "price": 90, "barcode": "123456789012"})
    # a scanner set to UPC-A drops the leading 0 of the EAN-13; one set to EAN-13 adds it
    assert client.get("/api/products/barcode/012345678905", headers=cashier).json()["name"] == "Imported Biscuits"
    assert client.get("/api/products/barcode/0123456789012", headers=cashier).json()["name"] == "Local Soap"
    assert client.get("/api/products/barcode/BIS-01", headers=cashier).json()["name"] == "Imported Biscuits"
    assert client.get("/api/products/barcode/999999999999", headers=cashier).status_code == 404
