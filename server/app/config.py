import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

SERVER_DIR = Path(__file__).resolve().parent.parent
SECRET_FILE = SERVER_DIR / ".jwt_secret"
UPLOAD_DIR = SERVER_DIR / "uploads"  # product photos; served at /uploads
ENV_FILE = SERVER_DIR / ".env"


def _load_env_file() -> None:
    """Read server/.env (KEY=VALUE lines). Real environment variables win."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _database_url() -> str:
    """POS_DATABASE_URL if set, else MySQL from DB_* settings, else a local SQLite file."""
    if os.getenv("POS_DATABASE_URL"):
        return os.environ["POS_DATABASE_URL"]
    if os.getenv("DB_USER"):
        user = quote_plus(os.environ["DB_USER"])
        password = quote_plus(os.getenv("DB_PASSWORD", ""))
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "pos_db")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    return "sqlite:///./pos.db"


def _jwt_secret() -> str:
    """POS_JWT_SECRET if set, else a random secret generated once and kept next to the app."""
    if os.getenv("POS_JWT_SECRET"):
        return os.environ["POS_JWT_SECRET"]
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(48))
    return SECRET_FILE.read_text().strip()


@dataclass(frozen=True)
class Config:
    database_url: str = field(default_factory=_database_url)
    jwt_secret: str = field(default_factory=_jwt_secret)
    jwt_algorithm: str = "HS256"
    token_minutes: int = field(default_factory=lambda: int(os.getenv("POS_TOKEN_MINUTES", "720")))
    seed_demo_data: bool = field(default_factory=lambda: os.getenv("POS_SEED", "true").lower() == "true")
    cors_origins: list[str] = field(default_factory=lambda: os.getenv("POS_CORS_ORIGINS", "*").split(","))


config = Config()
