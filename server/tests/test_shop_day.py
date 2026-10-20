"""A whole shop day, step by step, as the staff would do it. After every step the numbers are checked: stock,
average cost, the cash drawer, loyalty points, refunds, and finally that every report adds up."""

import uuid
from datetime import date

from app.pricing import khr_to_usd_cents
from tests.conftest import login


class Staff:
    """One person at a till: `do` expects success, `try_` returns the response."""

    def __init__(self, client, headers):
        self.client, self.headers = client, headers

    def try_(self, method, path, body=None, **params):
        return self.client.request(method, f"/api{path}", headers=self.headers, json=body, params=params or None)

    def do(self, method, path, body=None, **params):
        r = self.try_(method, path, body, **params)
        assert r.status_code in (200, 201, 204), f"{method} {path}: {r.status_code} {r.text}"
        return r.json() if r.content else None

    def quote(self, items, **discount):
        return self.do("POST", "/sales/quote", {"items": items, **discount})


def test_a_whole_shop_day(client):
    admin = Staff(client, login(client, "admin"))
    manager = Staff(client, login(client, "manager"))
    settings = admin.do("GET", "/settings")
    rate, per_usd = settings["exchange_rate"], settings["loyalty_points_per_usd"]
    today = date.today().isoformat()
    report = lambda: admin.do("GET", "/reports/summary", date_from=today, date_to=today)  # noqa: E731
    before = report()

    # --- morning: goods arrive, the cost becomes the average
    cat = admin.do("POST", "/categories", {"name": "Day test"})
    water = admin.do("POST", "/products", {"name": "Day water", "barcode": "2990000000017", "price": 125, "cost": 60,
                                           "category_id": cat["id"], "low_stock_threshold": 5})
    coffee = admin.do("POST", "/products", {"name": "Day coffee", "price": 300, "cost": 150, "category_id": cat["id"]})
    supplier = admin.do("POST", "/suppliers", {"name": "Day supplier"})
    admin.do("POST", "/inventory/stock-in", {"product_id": water["id"], "qty": 20, "unit_cost": 60, "supplier_id": supplier["id"]})
    w = admin.do("POST", "/inventory/stock-in", {"product_id": water["id"], "qty": 10, "unit_cost": 90, "supplier_id": supplier["id"]})
    assert (w["stock_qty"], w["cost"]) == (30, 70)  # (20 x 0.60 + 10 x 0.90) / 30
    admin.do("POST", "/inventory/stock-in", {"product_id": coffee["id"], "qty": 10, "unit_cost": 150})
    assert admin.do("GET", "/products/barcode/2990000000017")["id"] == water["id"]
    stock = lambda p: admin.do("GET", f"/products/{p['id']}")["stock_qty"]  # noqa: E731

    # --- the manager adds today's cashiers (not managers)
    assert manager.try_("POST", "/users", {"username": "dayboss", "password": "secret1", "role": "manager"}).status_code == 403
    manager.do("POST", "/users", {"username": "daycash", "full_name": "Day Cashier", "password": "secret1", "pin": "5678"})
    next_user = manager.do("POST", "/users", {"username": "daynext", "full_name": "Next Cashier", "password": "secret2", "pin": "8765"})
    assert manager.try_("POST", "/users", {"username": "daycash", "password": "secret1"}).status_code in (400, 409)

    def sign_in(username, password):
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        return Staff(client, {"Authorization": f"Bearer {r.json()['access_token']}"}), r.json()["user"]

    cash, me = sign_in("daycash", "secret1")
    nxt, _ = sign_in("daynext", "secret2")
    assert client.post("/api/auth/pin-login", json={"username": "daycash", "pin": "5678"}).status_code == 200

    # --- no sale before the drawer is counted
    two_and_one = [{"product_id": water["id"], "qty": 2}, {"product_id": coffee["id"], "qty": 1}]
    assert cash.try_("POST", "/sales", {"items": two_and_one, "payments": [{"method": "cash", "amount": 1000}]}).status_code == 400
    cash.do("POST", "/shifts/open", {"opening_cash": 2000})
    assert cash.try_("POST", "/shifts/open", {"opening_cash": 0}).status_code == 400

    # --- 1. plain cash sale, change in dollars and riel
    q = cash.quote(two_and_one)
    assert q["subtotal"] == 550
    s1 = cash.do("POST", "/sales", {"items": two_and_one, "payments": [{"method": "cash", "amount": 1000}]})
    assert s1["total"] == q["total"] and s1["change_due"] == 1000 - q["total"] and s1["change_due_khr"] % 100 == 0
    assert stock(water) == 28

    # --- 2. a discount needs a manager's PIN (not a cashier's)
    four = {"items": [{"product_id": water["id"], "qty": 4}], "discount_type": "percent", "discount_value": 1000,
            "payments": [{"method": "cash", "amount": 2000}]}
    for pin in (None, "9999", "3333"):
        assert cash.try_("POST", "/sales", {**four, "manager_pin": pin}).status_code == 403
    s2 = cash.do("POST", "/sales", {**four, "manager_pin": "2222"})
    assert s2["discount_total"] == 50
    assert cash.quote([{"product_id": water["id"], "qty": 1, "discount_type": "amount", "discount_value": 999}])["total"] >= 0
    assert cash.quote([{"product_id": water["id"], "qty": 1}], discount_type="percent", discount_value=20000)["total"] == 0

    # --- 3. riel: exact to the 100-riel note, short is refused, change worked out from riel
    one_coffee = [{"product_id": coffee["id"], "qty": 1}]
    qc = cash.quote(one_coffee)
    s3 = cash.do("POST", "/sales", {"items": one_coffee, "payments": [{"method": "cash", "currency": "KHR", "amount": qc["total_khr"]}]})
    assert s3["change_due"] == 0
    short = {"items": one_coffee, "payments": [{"method": "cash", "currency": "KHR", "amount": qc["total_khr"] - 1000}]}
    assert cash.try_("POST", "/sales", short).status_code == 400
    s3b = cash.do("POST", "/sales", {"items": one_coffee, "payments": [{"method": "cash", "currency": "KHR", "amount": 20000}]})
    assert s3b["change_due"] == khr_to_usd_cents(20000, rate) - qc["total"]

    # --- 4. card can't be more than the total; split card + cash gives change from the cash only
    assert cash.try_("POST", "/sales", {"items": [{"product_id": water["id"], "qty": 1}],
                                        "payments": [{"method": "card", "amount": 500}]}).status_code == 400
    two_water = [{"product_id": water["id"], "qty": 2}]
    s4 = cash.do("POST", "/sales", {"items": two_water, "payments": [{"method": "card", "amount": 100, "reference": "AP1"},
                                                                     {"method": "cash", "amount": 500}]})
    assert s4["change_due"] == 600 - cash.quote(two_water)["total"]
    s5 = cash.do("POST", "/sales", {"items": one_coffee, "payments": [{"method": "khqr", "amount": qc["total"], "reference": "TX9"}]})

    # --- 5. a customer earns points on whole dollars
    customer = admin.do("POST", "/customers", {"name": "Day customer", "phone": "012999888"})
    three = [{"product_id": coffee["id"], "qty": 3}]
    s6 = cash.do("POST", "/sales", {"items": three, "customer_id": customer["id"],
                                    "payments": [{"method": "cash", "amount": cash.quote(three)["total"]}]})
    assert admin.do("GET", f"/customers/{customer['id']}")["points"] == s6["total"] // 100 * per_usd

    # --- 6. stock limit (when the shop does not allow selling below 0), same product on two lines counts together
    assert stock(coffee) == 10 - 1 - 2 - 1 - 3
    admin.do("PUT", "/settings", {"allow_negative_stock": False})
    for items in ([{"product_id": coffee["id"], "qty": 4}], [{"product_id": coffee["id"], "qty": 3}, {"product_id": coffee["id"], "qty": 1}]):
        assert cash.try_("POST", "/sales", {"items": items, "payments": [{"method": "cash", "amount": 100000}]}).status_code == 400
    admin.do("PUT", "/settings", {"allow_negative_stock": True})

    # --- 7. a network retry with the same order id records one sale
    retry = {"items": [{"product_id": water["id"], "qty": 1}], "payments": [{"method": "cash", "amount": 200}], "client_uuid": str(uuid.uuid4())}
    first, again = cash.try_("POST", "/sales", retry), cash.try_("POST", "/sales", retry)
    assert (first.status_code, again.status_code) == (201, 200) and first.json()["id"] == again.json()["id"]
    s7 = first.json()
    water_left = stock(water)
    assert water_left == 30 - 2 - 4 - 2 - 1

    # --- 8. hold an order for the next till; only one till can resume it; throwing it away is a void
    held = cash.do("POST", "/parked", {"items": [{"product_id": water["id"], "qty": 3}], "label": "Lady in red", "assigned_to_id": next_user["id"]})
    seen = next(o for o in nxt.do("GET", "/parked") if o["id"] == held["id"])
    assert seen["assigned_to_id"] == next_user["id"] and seen["total"] == cash.quote([{"product_id": water["id"], "qty": 3}])["total"]
    assert stock(water) == water_left
    nxt.do("POST", f"/parked/{held['id']}/resume")
    assert cash.try_("POST", f"/parked/{held['id']}/resume").status_code == 404
    other = cash.do("POST", "/parked", {"items": [{"product_id": water["id"], "qty": 1}]})
    assert cash.try_("POST", f"/parked/{other['id']}/discard", {}).status_code == 403
    cash.do("POST", f"/parked/{other['id']}/discard", {"manager_pin": "2222"})
    void = {"kind": "line", "items": [{"name": "Day water", "qty": 1, "amount": 125}]}
    assert cash.try_("POST", "/sales/void", void).status_code == 403
    cash.do("POST", "/sales/void", {**void, "manager_pin": "2222"})

    # --- 9. refunds: PIN, never more than sold, partial refunds add up to the sale exactly, points come back
    line = next(i for i in s1["items"] if i["product_id"] == water["id"])
    refund = lambda sale, body: cash.try_("POST", f"/sales/{sale['id']}/refund", {"manager_pin": "2222", **body})  # noqa: E731
    assert cash.try_("POST", f"/sales/{s1['id']}/refund", {"items": [{"sale_item_id": line["id"], "qty": 1}], "reason": "x"}).status_code == 403
    assert refund(s1, {"items": [{"sale_item_id": line["id"], "qty": 3}], "reason": "x"}).status_code == 400
    r1 = refund(s1, {"items": [{"sale_item_id": line["id"], "qty": 1}], "reason": "Broken"}).json()
    assert r1["sale"]["status"] == "partially_refunded" and stock(water) == water_left + 1
    r2 = refund(s1, {"reason": "The rest"}).json()
    assert r1["amount"] + r2["amount"] == s1["total"] and r2["sale"]["status"] == "refunded"
    assert refund(s1, {"reason": "Again"}).status_code == 400
    r_card = refund(s5, {"reason": "QR"}).json()
    r_cust = refund(s6, {"items": [{"sale_item_id": s6["items"][0]["id"], "qty": 1}], "reason": "One back"}).json()
    kept = s6["total"] - r_cust["amount"]
    assert admin.do("GET", f"/customers/{customer['id']}")["points"] == kept // 100 * per_usd
    record = next(c for c in admin.do("GET", "/customers", q="Day customer"))
    assert (record["visits"], record["total_spent"]) == (1, kept) and record["last_visit"]
    r_split = refund(s4, {"reason": "Split"}).json()

    # --- 10. the drawer: every cash movement is accounted for
    cash.do("POST", "/shifts/current/cash", {"amount": 500, "reason": "Small change"})
    cash.do("POST", "/shifts/current/cash", {"amount": -300, "reason": "Ice"})
    assert cash.try_("POST", "/expenses", {"spent_on": today, "category": "Ice", "amount": 100, "from_drawer": True}).status_code == 403

    def kept_cash(sale):
        full = cash.do("GET", f"/sales/{sale['id']}")
        return sum(p["amount_usd"] for p in full["payments"] if p["method"] == "cash") - full["change_due"]

    cash_sales = sum(kept_cash(s) for s in (s1, s2, s3, s3b, s4, s6, s7))
    cash_refunds = r1["amount"] + r2["amount"] + r_cust["amount"] + kept_cash(s4)  # the card / QR parts stay out
    drawer = cash.do("GET", "/shifts/current")
    expected = 2000 + cash_sales + 500 - 300 - cash_refunds
    assert drawer["expected_cash"] == expected and drawer["cash_refunds"] == cash_refunds
    assert drawer["khqr_sales"] == s5["total"] and drawer["sales_count"] == 8

    # a manager's expense from their drawer follows edits and deletes
    manager.do("POST", "/shifts/open", {"opening_cash": 1000})
    expense = manager.do("POST", "/expenses", {"spent_on": today, "category": "Ice & supplies", "amount": 250, "from_drawer": True})
    expected_m = manager.do("GET", "/shifts/current")["expected_cash"]
    assert expected_m == 1000 - 250
    manager.do("PUT", f"/expenses/{expense['id']}", {"spent_on": today, "category": "Ice & supplies", "amount": 400})
    assert manager.do("GET", "/shifts/current")["expected_cash"] == 1000 - 400
    manager.do("DELETE", f"/expenses/{expense['id']}")
    assert manager.do("GET", "/shifts/current")["expected_cash"] == 1000
    manager.do("POST", "/expenses", {"spent_on": today, "category": "Rent", "amount": 5000})

    # --- 11. hand the drawer to the next cashier: $1.00 short, counted in dollars and riel
    handover = {"to_user_id": next_user["id"], "counted_usd": expected - 100 - 400, "counted_khr": 4 * rate}
    assert cash.try_("POST", "/shifts/current/handover", {**handover, "pin": "0000"}).status_code == 403
    assert cash.try_("POST", "/shifts/current/handover", {**handover, "to_user_id": me["id"], "pin": "5678"}).status_code == 400
    done = cash.do("POST", "/shifts/current/handover", {**handover, "pin": "8765"})
    assert done["closed"]["variance"] == -100 and done["opened"]["opening_cash"] == expected - 100
    assert cash.do("GET", "/shifts/current") is None
    assert cash.try_("POST", "/sales", {"items": one_coffee, "payments": [{"method": "cash", "amount": 500}]}).status_code == 400
    one_water = [{"product_id": water["id"], "qty": 1}]
    s8 = nxt.do("POST", "/sales", {"items": one_water, "payments": [{"method": "cash", "amount": cash.quote(one_water)["total"]}]})
    drawer2 = nxt.do("GET", "/shifts/current")
    assert drawer2["expected_cash"] == expected - 100 + s8["total"]
    assert nxt.do("POST", "/shifts/current/close", {"counted_usd": drawer2["expected_cash"] + 50})["variance"] == 50
    late = cash.try_("POST", f"/sales/{s3['id']}/refund", {"reason": "Late", "manager_pin": "2222"})
    assert late.status_code == 400 and "shift" in late.text.lower()  # cash comes out of a drawer

    # --- 12. who may do what
    assert cash.try_("GET", "/reports/summary").status_code == 403
    assert cash.try_("GET", "/users").status_code == 403
    assert cash.try_("POST", "/inventory/stock-in", {"product_id": water["id"], "qty": 1}).status_code == 403
    assert cash.try_("GET", f"/sales/{s8['id']}").status_code == 404  # another cashier's sale
    assert cash.try_("PUT", "/settings", {"store_name": "Mine now"}).status_code == 403
    assert cash.try_("PATCH", f"/users/{me['id']}", {"role": "admin"}).status_code == 403
    admin_id = next(u["id"] for u in manager.do("GET", "/users") if u["username"] == "admin")
    assert manager.try_("PATCH", f"/users/{admin_id}", {"password": "taken123"}).status_code == 403
    assert manager.try_("PATCH", f"/users/{me['id']}", {"role": "manager"}).status_code == 403
    manager.do("PATCH", f"/users/{next_user['id']}", {"is_active": False})
    assert nxt.try_("GET", "/auth/me").status_code == 401
    manager.do("PATCH", f"/users/{next_user['id']}", {"is_active": True})

    # --- 13. stock: write-off, count, and the history always adds up to the level
    have = stock(water)
    assert admin.try_("POST", "/inventory/write-off", {"product_id": water["id"], "qty": have + 1, "reason": "damaged"}).status_code == 400
    admin.do("POST", "/inventory/write-off", {"product_id": water["id"], "qty": 2, "reason": "expired"})
    counted = admin.do("POST", "/inventory/count", {"product_id": water["id"], "counted_qty": have - 3})["stock_qty"]
    assert counted == have - 3
    history = admin.do("GET", "/inventory/movements", product_id=water["id"], limit=500)
    assert sum(m["change"] for m in history) == counted == max(history, key=lambda m: m["id"])["balance"]

    # --- 14. a branch: stock leaves at once, arrives on receipt, a cancel puts it back
    branch = admin.do("POST", "/locations", {"name": "Day branch", "kind": "branch"})
    main = stock(water)
    too_many = {"to_location_id": branch["id"], "items": [{"product_id": water["id"], "qty": main + 1}]}
    assert admin.try_("POST", "/transfers", too_many).status_code == 400
    t = admin.do("POST", "/transfers", {"to_location_id": branch["id"], "items": [{"product_id": water["id"], "qty": 5}]})
    assert stock(water) == main - 5
    admin.do("POST", f"/transfers/{t['id']}/receive")
    at_branch = lambda: next(x["qty"] for x in admin.do("GET", f"/locations/{branch['id']}/stock") if x["product_id"] == water["id"])  # noqa: E731
    assert at_branch() == 5
    assert admin.try_("POST", f"/transfers/{t['id']}/receive").status_code == 400
    assert admin.try_("POST", f"/transfers/{t['id']}/cancel").status_code == 400
    back = admin.do("POST", "/transfers", {"from_location_id": branch["id"], "items": [{"product_id": water["id"], "qty": 2}]})
    admin.do("POST", f"/transfers/{back['id']}/cancel")
    assert at_branch() == 5

    # --- 15. a phone's offline sale keeps the phone's price, needs no shift, and syncs once
    offline = {"items": [{"product_id": water["id"], "qty": 1, "unit_price": 100}], "payments": [{"method": "cash", "amount": 200}],
               "offline": True, "client_uuid": str(uuid.uuid4()), "exchange_rate": rate}
    o1, o2 = cash.try_("POST", "/sales", offline), cash.try_("POST", "/sales", offline)
    assert o1.status_code == 201 and o1.json()["items"][0]["unit_price"] == 100
    assert o2.status_code == 200 and o2.json()["id"] == o1.json()["id"]

    # --- 16. a product taken off sale can't be sold
    admin.do("PUT", f"/products/{coffee['id']}", {"name": "Day coffee", "price": 300, "cost": 150, "category_id": cat["id"], "is_active": False})
    nxt.do("POST", "/shifts/open", {"opening_cash": 0})
    assert nxt.try_("POST", "/sales", {"items": one_coffee, "payments": [{"method": "cash", "amount": 500}]}).status_code == 400
    nxt.do("POST", "/shifts/current/close", {"counted_usd": 0})

    # --- 17. receipts, reprints marked as copies
    text = cash.try_("GET", f"/sales/{s2['id']}/receipt").text
    assert s2["receipt_no"] in text and f"${s2['total'] / 100:.2f}" in text
    assert "REPRINT" in cash.try_("GET", f"/sales/{s2['id']}/receipt", reprint=True).text.upper()

    # --- 18. evening: every report adds up
    after = report()
    sales = [s1, s2, s3, s3b, s4, s5, s6, s7, s8, o1.json()]
    refunds = r1["amount"] + r2["amount"] + r_card["amount"] + r_cust["amount"] + r_split["amount"]
    assert after["sales_count"] - before["sales_count"] == len(sales)
    assert after["gross_sales"] - before["gross_sales"] == sum(s["total"] for s in sales)
    assert after["refunds"] - before["refunds"] == refunds
    assert after["net_sales"] == after["gross_sales"] - after["refunds"]
    assert after["expenses"] - before["expenses"] == 5000 and after["net_profit"] == after["profit"] - after["expenses"]
    for rows in ("by_payment", "by_cashier", "by_category", "by_day", "by_hour"):
        assert sum(r["amount"] for r in after[rows]) == after["net_sales"], rows
    period = {"date_from": today, "date_to": today}
    assert sum(r["net"] for r in admin.do("GET", "/reports/payments", **period)) == after["net_sales"]
    cashiers = admin.do("GET", "/reports/cashiers", **period)
    assert sum(r["net"] for r in cashiers) == after["net_sales"]
    assert next(r for r in cashiers if r["name"] == "Day Cashier")["voids"] >= 1
    assert any(s["variance"] == -100 for s in admin.do("GET", "/reports/shifts", **period))
    assert admin.try_("GET", "/reports/export", **period).status_code == 200
    actions = {a["action"] for a in admin.do("GET", "/audit", limit=300)}
    assert {"discount", "refund", "void", "shift_handover", "cash_out", "expense", "stock_in", "order_transfer"} <= actions
