"""Alembic migrations for the POS database (MySQL pos_db by default; see server/.env)."""

from alembic import context
from sqlalchemy import create_engine

from app.config import config as app_config
from app.database import Base
import app.models  # noqa: F401  (registers every table on Base.metadata)

target_metadata = Base.metadata


def database_url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or app_config.database_url


def run_offline() -> None:
    """`alembic upgrade head --sql`: write the SQL instead of running it (e.g. to run in Navicat)."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    # the app passes its own connection (see app/migrate.py); the alembic command line opens one
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(database_url())
    with engine.connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite cannot ALTER most columns
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
