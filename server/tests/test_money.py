"""Money and stock checks: reports, shift cash, refunds, stock adjustments and CSV import."""

from datetime import date, datetime, timedelta

from app.database import SessionLocal
from app.models import Sale
from tests.conftest import product_by_name
from tests.test_api import checkout


def refund_all(client, headers, sale_id, reason="Returned"):
    return client.post(f"/api/sales/{sale_id}/refund", headers=headers, json={"reason": reason})


def open_shift(client, headers, cash=0):
    assert client.post("/api/shifts/open", headers=headers, json={"opening_cash": cash}).status_code == 201


def payments_of(report):
    return {p["name"]: p["amount"] for p in report["by_payment"]}


# ---------- reports and shift cash ----------

def test_report_counts_change_once_for_split_cash(client, cashier, manager):
    rice = product_by_name(client, cashier, "Jasmine Rice 5kg")  # 715
    payments = [{"method": "cash", "currency": "USD", "amount": 500}, {"method": "cash", "currency": "KHR", "amount": 10000}]
    sale = checkout(client, cashier, [{"product_id": rice["id"], "qty": 1}], payments).json()
    assert sale["change_due"] == 29
    assert payments_of(client.get("/api/reports/summary", headers=manager).json()) == {"Cash": 715}


def test_riel_rounding_shows_in_every_payment_breakdown(client, manager, admin):
    """$3.30 at 4100 is 13530 riel; the customer hands over 13500 (the 100-riel note), worth $3.29."""
    client.put("/api/settings", headers=admin, json={"exchange_rate": 4100, "tax_rate_bp": 0})
    product = client.post("/api/products", headers=manager, json={"name": "Rounding test", "price": 330, "stock_qty": 5}).json()
    open_shift(client, manager)
    sale = checkout(client, manager, [{"product_id": product["id"], "qty": 1}],
                    [{"method": "cash", "currency": "KHR", "amount": 13500}]).json()
    assert sale["total"] == 330 and sale["paid_total"] == 329

    report = client.get("/api/reports/summary", headers=manager).json()
    assert payments_of(report) == {"Cash": 329, "Riel rounding": 1}
    rows = client.get("/api/reports/payments", headers=manager).json()
    assert sum(r["net"] for r in rows) == report["net_sales"] == 330


def test_card_refund_leaves_the_cash_drawer_alone(client, manager):
    open_shift(client, manager, 2000)
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")
    sale = checkout(client, manager, [{"product_id": rice["id"], "qty": 1}], [{"method": "card", "amount": 715}]).json()
    assert refund_all(client, manager, sale["id"]).status_code == 200
    shift = client.get("/api/shifts/current", headers=manager).json()
    assert shift["cash_refunds"] == 0 and shift["expected_cash"] == 2000
    assert payments_of(client.get("/api/reports/summary", headers=manager).json()) == {"Card": 0}


def test_split_refund_takes_only_the_cash_part_from_the_drawer(client, manager):
    open_shift(client, manager)
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")  # 715 = 500 card + 215 cash
    payments = [{"method": "card", "amount": 500}, {"method": "cash", "amount": 215}]
    sale = checkout(client, manager, [{"product_id": rice["id"], "qty": 1}], payments).json()
    refund_all(client, manager, sale["id"])
    shift = client.get("/api/shifts/current", headers=manager).json()
    assert shift["cash_sales"] == 215 and shift["cash_refunds"] == 215 and shift["expected_cash"] == 0
    assert payments_of(client.get("/api/reports/summary", headers=manager).json()) == {"Card": 0, "Cash": 0}


def test_cash_refund_needs_an_open_shift(client, manager):
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    items = [{"product_id": coke["id"], "qty": 1}]
    cash_sale = checkout(client, manager, items, [{"method": "cash", "amount": 100}]).json()
    card_sale = checkout(client, manager, items, [{"method": "card", "amount": 83}]).json()
    client.post("/api/shifts/current/close", headers=manager, json={"counted_usd": 0, "counted_khr": 0})
    response = refund_all(client, manager, cash_sale["id"])
    assert response.status_code == 400 and "Open a shift" in response.json()["detail"]
    assert refund_all(client, manager, card_sale["id"]).status_code == 200  # nothing leaves the drawer


def test_report_totals_agree_after_refunds(client, manager):
    open_shift(client, manager)
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")
    coke = product_by_name(client, manager, "Coca-Cola 330ml")
    items = [{"product_id": rice["id"], "qty": 1}, {"product_id": coke["id"], "qty": 3}]
    sale = checkout(client, manager, items, [{"method": "cash", "amount": 5000}]).json()
    coke_line = next(i for i in sale["items"] if i["product_name"] == "Coca-Cola 330ml")
    body = {"items": [{"sale_item_id": coke_line["id"], "qty": 1}], "reason": "Dented"}
    assert client.post(f"/api/sales/{sale['id']}/refund", headers=manager, json=body).status_code == 200

    part = client.get("/api/reports/summary", headers=manager).json()
    assert part["net_sales"] == sale["total"] - part["refunds"]
    for rows in ("by_day", "by_hour", "by_payment", "by_cashier", "by_category"):
        assert sum(r["amount"] for r in part[rows]) == part["net_sales"], rows

    refund_all(client, manager, sale["id"])  # then the rest
    report = client.get("/api/reports/summary", headers=manager).json()
    assert report["gross_sales"] == sale["total"] and report["refunds"] == sale["total"] and report["net_sales"] == 0
    assert report["tax"] == 0 and report["discounts"] == 0 and report["cost"] == 0 and report["profit"] == 0
    assert report["top_products"] == [] and report["by_category"] == []


def test_refund_of_an_earlier_sale_does_not_change_the_old_report(client, manager):
    open_shift(client, manager)
    yesterday = date.today() - timedelta(days=1)
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")
    sale = checkout(client, manager, [{"product_id": rice["id"], "qty": 1}], [{"method": "cash", "amount": 715}]).json()
    with SessionLocal() as db:  # the server dates a sale itself: move it to yesterday morning
        db.get(Sale, sale["id"]).created_at = datetime.combine(yesterday, datetime.min.time()).replace(hour=10)
        db.commit()
    before = client.get("/api/reports/summary", headers=manager, params={"date_from": yesterday.isoformat()}).json()
    refund_all(client, manager, sale["id"])
    after = client.get("/api/reports/summary", headers=manager, params={"date_from": yesterday.isoformat()}).json()
    # stock value is "now", not part of the period: the refunded bag is back on the shelf
    assert after.pop("stock_value") > before.pop("stock_value")
    assert after == before and after["net_sales"] == 715 and after["profit"] == 650 - 520

    today = client.get("/api/reports/summary", headers=manager).json()
    assert today["sales_count"] == 0 and today["refunds"] == 715 and today["net_sales"] == -715
    assert today["profit"] == -(650 - 520) and today["tax"] == -65
    assert today["top_products"][0]["qty"] == -1


# ---------- refunds and sales ----------

def test_refund_takes_back_loyalty_points(client, manager):
    open_shift(client, manager)
    customer = client.post("/api/customers", headers=manager, json={"name": "Sokha", "phone": "099000111"}).json()
    rice = product_by_name(client, manager, "Jasmine Rice 5kg")
    sale = checkout(client, manager, [{"product_id": rice["id"], "qty": 2}], [{"method": "cash", "amount": 1430}],
                    customer_id=customer["id"]).json()

    def points():
        return client.get("/api/customers?q=Sokha", headers=manager).json()[0]["points"]

    assert points() == 14
    body = {"items": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}], "reason": "One bag torn"}
    client.post(f"/api/sales/{sale['id']}/refund", headers=manager, json=body)
    assert points() == 7  # $7.15 kept
    refund_all(client, manager, sale["id"])
    assert points() == 0


def test_receipt_number_clash_is_retried(client, cashier):
    coke = product_by_name(client, cashier, "Coca-Cola 330ml")
    items, pay = [{"product_id": coke["id"], "qty": 1}], [{"method": "cash", "amount": 100}]
    first = checkout(client, cashier, items, pay).json()
    with SessionLocal() as db:  # as if another till had just taken the next number
        sale = db.get(Sale, first["id"])
        sale.receipt_no = sale.receipt_no[:-4] + "0002"
        db.commit()
    second = checkout(client, cashier, items, pay)
    assert second.status_code == 201, second.text
    assert second.json()["receipt_no"].endswith("-0003")


# ---------- stock and catalog ----------

def test_adjustment_cannot_go_below_zero(client, manager):
    eggs = product_by_name(client, manager, "Eggs (10 pcs)")  # 3 in stock
    body = {"product_id": eggs["id"], "qty": -5, "note": "Broken"}
    response = client.post("/api/inventory/adjust", headers=manager, json=body)
    assert response.status_code == 400 and "Only 3" in response.json()["detail"]
    ok = client.post("/api/inventory/adjust", headers=manager, json={**body, "qty": -3})
    assert ok.json()["stock_qty"] == 0


def test_new_product_cannot_start_with_negative_stock(client, manager):
    assert client.post("/api/products", headers=manager, json={"name": "Test", "price": 100, "stock_qty": -4}).status_code == 422


def test_csv_import_checks_numbers(client, manager):
    header = "name,sku,barcode,category,price,cost,stock_qty,low_stock_threshold,track_stock,is_active\n"
    rows = [
        'Good Candy,,8888000000011,Snacks,$1.25,"1,000.50",4,5,true,true',
        "Bad Price,,8888000000012,Snacks,-1,0,4,5,true,true",
        "Bad Stock,,8888000000013,Snacks,1,0,-4,5,true,true",
        "Not Money,,8888000000014,Snacks,abc,0,4,5,true,true",
    ]
    files = {"file": ("p.csv", header + "\n".join(rows) + "\n", "text/csv")}
    result = client.post("/api/products/import", headers=manager, files=files).json()
    assert result["created"] == 1
    assert result["errors"] == [
        "Line 3: price cannot be negative",
        "Line 4: stock_qty cannot be negative",
        "Line 5: price 'abc' is not a number",
    ]
    candy = client.get("/api/products/barcode/8888000000011", headers=manager).json()
    assert candy["price"] == 125 and candy["cost"] == 100050


def test_csv_export_blocks_spreadsheet_formulas(client, manager):
    client.post("/api/products", headers=manager, json={"name": '=HYPERLINK("x")', "price": 100})
    assert "'=HYPERLINK" in client.get("/api/products/export", headers=manager).text
