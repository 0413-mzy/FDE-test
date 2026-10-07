"""Private inspection acceptance against isolated PostgreSQL."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_commerce import PASSWORD, signin
from test_commerce import commerce as commerce

from app.commerce.platform_seed import seed_platform

pytestmark = pytest.mark.database
BASE = "/api/commerce/v1/platform/data"


@pytest.fixture
def center(commerce):
    client, engine, _ = commerce
    with Session(engine) as db:
        seed_platform(db, PASSWORD)
    return client, engine, signin(client, "platform")


def test_private_authority_directory_safe_fields(center):
    client, _, headers = center
    assert client.get(BASE + "/resources").status_code == 401
    for name in ("customer.a", "owner.a", "staff.a", "demo"):
        assert client.get(BASE + "/resources", headers=signin(client, name)).status_code == 403
    resources = client.get(BASE + "/resources", headers=headers)
    assert resources.status_code == 200, resources.text
    names = {r["resource"] for r in resources.json()["items"]}
    assert "commerce_ai_attempts" in names
    assert not names & {"commerce_sessions", "commerce_email_challenges", "commerce_operations"}
    rows = client.get(BASE + "/resources/commerce_accounts", headers=headers).json()
    assert rows["items"] and all("password_hash" not in r for r in rows["items"])
    assert (
        client.post(BASE + "/resources/commerce_accounts", headers=headers, json={}).status_code
        == 405
    )


def test_current_projected_history_deleted_and_injection(center):
    client, engine, headers = center
    path = BASE + "/resources/commerce_products"
    data = client.get(path, headers=headers)
    assert data.status_code == 200, data.text
    pid = data.json()["items"][0]["id"]
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE commerce_products SET title=:title WHERE id=:id"),
            {"title": "Changed through SQL", "id": pid},
        )
    detail = client.get(path + "/" + pid, headers=headers).json()
    assert detail["record"]["title"] == "Changed through SQL"
    assert detail["history"]["items"][0]["after_data"]["title"] == "Changed through SQL"
    assert detail["related"]
    assert (
        client.get(path, params={"q": "';DROP TABLE commerce_products;--"}, headers=headers).json()[
            "total"
        ]
        == 0
    )
    assert client.get(BASE + "/resources/commerce_sessions", headers=headers).status_code == 404
    assert client.get(path, params={"limit": 101}, headers=headers).status_code == 400
    assert client.get(path, params={"id": "not-uuid"}, headers=headers).status_code == 400
    with engine.begin() as conn:
        aid = conn.scalar(text("SELECT id FROM commerce_accounts LIMIT 1"))
        conn.execute(
            text("UPDATE commerce_accounts SET password_hash='secret-hash' WHERE id=:id"),
            {"id": aid},
        )
        cart = conn.scalar(text("SELECT id FROM commerce_carts LIMIT 1"))
        sku = conn.scalar(text("SELECT id FROM commerce_skus LIMIT 1"))
        deleted = conn.scalar(
            text(
                "INSERT INTO commerce_cart_lines "
                "(id,version,created_at,updated_at,cart_id,sku_id,quantity,"
                "seen_price_version,seen_price_minor) VALUES "
                "(gen_random_uuid(),1,now(),now(),:cart,:sku,1,1,100) RETURNING id"
            ),
            {"cart": cart, "sku": sku},
        )
        conn.execute(text("DELETE FROM commerce_cart_lines WHERE id=:id"), {"id": deleted})
    hist = client.get(BASE + "/history", headers=headers)
    assert hist.status_code == 200
    assert "password_hash" not in hist.text and "secret-hash" not in hist.text
    deleted_data = client.get(
        BASE + "/resources/commerce_cart_lines/" + str(deleted), headers=headers
    ).json()
    assert deleted_data["deleted"] is True and deleted_data["record"] is None
    assert deleted_data["history"]["items"][0]["operation"] == "DELETE"


def test_exact_foreign_key_filters_and_readonly_transaction(center, monkeypatch):
    from sqlalchemy import event

    from app.commerce import data_center

    client, engine, headers = center
    pid = client.get(BASE + "/resources/commerce_products", headers=headers).json()["items"][0][
        "id"
    ]
    target = client.get(BASE + "/resources/commerce_products/" + pid, headers=headers).json()
    child = next(r for r in target["related"] if r["resource"] == "commerce_skus")
    assert child["filter"] == {"field": "product_id", "value": pid}
    rows = client.get(
        BASE + "/resources/commerce_skus", params=child["filter"], headers=headers
    ).json()
    assert rows["items"] and all(row["product_id"] == pid for row in rows["items"])
    assert (
        client.get(
            BASE + "/resources/commerce_skus",
            params={"field": "sku_code", "value": pid},
            headers=headers,
        ).status_code
        == 400
    )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        client.get(BASE + "/resources", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert any("SET TRANSACTION READ ONLY" in sql for sql in statements)
    assert any("statement_timeout" in sql for sql in statements)

    def forbidden(db):
        db.execute(text("UPDATE commerce_products SET title='should rollback'"))

    monkeypatch.setattr(data_center, "directory", forbidden)
    failure = client.get(BASE + "/resources", headers=headers)
    assert failure.status_code == 503 and "UPDATE" not in failure.text


def test_pagination_filters_baseline_ai_and_mixed_identity(center):
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.commerce.ai_models import AIAttempt
    from app.commerce.data_center import FIELDS

    client, engine, headers = center
    listing = BASE + "/resources/commerce_products"
    first = client.get(listing, params={"limit": 1}, headers=headers).json()
    second = client.get(listing, params={"limit": 1, "offset": 1}, headers=headers).json()
    assert first["total"] >= 2 and first["items"][0]["id"] != second["items"][0]["id"]
    assert (
        client.get(listing, params={"from": "2999-01-01T00:00:00Z"}, headers=headers).json()[
            "items"
        ]
        == []
    )
    assert client.get(listing, params={"from": "2026-10-07"}, headers=headers).status_code == 400
    assert (
        client.get(listing, params={"status": "NOT_A_STATE"}, headers=headers).json()["items"] == []
    )
    pid = first["items"][0]["id"]
    with engine.begin() as conn:
        current = conn.scalar(
            text("SELECT to_jsonb(p) FROM commerce_products p WHERE id=:id"), {"id": pid}
        )
        safe = {field: current[field] for field in FIELDS["commerce_products"]}
        import json

        conn.execute(
            text(
                "INSERT INTO commerce_record_history "
                "(entity_table,entity_id,operation,before_data,after_data,changed_fields,"
                "db_role,action) VALUES ('commerce_products',:id,'BASELINE',NULL,"
                "CAST(:safe AS jsonb),'{}',current_user,'MIGRATION_BASELINE')"
            ),
            {"id": pid, "safe": json.dumps(safe)},
        )
        conversation = conn.scalar(text("SELECT id FROM commerce_conversations LIMIT 1"))
        # Seed normally has no conversation; create a fictional one in this isolated schema.
        actor = conn.scalar(text("SELECT id FROM commerce_accounts WHERE username='platform'"))
        if conversation is None:
            customer = conn.scalar(
                text("SELECT id FROM commerce_accounts WHERE username='customer.a'")
            )
            shop = conn.scalar(text("SELECT id FROM commerce_shops LIMIT 1"))
            conversation = conn.scalar(
                text(
                    "INSERT INTO commerce_conversations "
                    "(id,version,created_at,updated_at,customer_id,shop_id) VALUES "
                    "(gen_random_uuid(),1,now(),now(),:customer,:shop) RETURNING id"
                ),
                {"customer": customer, "shop": shop},
            )
    baseline = client.get(
        BASE + "/history",
        params={"resource": "commerce_products", "id": pid, "operation": "BASELINE"},
        headers=headers,
    ).json()["items"][0]
    assert baseline["before_data"] is None and baseline["after_data"] == safe
    now = datetime.now(UTC)
    aid = uuid4()
    with Session(engine) as db, db.begin():
        db.add(
            AIAttempt(
                id=aid,
                cached_from=None,
                conversation_id=conversation,
                actor_id=actor,
                idempotency_key="private-technical-key",
                snapshot_hash="0" * 64,
                source_ids=[],
                message_count=0,
                model="test-model",
                prompt_version="test",
                state="FAILED",
                lease_until=now,
                created_at=now,
                finished_at=now,
                result=None,
                error_code="AI_INTERRUPTED",
                usage=[],
            )
        )
    ai = client.get(BASE + "/resources/commerce_ai_attempts/" + str(aid), headers=headers)
    assert ai.status_code == 200 and ai.json()["history_mode"] == "attempt_lifecycle"
    assert ai.json()["history"]["total"] == 0 and "idempotency_key" not in ai.text
    assert "private-technical-key" not in ai.text and "snapshot_hash" not in ai.text
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE commerce_accounts SET customer_enabled=true WHERE id=:id"), {"id": actor}
        )
    assert client.get(BASE + "/resources", headers=headers).status_code == 403


def test_composite_foreign_keys_link_target_primary_ids_only(center):
    client, _, headers = center
    sku = client.get(BASE + "/resources/commerce_skus", headers=headers).json()["items"][0]
    product = client.get(
        BASE + "/resources/commerce_products/" + sku["product_id"], headers=headers
    ).json()
    product_children = [r for r in product["related"] if r["resource"] == "commerce_skus"]
    assert product_children == [
        {
            "resource": "commerce_skus",
            "filter": {"field": "product_id", "value": sku["product_id"]},
            "field": "product_id",
            "direction": "children",
        }
    ]
    detail = client.get(BASE + "/resources/commerce_skus/" + sku["id"], headers=headers).json()
    parents = [r for r in detail["related"] if r["direction"] == "parent"]
    assert {
        "resource": "commerce_products",
        "id": sku["product_id"],
        "field": "product_id",
        "direction": "parent",
    } in parents
    assert not any(
        r["resource"] == "commerce_products" and r["field"] == "shop_id" for r in parents
    )
    assert len({str(r) for r in detail["related"]}) == len(detail["related"])
    assert (
        detail["related"]
        == client.get(BASE + "/resources/commerce_skus/" + sku["id"], headers=headers).json()[
            "related"
        ]
    )
    for parent in parents:
        target = client.get(
            BASE + "/resources/" + parent["resource"] + "/" + parent["id"], headers=headers
        )
        assert target.status_code == 200


def test_registered_relations_use_only_approved_primary_key_components(center):
    from app.commerce.data_center import FIELDS, resource

    client, _, headers = center
    for name in FIELDS:
        rows = client.get(BASE + "/resources/" + name, params={"limit": 1}, headers=headers).json()[
            "items"
        ]
        if not rows:
            continue
        record = rows[0]
        detail = client.get(
            BASE + "/resources/" + name + "/" + record["id"], headers=headers
        ).json()
        for relation in detail["related"]:
            if relation["direction"] == "parent":
                components = [
                    fk
                    for constraint in resource(name).foreign_key_constraints
                    for fk in constraint.elements
                    if fk.parent.name == relation["field"]
                    and fk.column.table.name == relation["resource"]
                    and fk.column.name == "id"
                ]
                assert components
                assert relation["id"] == record[relation["field"]]
                assert (
                    client.get(
                        BASE + "/resources/" + relation["resource"] + "/" + relation["id"],
                        headers=headers,
                    ).status_code
                    == 200
                )
            else:
                components = [
                    fk
                    for constraint in resource(relation["resource"]).foreign_key_constraints
                    for fk in constraint.elements
                    if fk.parent.name == relation["field"]
                    and fk.column.table.name == name
                    and fk.column.name == "id"
                ]
                assert components
                assert relation["filter"] == {"field": relation["field"], "value": record["id"]}
