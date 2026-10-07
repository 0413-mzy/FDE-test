import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commerce.models import CommerceAccount, Inventory
from app.commerce.public_demo_seed import bootstrap_public_demo
from app.commerce.seed import seed_id
from app.core.config import Settings

pytestmark = pytest.mark.database


def settings():
    return Settings(
        _env_file=None,
        app_env="production",
        commerce_public_demo=True,
        commerce_public_demo_bootstrap=True,
        commerce_public_origin="https://demo.example.test",
        commerce_demo_password="public-fictional-password",
        commerce_operator_password="private-operator-secret-12345",
    )


def test_bootstrap_preserves_business_and_rejects_password_change(database):
    engine, _, _ = database
    configured = settings()
    bootstrap_public_demo(configured)
    with Session(engine) as db, db.begin():
        db.get(Inventory, seed_id("inventory/A")).on_hand = 99
    bootstrap_public_demo(configured)
    with Session(engine) as db:
        assert db.get(Inventory, seed_id("inventory/A")).on_hand == 99
        assert len(list(db.scalars(select(CommerceAccount)))) == 9
    changed = configured.model_copy(
        update={
            "commerce_demo_password": __import__("pydantic").SecretStr("changed-public-password")
        }
    )
    with pytest.raises(ValueError, match="configuration mismatch"):
        bootstrap_public_demo(changed)
    with Session(engine) as db:
        assert db.get(Inventory, seed_id("inventory/A")).on_hand == 99


def test_unknown_database_and_mode_are_refused(database):
    engine, _, _ = database
    with Session(engine) as db, db.begin():
        db.add(
            CommerceAccount(
                id=seed_id("unknown"),
                username="unknown",
                password_hash="unused",
                active=True,
                customer_enabled=True,
                demo_enabled=False,
            )
        )
    with pytest.raises(ValueError, match="accounts refused"):
        bootstrap_public_demo(settings())
    with Session(engine) as db:
        assert len(list(db.scalars(select(CommerceAccount)))) == 1
    with pytest.raises(ValueError, match="Explicit production"):
        bootstrap_public_demo(Settings(_env_file=None))


def test_global_image_quota_rolls_back_under_commerce_mutex(database):
    import base64
    import io
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from PIL import Image

    from app.commerce.catalog_models import ProductImage
    from app.main import create_app

    engine, _, _ = database
    configured = settings().model_copy(update={"commerce_image_quota_bytes": 1})
    bootstrap_public_demo(configured)
    app = create_app(configured, session_factory=lambda: Session(engine))
    client = TestClient(app)
    logged = client.post(
        "/api/commerce/v1/auth/login",
        json={
            "username": "owner.a",
            "password": configured.commerce_demo_password.get_secret_value(),
        },
    )
    assert logged.status_code == 200, logged.text
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(out, format="PNG")
    result = client.post(
        "/api/commerce/v1/merchant/shops/"
        + str(seed_id("shop/shopA"))
        + "/products/"
        + str(seed_id("product/A"))
        + "/experience/images",
        headers={
            "Authorization": "Bearer " + logged.json()["token"],
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "expected_version": 1,
            "data_base64": base64.b64encode(out.getvalue()).decode(),
            "alt": "fictional",
        },
    )
    assert result.status_code == 409 and result.json()["error"]["code"] == "IMAGE_STORAGE_LIMIT"
    with Session(engine) as db:
        assert not list(db.scalars(select(ProductImage)))


def test_bootstrap_preserves_suspended_visitor_but_requires_active_operators(database):
    engine, _, _ = database
    configured = settings()
    bootstrap_public_demo(configured)
    with Session(engine) as db, db.begin():
        db.get(CommerceAccount, seed_id("account/customer.a")).active = False
    bootstrap_public_demo(configured)
    with Session(engine) as db, db.begin():
        assert not db.get(CommerceAccount, seed_id("account/customer.a")).active
        db.get(CommerceAccount, seed_id("account/platform")).active = False
    with pytest.raises(ValueError, match="configuration mismatch"):
        bootstrap_public_demo(configured)
