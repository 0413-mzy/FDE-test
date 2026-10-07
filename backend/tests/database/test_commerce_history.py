"""History checks against real PostgreSQL including physical SQL writes."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.commerce.seed import seed_commerce

pytestmark = pytest.mark.database
PASSWORD = "history-test-secret-123"


def history(connection, table, identifier=None):
    return (
        connection.execute(
            text(
                "SELECT * FROM commerce_record_history WHERE entity_table=:table "
                "AND (CAST(:identifier AS uuid) IS NULL OR entity_id=CAST(:identifier AS uuid)) "
                "ORDER BY id"
            ),
            {"table": table, "identifier": str(identifier) if identifier else None},
        )
        .mappings()
        .all()
    )


def test_direct_changes_delete_noop_and_rollback(database):
    engine, _, _ = database
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, datetime(2026, 10, 7, tzinfo=UTC))
    with engine.begin() as conn:
        product = conn.scalar(text("SELECT id FROM commerce_products LIMIT 1"))
        old = conn.scalar(text("SELECT title FROM commerce_products WHERE id=:id"), {"id": product})
        conn.execute(
            text("UPDATE commerce_products SET title='First' WHERE id=:id"), {"id": product}
        )
        conn.execute(
            text("UPDATE commerce_products SET title='Second' WHERE id=:id"), {"id": product}
        )
        rows = history(conn, "commerce_products", product)
        assert [r["operation"] for r in rows] == ["INSERT", "UPDATE", "UPDATE"]
        assert rows[1]["before_data"]["title"] == old
        assert rows[1]["after_data"]["title"] == "First"
        assert rows[2]["before_data"]["title"] == "First"
        assert rows[2]["changed_fields"] == ["title"]
        assert rows[2]["actor_id"] is None
        assert rows[2]["action"] == "DIRECT_SQL"
        assert rows[2]["recorded_at"].tzinfo is not None
        conn.execute(text("UPDATE commerce_products SET title=title WHERE id=:id"), {"id": product})
        assert len(history(conn, "commerce_products", product)) == 3
        cart = conn.scalar(text("SELECT id FROM commerce_carts LIMIT 1"))
        sku = conn.scalar(text("SELECT id FROM commerce_skus LIMIT 1"))
        line = conn.scalar(
            text(
                "INSERT INTO commerce_cart_lines "
                "(id,version,created_at,updated_at,cart_id,sku_id,quantity,"
                "seen_price_version,seen_price_minor) "
                "VALUES (gen_random_uuid(),1,now(),now(),:cart,:sku,1,1,1000) RETURNING id"
            ),
            {"cart": cart, "sku": sku},
        )
        conn.execute(text("DELETE FROM commerce_cart_lines WHERE id=:id"), {"id": line})
        deleted = history(conn, "commerce_cart_lines", line)[-1]
        assert deleted["operation"] == "DELETE"
        assert deleted["before_data"]["quantity"] == 1
        assert deleted["after_data"] is None
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("UPDATE commerce_products SET title='Rolled back' WHERE id=:id"), {"id": product}
        )
        tx.rollback()
        assert len(history(conn, "commerce_products", product)) == 3


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE commerce_record_history SET action='forged'",
        "DELETE FROM commerce_record_history",
        "TRUNCATE commerce_record_history",
    ],
)
def test_history_immutable(database, statement):
    engine, _, _ = database
    with pytest.raises(DBAPIError, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text(statement))


def test_api_actor_public_login_and_idempotent_cart(database):
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    engine, _, _ = database
    with Session(engine) as db:
        seed_commerce(db, PASSWORD)
    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine))
    with TestClient(app) as client:
        login = client.post(
            "/api/commerce/v1/auth/login", json={"username": "customer.a", "password": PASSWORD}
        )
        assert login.status_code == 200
        actor = login.json()["account"]["id"]
        with engine.connect() as conn:
            entry = history(conn, "commerce_sessions")[-1]
            assert str(entry["actor_id"]) == actor
            assert entry["action"] == "login"
            assert "token_digest" not in entry["after_data"]
        headers = {
            "Authorization": "Bearer " + login.json()["token"],
            "Idempotency-Key": "history-cart",
        }
        sku = client.get("/api/commerce/v1/catalog/products").json()["items"][0]["skus"][0]
        cart = client.get("/api/commerce/v1/customer/cart", headers=headers).json()
        payload = {
            "expected_version": cart["version"],
            "sku_id": sku["id"],
            "quantity": 2,
            "seen_price_version": sku["price_version"],
        }
        first = client.post("/api/commerce/v1/customer/cart/lines", json=payload, headers=headers)
        assert first.status_code == 201, first.text
        with engine.connect() as conn:
            count = conn.scalar(text("SELECT count(*) FROM commerce_record_history"))
            entry = history(conn, "commerce_cart_lines")[-1]
            assert str(entry["actor_id"]) == actor
            assert entry["action"] == "customer.cart.set"
            assert entry["request_id"] == first.headers["X-Request-Id"]
        second = client.post("/api/commerce/v1/customer/cart/lines", json=payload, headers=headers)
        assert second.status_code == 200
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM commerce_record_history")) == count


def test_baselines_all_triggers_preserve_rows_and_roundtrip(database):
    import importlib.util
    from pathlib import Path

    from alembic import command

    frozen = Path(__file__).resolve().parents[2] / "migrations/versions/0006_commerce_history.py"
    spec = importlib.util.spec_from_file_location("frozen_history", frozen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    FIELD_POLICY = module.FIELD_POLICY

    engine, config, _ = database
    command.downgrade(config, "0005_commerce_onboarding")
    with Session(engine) as db:
        seed_commerce(db, PASSWORD)
    with engine.connect() as conn:
        before = {
            table: conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
            .scalars()
            .all()
            for table in FIELD_POLICY
        }
    command.upgrade(config, "0006_commerce_history")
    with engine.connect() as conn:
        after = {
            table: conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
            .scalars()
            .all()
            for table in FIELD_POLICY
        }
        assert before == after
        entries = conn.execute(text("SELECT * FROM commerce_record_history")).mappings().all()
        assert len(entries) == sum(map(len, before.values()))
        assert all(row["operation"] == "BASELINE" for row in entries)
        assert all(row["before_data"] is None and row["actor_id"] is None for row in entries)
        assert all(row["action"] == "MIGRATION_BASELINE" for row in entries)
        assert all(
            set(row["after_data"]) == set(FIELD_POLICY[row["entity_table"]]) for row in entries
        )
        tables = conn.execute(
            text(
                "SELECT c.relname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE t.tgname='commerce_history_record' AND n.nspname=current_schema()"
            )
        )
        assert set(tables.scalars()) == set(FIELD_POLICY)


def test_credentials_changed_field_only_and_transaction_context_isolation(database):
    from app.commerce.history import set_context
    from app.commerce.models import CommerceAccount

    engine, _, _ = database
    with Session(engine) as db:
        seed_commerce(db, PASSWORD)
    with Session(engine) as db, db.begin():
        actor = db.query(CommerceAccount).filter_by(username="customer.a").one()
        set_context(db, actor, reason="Business correction", action="TEST_EDIT")
        identifier = actor.id
        db.execute(
            text(
                "UPDATE commerce_accounts SET password_hash='secret-hash-never-record' WHERE id=:id"
            ),
            {"id": identifier},
        )
        row = history(db, "commerce_accounts", identifier)[-1]
        assert row["changed_fields"] == ["password_hash"]
        assert row["before_data"] == row["after_data"]
        assert "password_hash" not in row["after_data"]
        assert "secret-hash-never-record" not in str(row)
        assert row["actor_id"] == identifier
        assert row["reason"] == "Business correction"
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE commerce_accounts SET active=false WHERE id=:id"), {"id": identifier}
        )
        row = history(conn, "commerce_accounts", identifier)[-1]
        assert row["actor_id"] is None and row["reason"] is None
        assert row["actor_username"] is None and row["request_id"] is None
        assert row["action"] == "DIRECT_SQL"
        assert row["db_role"] == conn.scalar(text("SELECT current_user"))


def test_public_registration_remains_anonymous_and_tokens_absent(database, tmp_path):
    import json

    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    engine, _, _ = database
    app = create_app(
        Settings(app_env="test", commerce_mailbox_dir=tmp_path / "mail"),
        session_factory=lambda: Session(engine),
    )
    with TestClient(app) as client:
        result = client.post(
            "/api/commerce/v1/auth/register",
            headers={"Idempotency-Key": "history-register"},
            json={"username": "history.user", "email": "history@example.com", "password": PASSWORD},
        )
        assert result.status_code == 202, result.text
        code = json.loads(next((tmp_path / "mail").glob("*.json")).read_text())["code"]
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM commerce_record_history")).mappings().all()
            assert rows
            assert all(r["actor_id"] is None and r["actor_username"] is None for r in rows)
            assert all(r["action"] == "onboarding.register" for r in rows)
            assert all(r["request_id"] == result.headers["X-Request-Id"] for r in rows)
            assert PASSWORD not in str(rows) and code not in str(rows)
            assert "token_digest" not in str(rows[0]["after_data"])
        verified = client.post(
            "/api/commerce/v1/auth/verify-email",
            headers={"Idempotency-Key": "history-verify"},
            json={"email": "history@example.com", "code": code},
        )
        assert verified.status_code == 200, verified.text
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM commerce_record_history "
                        "WHERE action='onboarding.verify-email'"
                    )
                )
                .mappings()
                .all()
            )
            assert rows and all(r["actor_id"] is None for r in rows)
            assert code not in str(rows)


def test_profile_address_versions_soft_delete_and_unauthorized_rollback(database, tmp_path):
    from fastapi.testclient import TestClient
    from test_commerce import ADDRESS
    from test_onboarding import login, post, setup

    engine, _, app = setup(database, tmp_path)
    with TestClient(app) as client:
        token = login(client)
        other = login(client, "customer.b")
        profile = post(
            client,
            "account/profile",
            {"expected_version": 0, "display_name": "First", "phone": ""},
            token,
        )
        assert profile.status_code == 200
        profile = post(
            client,
            "account/profile",
            {"expected_version": 1, "display_name": "Second", "phone": "123"},
            token,
        )
        assert profile.status_code == 200
        address = post(
            client, "customer/addresses", {"address": ADDRESS, "is_default": False}, token
        ).json()
        changed = post(
            client,
            "customer/addresses/" + address["id"] + "/edit",
            {
                "expected_version": address["version"],
                "address": ADDRESS | {"city": "New City"},
                "is_default": True,
            },
            token,
        )
        assert changed.status_code == 200, changed.text
        deleted = post(
            client,
            "customer/addresses/" + address["id"] + "/delete",
            {"expected_version": changed.json()["version"]},
            token,
        )
        assert deleted.status_code == 200, deleted.text
        with engine.connect() as conn:
            count = conn.scalar(text("SELECT count(*) FROM commerce_record_history"))
            profiles = [
                r
                for r in history(conn, "commerce_account_profiles")
                if r["after_data"]["display_name"] in {"First", "Second"}
            ]
            assert profiles[-1]["before_data"]["display_name"] == "First"
            assert profiles[-1]["after_data"]["display_name"] == "Second"
            rows = history(conn, "commerce_address_book", address["id"])
            assert rows[1]["before_data"]["address"]["city"] == ADDRESS["city"]
            assert rows[1]["after_data"]["address"]["city"] == "New City"
            assert rows[-1]["before_data"]["active"] is True
            assert rows[-1]["after_data"]["active"] is False
            assert rows[-1]["operation"] == "UPDATE"
        rejected = post(
            client, "customer/addresses/" + address["id"] + "/edit", {"junk": True}, other
        )
        assert rejected.status_code == 404
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM commerce_record_history")) == count


def test_checkout_payment_refund_state_history(database):
    from fastapi.testclient import TestClient
    from test_commerce import Clock, get, pay, post, purchase, signin
    from test_commerce_step4 import make_case

    from app.core.config import Settings
    from app.main import create_app

    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine), clock=clock)
    # Existing purchase helpers use the shared fictional seed password.
    from test_commerce import PASSWORD as commerce_password

    from app.core.security import PASSWORD_HASHER

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE commerce_accounts SET password_hash=:hash"),
            {"hash": PASSWORD_HASHER.hash(commerce_password)},
        )
    with TestClient(app) as client:
        customer, owner, demo = [signin(client, name) for name in ("customer.a", "owner.a", "demo")]
        order = purchase(client, customer)["orders"][0]
        oid, shop = order["id"], order["shop_id"]
        with engine.connect() as conn:
            assert history(conn, "commerce_cart_lines")[-1]["operation"] == "DELETE"
        pay(client, customer, demo, oid)
        case = make_case(client, customer, oid)
        path = "/merchant/shops/" + shop + "/orders/" + oid + "/after-sales/" + case["id"]
        approved = post(
            client,
            path + "/decision",
            owner,
            {
                "expected_version": case["version"],
                "decision": "APPROVE",
                "reason": "Inspected refund request",
            },
        ).json()
        attempt = post(
            client,
            path + "/refunds",
            owner,
            {"expected_version": approved["version"]},
            expected=201,
        ).json()
        post(
            client,
            "/demo/refunds/" + attempt["id"] + "/result",
            demo,
            {"expected_version": 1, "result": "SUCCEEDED", "event_id": "history-refund"},
        )
        assert (
            get(client, "/customer/orders/" + oid, customer)["financial_status"]
            == "PARTIALLY_REFUNDED"
        )
        with engine.connect() as conn:
            rows = history(conn, "commerce_payment_attempts")
            assert rows[-1]["before_data"]["state"] == "PENDING"
            assert rows[-1]["after_data"]["state"] == "SUCCEEDED"
            rows = history(conn, "commerce_refund_attempts", attempt["id"])
            assert rows[-1]["before_data"]["state"] == "PENDING"
            assert rows[-1]["after_data"]["state"] == "SUCCEEDED"
            cases = history(conn, "commerce_after_sale_cases", case["id"])
            decision = next(r for r in cases if r["action"] == "merchant.case.decision")
            assert decision["reason"] == "Inspected refund request"
            assert decision["actor_username"] == "owner.a"
            orders = history(conn, "commerce_orders", oid)
            assert orders[-1]["after_data"]["financial_status"] == "PARTIALLY_REFUNDED"


def test_price_changes_actual_observation_time_and_rolled_back_insert(database):
    engine, _, _ = database
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, datetime(2020, 1, 1, tzinfo=UTC))
    with engine.begin() as conn:
        sku = conn.scalar(text("SELECT id FROM commerce_skus LIMIT 1"))
        conn.execute(
            text("UPDATE commerce_skus SET unit_price_minor=1900 WHERE id=:id"), {"id": sku}
        )
        conn.execute(
            text("UPDATE commerce_skus SET unit_price_minor=2200 WHERE id=:id"), {"id": sku}
        )
        rows = history(conn, "commerce_skus", sku)
        assert rows[-2]["after_data"]["unit_price_minor"] == 1900
        assert rows[-1]["before_data"]["unit_price_minor"] == 1900
        assert rows[-1]["after_data"]["unit_price_minor"] == 2200
        assert rows[-1]["recorded_at"].year != 2020
        assert rows[-1]["after_data"]["created_at"].startswith("2020-01-01")
        assert rows[-2]["id"] < rows[-1]["id"]
    with engine.connect() as conn:
        tx = conn.begin()
        identifier = conn.scalar(
            text(
                "INSERT INTO commerce_shops(id,version,created_at,updated_at,name,status) "
                "VALUES(gen_random_uuid(),1,now(),now(),'Rollback','ACTIVE') RETURNING id"
            )
        )
        assert len(history(conn, "commerce_shops", identifier)) == 1
        tx.rollback()
        assert history(conn, "commerce_shops", identifier) == []


def test_reviewer_approval_and_created_shop_attribution(database, tmp_path):
    from fastapi.testclient import TestClient
    from test_onboarding import bind, login, post, setup

    engine, _, app = setup(database, tmp_path)
    with TestClient(app) as client:
        customer, reviewer = login(client), login(client, "reviewer")
        bind(client, customer, tmp_path)
        created = post(
            client,
            "customer/merchant-applications",
            {
                "shop_name": "History Shop",
                "business_scope": "Physical goods",
                "contact_name": "Customer",
                "contact_phone": "123",
                "description": "Fictional application",
            },
            customer,
        )
        assert created.status_code == 201, created.text
        application = created.json()
        decision = post(
            client,
            "review/merchant-applications/" + application["id"] + "/decision",
            {
                "expected_version": 1,
                "decision": "APPROVE",
                "reason": "Verified fictional application",
            },
            reviewer,
        )
        assert decision.status_code == 200, decision.text
        with engine.connect() as conn:
            row = history(conn, "commerce_merchant_applications", application["id"])[-1]
            assert row["before_data"]["state"] == "PENDING"
            assert row["after_data"]["state"] == "APPROVED"
            assert row["actor_username"] == "reviewer"
            assert row["reason"] == "Verified fictional application"
            shop = history(conn, "commerce_shops", decision.json()["shop_id"])[-1]
            assert shop["actor_username"] == "reviewer"
            assert shop["action"] == "onboarding.application.decision"
