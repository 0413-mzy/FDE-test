"""Explicit CLI/test engine creation; /health has no database dependency."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def product_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Product persistence requires postgresql+psycopg")
    options = str(url.query.get("options", "")) + " -c timezone=UTC"
    return create_engine(url, echo=False, hide_parameters=True, connect_args={"options": options})
