"""Migrations use process DATABASE_URL only; never log connection credentials."""

import os

from alembic import context

from app.commerce import catalog_models, history, onboarding_models, platform_models  # noqa: F401
from app.commerce.models import Base as CommerceBase
from app.db.connection import product_engine
from app.db.models import Base

target_metadata = [Base.metadata, CommerceBase.metadata]
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required for Product migrations")

engine = product_engine(database_url)
if context.is_offline_mode():
    context.configure(url=engine.url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
engine.dispose()
