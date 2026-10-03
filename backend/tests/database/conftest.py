"""Every test owns a fresh PostgreSQL schema; never drop/truncate existing data."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.db.connection import product_engine


@pytest.fixture
def database(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Real PostgreSQL tests require explicit TEST_DATABASE_URL")
    # Restrict all cleanup to the generated schema, including a dedicated function namespace.
    schema = "fde_test_" + uuid4().hex
    bootstrap = product_engine(database_url)
    try:
        with bootstrap.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            bootstrap.url,
            echo=False,
            hide_parameters=True,
            connect_args={"options": f"-c search_path={schema} -c timezone=UTC"},
        )
        monkeypatch.setenv("DATABASE_URL", database_url)
        # The migration engine inherits this isolated search_path through the URL's options.
        migration_url = bootstrap.url.update_query_dict(
            {"options": f"-c search_path={schema} -c timezone=UTC"}
        ).render_as_string(hide_password=False)
        monkeypatch.setenv("DATABASE_URL", migration_url)
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        command.upgrade(config, "head")
        yield engine, config, schema
        engine.dispose()
    finally:
        with bootstrap.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        bootstrap.dispose()
