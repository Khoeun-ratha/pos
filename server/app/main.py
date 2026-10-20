import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import UPLOAD_DIR, config
from .database import SessionLocal, engine
from .migrate import migrate
from .routers import admin, auth, catalog, customers, inventory, locations, parked, reports, sales, shifts, suppliers, users
from .seed import seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate()  # creates pos_db and its tables, or updates them to the latest version
    if config.seed_demo_data:
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(title="POS Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins, allow_methods=["*"], allow_headers=["*"])

for module in (auth, users, catalog, inventory, locations, suppliers, customers, sales, parked, shifts, reports, admin):
    app.include_router(module.router)

# product photos (see app/images.py)
mimetypes.add_type("image/webp", ".webp")  # missing from some Windows registries
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "database": engine.dialect.name}
