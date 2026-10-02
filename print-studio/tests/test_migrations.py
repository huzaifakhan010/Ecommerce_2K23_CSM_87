"""The Alembic migration must build (and remove) the same schema the models describe."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.database import Base

ROOT = Path(__file__).resolve().parent.parent


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_creates_every_model_table_and_downgrade_removes_them(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    command.upgrade(_config(url), "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert set(Base.metadata.tables) <= tables

    for table_name, table in Base.metadata.tables.items():
        model_columns = {c.name for c in table.columns}
        db_columns = {c["name"] for c in inspector.get_columns(table_name)}
        assert model_columns == db_columns, table_name

    unique_names = {u["name"] for u in inspector.get_unique_constraints("skus")}
    assert "uq_skus_code" in unique_names
    index_names = {i["name"] for i in inspector.get_indexes("skus")}
    assert "uq_skus_one_default_per_product" in index_names

    command.downgrade(_config(url), "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
    engine.dispose()
