"""Scenario completeness regressions in isolated real PostgreSQL schemas."""

from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_commerce import commerce as commerce
from test_commerce import get, pay, post, purchase, signin
from test_commerce_step4 import case_base, make_case

from app.commerce.models import CommerceAccount, Inventory, Shop
from app.commerce.seed import seed_id

pytestmark = pytest.mark.database


def test_account_deactivation_blocks_original_message_replay_and_reads(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    conversation = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": str(seed_id("shop/shopA")), "order_id": None},
        expected=201,
    ).json()
    path = "/customer/conversations/" + conversation["id"] + "/messages"
    body = {"body": "original authorized message"}
    original = post(client, path, customer, body, key="before-deactivation", expected=201)
    assert original.json()["body"] == body["body"]
    with Session(engine) as db, db.begin():
        db.execute(
            update(CommerceAccount)
            .where(CommerceAccount.id == seed_id("account/customer.a"))
            .values(active=False)
        )
    replay = client.post(
        "/api/commerce/v1" + path,
        headers=customer | {"Idempotency-Key": "before-deactivation"},
        json=body,
    )
    assert replay.status_code == 401
    assert client.get("/api/commerce/v1" + path, headers=customer).status_code == 401


def test_suspended_shop_existing_messages_and_refund_completion(commerce):
    client, engine, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    conversation = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    with Session(engine) as db, db.begin():
        db.execute(update(Shop).where(Shop.id == UUID(order["shop_id"])).values(status="SUSPENDED"))
    customer_path = "/customer/conversations/" + conversation["id"] + "/messages"
    merchant_path = (
        "/merchant/shops/" + order["shop_id"] + "/conversations/" + conversation["id"] + "/messages"
    )
    post(client, customer_path, customer, {"body": "existing order question"}, expected=201)
    post(client, merchant_path, owner, {"body": "existing order response"}, expected=201)
    assert len(get(client, customer_path, customer)["items"]) == 2
    case = make_case(client, customer, order["id"], quantity=2)
    base = case_base(order, case, True)
    case = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": case["version"], "decision": "APPROVE", "reason": "yes"},
    ).json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": case["version"]}, expected=201
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {"expected_version": 1, "result": "SUCCEEDED", "event_id": "suspended-refund"},
    )
    final = get(client, "/customer/orders/" + order["id"], customer)
    assert (final["status"], final["financial_status"]) == ("CANCELLED", "REFUNDED")
    with Session(engine) as db:
        assert db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand == 5


def test_finished_case_replays_original_decision_and_rejects_changed_body(commerce):
    client, _, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    base = case_base(order, case, True)
    body = {"expected_version": case["version"], "decision": "APPROVE", "reason": "original"}
    original = post(client, base + "/decision", owner, body, key="original-decision").json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": original["version"]}, expected=201
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {"expected_version": 1, "result": "SUCCEEDED", "event_id": "finished-refund"},
    )
    final = get(client, case_base(order, case), customer)
    assert final["state"] == "COMPLETED"
    replay = post(client, base + "/decision", owner, body, key="original-decision")
    assert replay.json() == original
    assert replay.headers["Idempotent-Replay"] == "true"
    for changed in (body | {"reason": "changed"}, body | {"expected_version": final["version"]}):
        post(client, base + "/decision", owner, changed, key="original-decision", expected=409)
    assert get(client, case_base(order, case), customer) == final


def test_mixed_shipped_unshipped_quantity_case_is_atomic(commerce):
    from app.commerce.models import AfterSaleCase, AfterSaleLine, RefundAttempt

    client, engine, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    current = get(client, "/customer/orders/" + order["id"], customer)
    post(
        client,
        "/merchant/shops/" + order["shop_id"] + "/orders/" + order["id"] + "/shipments",
        owner,
        {
            "expected_version": current["version"],
            "lines": [{"order_line_id": current["lines"][0]["id"], "quantity": 1}],
        },
        expected=201,
    )
    before = get(client, "/customer/orders/" + order["id"], customer)
    response = post(
        client,
        "/customer/orders/" + order["id"] + "/after-sales",
        customer,
        {
            "expected_version": before["version"],
            "type": "UNSHIPPED_REFUND",
            "reason": "request both shipped and unshipped units",
            "lines": [{"order_line_id": before["lines"][0]["id"], "quantity": 2}],
        },
        key="mixed-quantity",
        expected=409,
    )
    assert response.json()["error"]["code"] == "QUANTITY_CONFLICT"
    assert get(client, "/customer/orders/" + order["id"], customer) == before
    with Session(engine) as db:
        for model in (AfterSaleCase, AfterSaleLine, RefundAttempt):
            assert list(db.scalars(select(model))) == []
        inventory = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inventory.on_hand, inventory.reserved) == (3, 0)
    # Rejection did not freeze the remaining eligible unit.
    assert make_case(client, customer, order["id"], quantity=1)["state"] == "REQUESTED"


def test_distinct_refund_successes_forced_overlap_separate_connections(commerce, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic

    from sqlalchemy import text

    from app.commerce import after_sales
    from app.commerce.models import SimulationEvent, StockMovement
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
    first_inside, second_entering = Event(), Event()
    backend_pids = []
    original_acquire, original_result = Commerce.acquire_write, after_sales.refund_result

    def acquire(self):
        backend_pids.append(self.db.scalar(text("SELECT pg_backend_pid()")))
        if first_inside.is_set():
            second_entering.set()
        return original_acquire(self)

    def result(svc, row, body):
        if not first_inside.is_set():
            first_inside.set()
            assert second_entering.wait(5), "Second connection never entered the write lock"
            deadline = monotonic() + 1.5
            with engine.connect() as observer:
                while monotonic() < deadline:
                    waiting = observer.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks "
                            "WHERE pid=:pid AND locktype='advisory' AND NOT granted)"
                        ),
                        {"pid": backend_pids[1]},
                    )
                    if waiting:
                        break
                else:
                    pytest.fail("Second connection was not observed waiting on the business lock")
        return original_result(svc, row, body)

    monkeypatch.setattr(Commerce, "acquire_write", acquire)
    monkeypatch.setattr(after_sales, "refund_result", result)

    def callback(index):
        return client.post(
            "/api/commerce/v1/demo/refunds/" + attempt["id"] + "/result",
            headers=demo | {"Idempotency-Key": f"overlap-refund-{index}"},
            json={
                "expected_version": 1,
                "result": "SUCCEEDED",
                "event_id": f"overlap-refund-event-{index}",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(callback, 0)
        assert first_inside.wait(5)
        second = pool.submit(callback, 1)
        responses = [first.result(timeout=10), second.result(timeout=10)]
    assert len(backend_pids) == 2 and len(set(backend_pids)) == 2
    assert sorted(r.status_code for r in responses) == [200, 409]
    final = get(client, "/customer/orders/" + order["id"], customer)
    assert final["financial_status"] == "PARTIALLY_REFUNDED"
    assert final["lines"][0]["refunded_unshipped_qty"] == 1
    assert get(client, case_base(order, case), customer)["state"] == "COMPLETED"
    with Session(engine) as db:
        assert db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand == 4
        assert (
            len(
                list(
                    db.scalars(
                        select(StockMovement).where(
                            StockMovement.reason == "UNSHIPPED_REFUND_RESTOCK"
                        )
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(SimulationEvent).where(
                            SimulationEvent.event_id.in_(
                                ["overlap-refund-event-0", "overlap-refund-event-1"]
                            )
                        )
                    )
                )
            )
            == 1
        )
