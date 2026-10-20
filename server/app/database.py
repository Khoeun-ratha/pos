from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import config


class Base(DeclarativeBase):
    pass


def ensure_database(url: str) -> None:
    """MySQL: create the database (utf8mb4, for Khmer text) if it does not exist yet."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql") or not parsed.database:
        return
    server = create_engine(parsed.set(database=None), pool_pre_ping=True)
    with server.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{parsed.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    server.dispose()


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = make_engine(config.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
