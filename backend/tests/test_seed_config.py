import secrets

import pytest

from app.db.connection import product_engine
from app.db.seed import validate_seed_config


@pytest.mark.parametrize("password", [None, "", " " * 12, "short", "x" * 129])
def test_seed_requires_explicit_valid_password(password):
    with pytest.raises(ValueError, match="DEMO_SEED_PASSWORD"):
        validate_seed_config("test", password)


def test_production_seed_is_refused_before_database_access():
    with pytest.raises(ValueError, match="restricted"):
        validate_seed_config("production", secrets.token_urlsafe(24))


def test_seed_preserves_password_exactly():
    password = " " + secrets.token_urlsafe(24) + " "
    assert validate_seed_config("test", password) == password


@pytest.mark.parametrize("url", ["sqlite://", "postgresql://localhost/order_support"])
def test_database_engine_requires_explicit_postgresql_driver(url):
    with pytest.raises(ValueError, match="postgresql\\+psycopg"):
        product_engine(url)
