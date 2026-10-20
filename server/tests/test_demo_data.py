from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.seed import DEMO_PRODUCTS, seed
from tests.conftest import login


def test_demo_history_is_consistent():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, demo_history=True, demo_images=False)  # keep test pictures out of server/uploads

    with TestClient(app) as client:
        manager = login(client, "manager")

        # stock ends exactly at the listed levels (+1 for any unit refunded back to the shelf)
        expected = {name: stock for items in DEMO_PRODUCTS.values() for name, _, _, _, stock in items}
        products = client.get("/api/products", headers=manager).json()
        assert len(products) == len(expected)
        for p in products:
            if p["track_stock"]:
                moves = client.get(f"/api/inventory/movements?product_id={p['id']}&limit=2000", headers=manager).json()
                assert sum(m["change"] for m in moves) == p["stock_qty"]
                assert p["stock_qty"] - expected[p["name"]] in (0, 1, 2, 3, 4)

        month = client.get("/api/reports/summary", headers=manager, params={
            "date_from": (date.today() - timedelta(days=29)).isoformat(), "date_to": date.today().isoformat(),
        }).json()
        assert month["sales_count"] > 200
        assert month["refunds"] > 0
        assert month["profit"] > 0
        assert {p["name"] for p in month["by_payment"]} == {"Cash", "Card", "KHQR"}

        shifts = client.get("/api/shifts", headers=manager).json()
        closed = [s for s in shifts if not s["is_open"]]
        assert closed and all(s["variance"] is not None for s in closed)

        assert len(client.get("/api/customers", headers=manager).json()) == 10
