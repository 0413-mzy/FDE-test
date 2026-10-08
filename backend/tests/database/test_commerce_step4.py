"""Step 4 acceptance against isolated PostgreSQL schemas."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_commerce import ADDRESS, carrier_stages, get, pay, post, purchase, signin
from test_commerce import commerce as commerce

from app.commerce.models import (
    AfterSaleCase,
    IdempotencyRecord,
    Inventory,
    Shop,
    ShopMembership,
    StockMovement,
)
from app.commerce.seed import seed_id

pytestmark = pytest.mark.database


def test_messages_and_partial_refund(commerce):
    client, _, _ = commerce
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    order = purchase(client, customer)["orders"][0]
    oid, shop = order["id"], order["shop_id"]
    conv = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": shop, "order_id": oid},
        expected=201,
    ).json()
    message = post(
        client,
        "/customer/conversations/" + conv["id"] + "/messages",
        customer,
        {"body": "hello"},
        key="message",
        expected=201,
    )
    replay = post(
        client,
        "/customer/conversations/" + conv["id"] + "/messages",
        customer,
        {"body": "hello"},
        key="message",
    )
    assert replay.json() == message.json()
    pay(client, customer, demo, oid)
    order = get(client, "/customer/orders/" + oid, customer)
    case = post(
        client,
        "/customer/orders/" + oid + "/after-sales",
        customer,
        {
            "expected_version": order["version"],
            "type": "UNSHIPPED_REFUND",
            "reason": "one item",
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        },
        expected=201,
    ).json()
    base = "/merchant/shops/" + shop + "/orders/" + oid + "/after-sales/" + case["id"]
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": case["version"], "decision": "APPROVE", "reason": "approved"},
    ).json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=201
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {"expected_version": 1, "result": "SUCCEEDED", "event_id": "refund"},
    )
    final = get(client, "/customer/orders/" + oid, customer)
    assert final["financial_status"] == "PARTIALLY_REFUNDED"
    assert final["lines"][0]["refunded_unshipped_qty"] == 1


def make_case(client, customer, oid, kind="UNSHIPPED_REFUND", quantity=1):
    order = get(client, "/customer/orders/" + oid, customer)
    return post(
        client,
        "/customer/orders/" + oid + "/after-sales",
        customer,
        {
            "expected_version": order["version"],
            "type": kind,
            "reason": "test reason",
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": quantity}],
        },
        expected=201,
    ).json()


def case_base(order, case, merchant=False):
    return (
        ("/merchant/shops/" + order["shop_id"] if merchant else "/customer")
        + "/orders/"
        + order["id"]
        + "/after-sales/"
        + case["id"]
    )


def test_return_boundary_failure_retry_stock_and_events(commerce, monkeypatch):
    client, engine, clock = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    oid = order["id"]
    pay(client, customer, demo, oid)
    current = get(client, "/customer/orders/" + oid, customer)
    shipment = post(
        client,
        "/merchant/shops/" + order["shop_id"] + "/orders/" + oid + "/shipments",
        owner,
        {
            "expected_version": current["version"],
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 2}],
        },
        expected=201,
    ).json()
    shipment = carrier_stages(client, demo, shipment, clock)
    post(
        client,
        "/demo/shipments/" + shipment["id"] + "/events",
        demo,
        {
            "expected_version": shipment["version"],
            "event_id": "delivered",
            "kind": "DELIVERED",
            "description": "simulated",
            "occurred_at": clock.now().isoformat(),
        },
    )
    clock.value += timedelta(days=14)
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    case = make_case(client, customer, oid, "RETURN_REFUND")
    base = case_base(order, case, True)
    clock.value += timedelta(seconds=1)
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": 1, "decision": "APPROVE", "reason": "approve after window"},
    ).json()
    case = post(
        client,
        case_base(order, case) + "/return",
        customer,
        {"expected_version": case["version"], "tracking_number": "SIM-RETURN"},
    ).json()
    with Session(engine) as db:
        before = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
    receive_body = {"expected_version": case["version"], "restock": True}
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.commerce import after_sales
    from app.commerce.service import Commerce

    entered, prefetched = Event(), Event()
    original_action, original_get = after_sales.case_action, Commerce.get

    def observe_get(self, cls, identifier, lock=False):
        row = original_get(self, cls, identifier, lock)
        if cls is AfterSaleCase and not lock and entered.is_set():
            prefetched.set()
        return row

    def pause_action(svc, order_row, case_row, action, body):
        if action == "receive-return" and not entered.is_set():
            entered.set()
            assert prefetched.wait(5)
        return original_action(svc, order_row, case_row, action, body)

    monkeypatch.setattr(Commerce, "get", observe_get)
    monkeypatch.setattr(after_sales, "case_action", pause_action)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            post, client, base + "/receive-return", owner, receive_body, "receive"
        )
        assert entered.wait(5)
        second = executor.submit(
            post, client, base + "/receive-return", owner, receive_body, "receive-race", 409
        )
        received = first.result().json()
        assert second.result().json()["error"]["code"] == "VERSION_CONFLICT"
    monkeypatch.setattr(Commerce, "get", original_get)
    monkeypatch.setattr(after_sales, "case_action", original_action)
    replay = post(client, base + "/receive-return", owner, receive_body, key="receive").json()
    assert received == replay
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
            == before + 1
        )
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": received["version"]}, expected=201
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {"expected_version": 1, "result": "FAILED", "event_id": "refund-failed"},
    )
    case = get(client, case_base(order, case), customer)
    assert (
        case["state"] == "REFUND_PENDING"
        and case["refund_attempts"][0]["failure_code"] == "SIMULATED_REFUND_FAILURE"
    )
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=201
    ).json()
    event = {"expected_version": 1, "result": "SUCCEEDED", "event_id": "refund-success"}
    result = post(client, "/demo/refunds/" + attempt["id"] + "/result", demo, event).json()
    assert post(client, "/demo/refunds/" + attempt["id"] + "/result", demo, event).json() == result
    for version in (True, "1", 0):
        malformed = event | {"expected_version": version}
        post(client, "/demo/refunds/" + attempt["id"] + "/result", demo, malformed, expected=400)
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
            == before + 1
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(StockMovement).where(StockMovement.reason == "RETURN_RESTOCK")
                    )
                )
            )
            == 1
        )
    current = get(client, "/customer/orders/" + oid, customer)
    post(
        client,
        "/customer/orders/" + oid + "/after-sales",
        customer,
        {
            "expected_version": current["version"],
            "type": "RETURN_REFUND",
            "reason": "late",
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
        },
        expected=409,
    )


def test_ownership_staff_suspended_and_auth_before_body(commerce):
    client, engine, _ = commerce
    customer, other, owner, staff, demo = [
        signin(client, u) for u in ["customer.a", "customer.b", "owner.a", "staff.a", "demo"]
    ]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    conv = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    path = "/api/commerce/v1/customer/conversations/" + conv["id"] + "/messages"
    assert client.post(path, headers=other, content=b"{bad").status_code == 404
    case = make_case(client, customer, order["id"])
    base = case_base(order, case, True)
    assert (
        client.post(
            "/api/commerce/v1" + base + "/decision", headers=staff, content=b"{bad"
        ).status_code
        == 403
    )
    merchant_messages = (
        "/merchant/shops/" + order["shop_id"] + "/conversations/" + conv["id"] + "/messages"
    )
    post(client, merchant_messages, staff, {"body": "<script>text only</script>"}, expected=201)
    with Session(engine) as db, db.begin():
        db.execute(update(Shop).where(Shop.id == UUID(order["shop_id"])).values(status="SUSPENDED"))
    assert (
        post(
            client,
            "/customer/conversations",
            customer,
            {"shop_id": order["shop_id"], "order_id": order["id"]},
        ).json()["id"]
        == conv["id"]
    )
    post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": None},
        expected=409,
    )
    decision = {"expected_version": 1, "decision": "REJECT", "reason": "denied"}
    post(client, base + "/decision", owner, decision, key="decision")
    with Session(engine) as db, db.begin():
        db.execute(
            update(ShopMembership)
            .where(ShopMembership.account_id == seed_id("account/owner.a"))
            .values(active=False)
        )
    assert client.post(
        "/api/commerce/v1" + base + "/decision",
        headers=owner | {"Idempotency-Key": "decision"},
        json=decision,
    ).status_code in {403, 404}


def test_active_case_invalid_quantity_strict_body_and_exact_historical_replay(commerce):
    client, engine, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    current = get(client, "/customer/orders/" + order["id"], customer)
    post(
        client,
        "/merchant/shops/" + order["shop_id"] + "/orders/" + order["id"] + "/shipments",
        owner,
        {
            "expected_version": current["version"],
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
        },
        expected=409,
    )
    post(
        client,
        "/customer/orders/" + order["id"] + "/address",
        customer,
        {"expected_version": current["version"], "address": ADDRESS},
        expected=409,
    )
    case = post(
        client, case_base(order, case) + "/withdraw", customer, {"expected_version": 1}
    ).json()
    current = get(client, "/customer/orders/" + order["id"], customer)
    payload = {
        "expected_version": current["version"],
        "type": "UNSHIPPED_REFUND",
        "reason": "bad",
        "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 3}],
    }
    post(
        client, "/customer/orders/" + order["id"] + "/after-sales", customer, payload, expected=409
    )
    payload["lines"][0]["quantity"] = True
    post(
        client, "/customer/orders/" + order["id"] + "/after-sales", customer, payload, expected=400
    )
    with Session(engine) as db, db.begin():
        record = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation.like("customer.checkout.create:%")
            )
        )
        stored = dict(record.response_payload)
        stored["orders"] = [
            {k: v for k, v in o.items() if k != "shop_name"} for o in stored["orders"]
        ]
        from datetime import UTC, datetime

        from app.commerce.models import IdempotencyRecord as Replay

        historical = Replay(
            id=uuid4(),
            actor_id=record.actor_id,
            operation=record.operation,
            key="historic",
            request_hash=record.request_hash,
            resource_ids=record.resource_ids,
            response_status=record.response_status,
            response_payload=stored,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(historical)
        key = "historic"
        # Original checkout body from immutable checkout's original source version.
        from app.commerce.models import Checkout

        checkout = db.get(Checkout, UUID(stored["id"]))
        body = {"expected_version": checkout.source_cart_version, "address": ADDRESS}
    replay = post(client, "/customer/checkouts", customer, body, key=key)
    assert replay.json() == stored and "shop_name" not in replay.json()["orders"][0]


def test_concurrent_case_requests_and_atomic_audit_failure(commerce, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from app.commerce.service import Commerce

    client, engine, _ = commerce
    customer, demo = [signin(client, u) for u in ["customer.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    current = get(client, "/customer/orders/" + order["id"], customer)
    path = "/api/commerce/v1/customer/orders/" + order["id"] + "/after-sales"
    payload = {
        "expected_version": current["version"],
        "type": "UNSHIPPED_REFUND",
        "reason": "concurrent",
        "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
    }

    def request(key):
        return client.post(path, headers=customer | {"Idempotency-Key": key}, json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(request, ["same-case", "same-case"]))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    case = results[0].json()
    post(client, case_base(order, case) + "/withdraw", customer, {"expected_version": 1})
    current = get(client, "/customer/orders/" + order["id"], customer)
    payload["expected_version"] = current["version"]
    original = Commerce.audit

    def broken(self, *args, **kwargs):
        raise RuntimeError("injected safe audit failure")

    monkeypatch.setattr(Commerce, "audit", broken)
    assert request("rollback-case").status_code == 500
    monkeypatch.setattr(Commerce, "audit", original)
    with Session(engine) as db:
        assert len(list(db.scalars(select(AfterSaleCase)))) == 1
        assert (
            db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == "rollback-case"))
            is None
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(request, ["different-a", "different-b"]))
    assert sorted(r.status_code for r in results) == [201, 409]


def test_additive_migration_preserves_orders_and_closed_new_records(database):
    from uuid import uuid4

    from alembic import command
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from test_commerce import PASSWORD, Clock

    from app.commerce.seed import seed_commerce

    engine, config, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine), clock=clock)
    with TestClient(app) as client:
        customer = signin(client, "customer.a")
        purchase(client, customer)
    with engine.connect() as connection:
        order_facts = connection.execute(
            text("SELECT id, total_minor, status, version FROM commerce_orders ORDER BY id")
        ).all()
    command.downgrade(config, "0003_commerce")
    with engine.connect() as connection:
        original = connection.execute(text("SELECT id, name FROM commerce_shops ORDER BY id")).all()
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT id, name FROM commerce_shops ORDER BY id")).all()
            == original
        )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id, total_minor, status, version FROM commerce_orders ORDER BY id")
            ).all()
            == order_facts
        )
    # Database itself guards pure-text message history and conversation binding.
    from app.commerce.models import Conversation, Message

    cid = uuid4()
    with Session(engine) as db, db.begin():
        db.add(
            Conversation(
                id=cid,
                customer_id=seed_id("account/customer.a"),
                shop_id=seed_id("shop/shopA"),
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        db.flush()
        db.add(
            Message(
                id=uuid4(),
                conversation_id=cid,
                sender_account_id=seed_id("account/customer.a"),
                sender_side="CUSTOMER",
                body="immutable",
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("UPDATE commerce_messages SET body=:body"), {"body": "changed"})


def test_overlapping_decisions_cannot_reopen_rejected_case(commerce, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.commerce import after_sales
    from app.commerce.service import Commerce

    client, _, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    base = case_base(order, case, True)
    entered, prefetched = Event(), Event()
    original_action, original_get = after_sales.case_action, Commerce.get

    def observe_get(self, cls, identifier, lock=False):
        row = original_get(self, cls, identifier, lock)
        if cls is AfterSaleCase and not lock and entered.is_set():
            prefetched.set()
        return row

    def pause_action(svc, order_row, case_row, action, body):
        if action == "decision" and not entered.is_set():
            entered.set()
            assert prefetched.wait(5)
        return original_action(svc, order_row, case_row, action, body)

    monkeypatch.setattr(Commerce, "get", observe_get)
    monkeypatch.setattr(after_sales, "case_action", pause_action)
    reject = {"expected_version": 1, "decision": "REJECT", "reason": "reject"}
    approve = {"expected_version": 1, "decision": "APPROVE", "reason": "approve"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(post, client, base + "/decision", owner, reject, "reject")
        assert entered.wait(5)
        second = executor.submit(post, client, base + "/decision", owner, approve, "approve", 409)
        assert first.result().json()["state"] == "REJECTED"
        assert second.result().json()["error"]["code"] == "VERSION_CONFLICT"
    assert get(client, case_base(order, case), customer)["state"] == "REJECTED"


def test_case_creation_overlaps_shipping_without_quantity_drift(commerce, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.commerce import after_sales
    from app.commerce.models import Order
    from app.commerce.service import Commerce

    client, _, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    current = get(client, "/customer/orders/" + order["id"], customer)
    entered, prefetched = Event(), Event()
    original_create, original_get = after_sales.create_case, Commerce.get

    def observe_get(self, cls, identifier, lock=False):
        row = original_get(self, cls, identifier, lock)
        if cls is Order and not lock and entered.is_set():
            prefetched.set()
        return row

    def pause_create(svc, row, body):
        entered.set()
        assert prefetched.wait(5)
        return original_create(svc, row, body)

    monkeypatch.setattr(Commerce, "get", observe_get)
    monkeypatch.setattr(after_sales, "create_case", pause_create)
    lines = [{"order_line_id": current["lines"][0]["id"], "quantity": 1}]
    create_body = {
        "expected_version": current["version"],
        "type": "UNSHIPPED_REFUND",
        "reason": "overlap",
        "lines": lines,
    }
    ship_body = {"expected_version": current["version"], "lines": lines}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            post,
            client,
            "/customer/orders/" + order["id"] + "/after-sales",
            customer,
            create_body,
            "case-v-ship",
            201,
        )
        assert entered.wait(5)
        second = executor.submit(
            post,
            client,
            "/merchant/shops/" + order["shop_id"] + "/orders/" + order["id"] + "/shipments",
            owner,
            ship_body,
            "ship-v-case",
            409,
        )
        assert first.result().json()["state"] == "REQUESTED"
        assert second.result().json()["error"]["code"] == "VERSION_CONFLICT"
    final = get(client, "/customer/orders/" + order["id"], customer)
    assert final["lines"][0]["shipped_qty"] == 0
    assert final["lines"][0]["refunded_unshipped_qty"] == 0
    assert final["shipments"] == []
    assert len(final["after_sale_cases"]) == 1


@pytest.mark.parametrize("failure_point", ["inventory", "order", "attempt", "event", "audit"])
def test_refund_success_rolls_back_every_business_record_then_retries(
    commerce, monkeypatch, failure_point
):
    from app.commerce.models import Order, RefundAttempt, SimulationEvent
    from app.commerce.service import Commerce

    client, engine, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    base = case_base(order, case, True)
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": 1, "decision": "APPROVE", "reason": "yes"},
    ).json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=201
    ).json()
    before = get(client, "/customer/orders/" + order["id"], customer)
    with Session(engine) as db:
        stock = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
        movements = len(list(db.scalars(select(StockMovement))))
    original_new, original_bump = Commerce.new, Commerce.bump
    original_movement, original_audit = Commerce.movement, Commerce.audit

    def injected():
        raise RuntimeError("safe test injection")

    def new(self, cls, **values):
        row = original_new(self, cls, **values)
        if failure_point == "event" and cls is SimulationEvent:
            injected()
        return row

    def bump(self, row):
        original_bump(self, row)
        if (
            failure_point == "order"
            and isinstance(row, Order)
            or failure_point == "attempt"
            and isinstance(row, RefundAttempt)
        ):
            injected()

    def movement(self, *args, **kwargs):
        result = original_movement(self, *args, **kwargs)
        if failure_point == "inventory":
            injected()
        return result

    def audit(self, *args, **kwargs):
        result = original_audit(self, *args, **kwargs)
        if failure_point == "audit":
            injected()
        return result

    monkeypatch.setattr(Commerce, "new", new)
    monkeypatch.setattr(Commerce, "bump", bump)
    monkeypatch.setattr(Commerce, "movement", movement)
    monkeypatch.setattr(Commerce, "audit", audit)
    path = "/demo/refunds/" + attempt["id"] + "/result"
    body = {"expected_version": 1, "result": "SUCCEEDED", "event_id": "atomic-refund"}
    post(client, path, demo, body, key="atomic-refund", expected=500)
    monkeypatch.setattr(Commerce, "new", original_new)
    monkeypatch.setattr(Commerce, "bump", original_bump)
    monkeypatch.setattr(Commerce, "movement", original_movement)
    monkeypatch.setattr(Commerce, "audit", original_audit)
    assert get(client, "/customer/orders/" + order["id"], customer) == before
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
            == stock
        )
        assert len(list(db.scalars(select(StockMovement)))) == movements
        assert (
            db.scalar(select(SimulationEvent).where(SimulationEvent.event_id == "atomic-refund"))
            is None
        )
        assert (
            db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == "atomic-refund"))
            is None
        )
    result = post(client, path, demo, body, key="atomic-refund").json()
    assert post(client, path, demo, body, key="atomic-refund").json() == result
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
            == stock + 1
        )
        assert len(list(db.scalars(select(StockMovement)))) == movements + 1


def test_active_case_nested_ownership_and_order_conversation_binding(commerce):
    client, _, _ = commerce
    customer, other, owner, demo = [
        signin(client, u) for u in ["customer.a", "customer.b", "owner.a", "demo"]
    ]
    first = purchase(client, customer)["orders"][0]
    second = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, first["id"])
    case = make_case(client, customer, first["id"])
    current = get(client, "/customer/orders/" + first["id"], customer)
    response = post(
        client,
        "/customer/orders/" + first["id"] + "/after-sales",
        customer,
        {
            "expected_version": current["version"],
            "type": "UNSHIPPED_REFUND",
            "reason": "duplicate active",
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
        },
        expected=409,
    )
    assert response.json()["error"]["code"] == "ACTIVE_CASE_EXISTS"
    wrong_order = "/api/commerce/v1/customer/orders/" + second["id"] + "/after-sales/" + case["id"]
    assert client.get(wrong_order, headers=customer).status_code == 404
    wrong_shop = (
        "/api/commerce/v1/merchant/shops/"
        + str(seed_id("shop/shopB"))
        + "/orders/"
        + first["id"]
        + "/after-sales/"
        + case["id"]
    )
    assert client.get(wrong_shop, headers=owner).status_code == 404
    response = post(
        client,
        "/customer/conversations",
        other,
        {"shop_id": first["shop_id"], "order_id": first["id"]},
        expected=404,
    )
    assert response.json()["error"]["code"] == "NOT_FOUND"


def deliver(client, demo, shipment, clock, event):
    shipment = carrier_stages(client, demo, shipment, clock)
    return post(
        client,
        "/demo/shipments/" + shipment["id"] + "/events",
        demo,
        {
            "expected_version": shipment["version"],
            "event_id": event,
            "kind": "DELIVERED",
            "description": "simulation only",
            "occurred_at": clock.now().isoformat(),
        },
    )


def test_return_all_parcels_window_and_registered_return_restrictions(commerce):
    client, _, clock = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    shipments = []
    for _ in range(2):
        current = get(client, "/customer/orders/" + order["id"], customer)
        shipments.append(
            post(
                client,
                "/merchant/shops/" + order["shop_id"] + "/orders/" + order["id"] + "/shipments",
                owner,
                {
                    "expected_version": current["version"],
                    "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
                },
                expected=201,
            ).json()
        )
    deliver(client, demo, shipments[0], clock, "parcel-one-delivered")

    def request_return():
        current = get(client, "/customer/orders/" + order["id"], customer)
        return client.post(
            "/api/commerce/v1/customer/orders/" + order["id"] + "/after-sales",
            headers=customer | {"Idempotency-Key": str(uuid4())},
            json={
                "expected_version": current["version"],
                "type": "RETURN_REFUND",
                "reason": "return",
                "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
            },
        )

    response = request_return()
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE"
    deliver(client, demo, shipments[1], clock, "parcel-two-delivered")
    delivered_at = clock.now()
    clock.value += timedelta(days=14, seconds=1)
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    response = request_return()
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "RETURN_WINDOW_EXPIRED"
    )
    # Separate eligible request before the deadline; Clock is controlled only by test.
    clock.value = delivered_at + timedelta(days=14)
    case = make_case(client, customer, order["id"], "RETURN_REFUND")
    base = case_base(order, case, True)
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": 1, "decision": "APPROVE", "reason": "yes"},
    ).json()
    response = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=409
    )
    assert response.json()["error"]["code"] == "INVALID_STATE"
    case = post(
        client,
        case_base(order, case) + "/return",
        customer,
        {"expected_version": case["version"], "tracking_number": "SIM-REGISTERED"},
    ).json()
    response = post(
        client,
        case_base(order, case) + "/withdraw",
        customer,
        {"expected_version": case["version"]},
        expected=409,
    )
    assert response.json()["error"]["code"] == "INVALID_STATE"
    response = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=409
    )
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_completed_partial_return_nonrestock_preserves_fulfillment_history(commerce):
    client, engine, clock = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    current = get(client, "/customer/orders/" + order["id"], customer)
    shipment = post(
        client,
        "/merchant/shops/" + order["shop_id"] + "/orders/" + order["id"] + "/shipments",
        owner,
        {
            "expected_version": current["version"],
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 2}],
        },
        expected=201,
    ).json()
    deliver(client, demo, shipment, clock, "complete-delivered")
    current = get(client, "/customer/orders/" + order["id"], customer)
    completed = post(
        client,
        "/customer/orders/" + order["id"] + "/confirm-receipt",
        customer,
        {"expected_version": current["version"]},
    ).json()
    with Session(engine) as db:
        stock = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
        movement_count = len(list(db.scalars(select(StockMovement))))
        inventory_version = db.scalar(
            select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))
        ).version
    case = make_case(client, customer, order["id"], "RETURN_REFUND", 1)
    base = case_base(order, case, True)
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": case["version"], "decision": "APPROVE", "reason": "yes"},
    ).json()
    case = post(
        client,
        case_base(order, case) + "/return",
        customer,
        {"expected_version": case["version"], "tracking_number": "SIM-DAMAGED"},
    ).json()
    case = post(
        client,
        base + "/receive-return",
        owner,
        {"expected_version": case["version"], "restock": False},
    ).json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=201
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {"expected_version": 1, "result": "SUCCEEDED", "event_id": "complete-refund"},
    )
    final = get(client, "/customer/orders/" + order["id"], customer)
    assert final["status"] == "COMPLETED" and final["completed_at"] == completed["completed_at"]
    assert final["lines"][0]["shipped_qty"] == 2 and final["lines"][0]["refunded_shipped_qty"] == 1
    assert final["financial_status"] == "PARTIALLY_REFUNDED"
    assert final["shipments"] == completed["shipments"]
    with Session(engine) as db:
        inventory = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inventory.on_hand, inventory.version) == (stock, inventory_version)
        assert len(list(db.scalars(select(StockMovement)))) == movement_count
    response = post(
        client,
        "/customer/orders/" + order["id"] + "/after-sales",
        customer,
        {
            "expected_version": final["version"],
            "type": "RETURN_REFUND",
            "reason": "repeat refunded quantity",
            "lines": [{"order_line_id": final["lines"][0]["id"], "quantity": 2}],
        },
        expected=409,
    )
    assert response.json()["error"]["code"] == "QUANTITY_CONFLICT"
