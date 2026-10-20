import os

os.environ["POS_DATABASE_URL"] = "sqlite://"
os.environ["POS_SEED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, demo_history=False)
    with TestClient(app) as c:
        yield c


def login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": f"{username}123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def cashier(client):
    return login(client, "cashier")


@pytest.fixture()
def manager(client):
    return login(client, "manager")


@pytest.fixture()
def admin(client):
    return login(client, "admin")


def product_by_name(client: TestClient, headers, name: str) -> dict:
    return next(p for p in client.get("/api/products", headers=headers).json() if p["name"] == name)
