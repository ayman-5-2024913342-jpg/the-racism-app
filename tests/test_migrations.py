"""The Alembic migration must produce exactly the schema the models describe."""
import os

from sqlalchemy import create_engine, inspect


def test_migration_matches_models(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    from app import models  # noqa: F401
    from app.config import BASE_DIR, get_settings
    from app.db import Base

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BASE_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
        command.upgrade(cfg, "head")
        insp = inspect(create_engine(url))
        for table in Base.metadata.sorted_tables:
            migrated = {c["name"]: c for c in insp.get_columns(table.name)}
            assert set(migrated) == {c.name for c in table.columns}, table.name
            for col in table.columns:
                assert migrated[col.name]["nullable"] == col.nullable, (table.name, col.name)
        indexed = {tuple(i["column_names"]) for i in insp.get_indexes("analyses")}
        assert {("owner_id",), ("expires_at",), ("saved",), ("shared",)} <= indexed
    finally:
        get_settings.cache_clear()
