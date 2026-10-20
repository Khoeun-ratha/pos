"""Brings the database up to the latest migration (server/migrations). Run on every service start,
or by hand with:  .venv\\Scripts\\alembic upgrade head"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import config
from .database import engine, ensure_database

SERVER_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    return cfg


def migrate() -> None:
    ensure_database(config.database_url)  # MySQL: CREATE DATABASE pos_db if missing
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        tables = inspect(connection).get_table_names()
        if "users" in tables and "alembic_version" not in tables:
            # made before migrations existed: the tables already match the first migration
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
