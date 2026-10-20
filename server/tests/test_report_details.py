"""The reports in the Reports menu must add up to the summary for the same days."""
from conftest import product_by_name


def test_feature_reports_agree_with_the_summary(client, cashier, manager, admin):
    cola = product_by_name(client, cashier, "Coca-Cola 330ml")
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")
    client.post("/api/shifts/open", json={"opening_cash": 2000}, headers=cashier)
    customer = client.post("/api/customers", json={"name": "Sokha", "phone": "099111222"}, headers=cashier).json()

    def sell(body):
        response = client.post("/api/sales", json=body, headers=cashier)
        assert response.status_code == 201, response.text
        return response.json()

    s1 = sell({"items": [{"product_id": cola["id"], "qty": 4}, {"product_id": rice["id"], "qty": 1}],
               "payments": [{"method": "cash", "currency": "KHR", "amount": 50000}], "customer_id": customer["id"]})
    sell({"items": [{"product_id": rice["id"], "qty": 2}], "payments": [{"method": "khqr", "amount": 1430}]})
    sell({"items": [{"product_id": cola["id"], "qty": 2}], "discount_type": "percent", "discount_value": 1000,
          "manager_pin": "2222", "payments": [{"method": "card", "amount": 100}, {"method": "cash", "amount": 500}]})
    cola_line = next(i for i in s1["items"] if i["product_id"] == cola["id"])
    refund = client.post(f"/api/sales/{s1['id']}/refund", headers=cashier,
                         json={"items": [{"sale_item_id": cola_line["id"], "qty": 1}], "reason": "Dented", "manager_pin": "2222"})
    assert refund.status_code == 200, refund.text
    client.post("/api/sales/void", json={"kind": "line", "items": [{"name": "Cola", "qty": 1, "amount": 75}], "manager_pin": "2222"},
                headers=cashier)
    client.post("/api/inventory/write-off", json={"product_id": cola["id"], "qty": 2, "reason": "damaged"}, headers=manager)
    client.post("/api/inventory/stock-in", json={"product_id": rice["id"], "qty": 5, "unit_cost": 500}, headers=manager)
    expected = client.get("/api/shifts/current", headers=cashier).json()["expected_cash"]
    client.post("/api/shifts/current/close", json={"counted_usd": expected - 50}, headers=cashier)

    summary = client.get("/api/reports/summary", headers=manager).json()
    get = lambda name: client.get(f"/api/reports/{name}", headers=manager).json()  # noqa: E731

    products = get("products")
    assert sum(r["sales"] for r in products) == summary["net_sales"]
    assert sum(r["profit"] for r in products) == summary["profit"]
    assert sum(r["cost"] for r in products) == summary["cost"]
    assert next(r for r in products if r["name"] == "Coca-Cola 330ml")["qty"] == 4 + 2 - 1

    cashiers = get("cashiers")
    me = next(r for r in cashiers if r["name"] == "Cashier 1")
    assert sum(r["net"] for r in cashiers) == summary["net_sales"]
    assert me["sales_count"] == 3 and me["voids"] == 1 and me["shifts"] == 1 and me["over_short"] == -50
    assert me["discounts"] == summary["discounts"] + 0  # the refunded cola was not discounted

    payments = get("payments")
    assert sum(r["net"] for r in payments) == summary["net_sales"]
    cash = next(r for r in payments if r["method"] == "Cash")
    assert all(r["method"] in ("Cash", "Card", "KHQR", "Riel rounding") for r in payments)
    assert cash["received_khr"] == 50000 and cash["received_usd"] == 500 and cash["count"] == 2

    refunds = get("refunds")
    assert len(refunds) == 1 and refunds[0]["amount"] == summary["refunds"]
    assert refunds[0]["items"] == "1 x Coca-Cola 330ml" and refunds[0]["approved_by"] == "Store Manager"
    assert len(get("voids")) == 1

    discounts = get("discounts")
    assert len(discounts) == 1 and discounts[0]["approved_by"] == "manager" and discounts[0]["discount"] > 0

    shifts = get("shifts")
    assert len(shifts) == 1 and shifts[0]["variance"] == -50

    stock = get("stock")
    assert sum(p["value"] for p in stock["places"]) == summary["stock_value"]
    assert stock["losses"] == [{"name": "Damaged", "qty": 2, "value": 2 * cola["cost"]}]
    assert sum(r["value"] for r in stock["received"]) == summary["purchases"] == 2500  # opening stock had no cost

    customers = get("customers")
    assert len(customers) == 1 and customers[0]["name"] == "Sokha"
    assert customers[0]["spent"] == s1["total"] - refund.json()["amount"] and customers[0]["visits"] == 1


def test_feature_reports_need_the_reports_permission(client, cashier):
    for name in ("products", "cashiers", "payments", "refunds", "voids", "discounts", "shifts", "stock", "customers"):
        assert client.get(f"/api/reports/{name}", headers=cashier).status_code == 403, name
