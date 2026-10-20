from alembic import command
from sqlalchemy import create_engine

from app.migrate import alembic_config


def test_migrations_match_the_models(tmp_path):
    """Fails when a model changed without a new migration (fix: alembic revision --autogenerate -m "...")."""
    engine = create_engine(f"sqlite:///{tmp_path / 'check.db'}")
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        command.check(cfg)
