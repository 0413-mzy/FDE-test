"""Commerce purchase/fulfillment tests use isolated real PostgreSQL schemas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.commerce.models import (
    BusinessAudit,
    CartLine,
    Checkout,
    CommerceAccount,
    IdempotencyRecord,
    Inventory,
    Order,
    OrderLine,
    Shipment,
    StockMovement,
    StockReservation,
    TrackingEvent,
)
from app.commerce.seed import seed_commerce, seed_id
from app.core.config import Settings
from app.main import create_app

PASSWORD = "test-commerce-secret-123"
ADDRESS = dict(
    recipient_name="Test Customer",
    phone="000000000",
    country_code="CN",
    region="Test",
    city="Test",
    postal_code="000000",
    address_line="Fictional Street",
)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 6, 8, tzinfo=UTC)

    def now(self):
        return self.value


def test_commerce_persistent_purchase(database):
    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine), clock=clock)
    with TestClient(app) as client:
        result = client.post(
            "/api/commerce/v1/auth/login", json={"username": "customer.a", "password": PASSWORD}
        )
        assert result.status_code == 200, result.text
        token = result.json()["token"]
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "cart-a"}
        products = client.get("/api/commerce/v1/catalog/products").json()["items"]
        sku = next(s for p in products for s in p["skus"] if s["sku_code"] == "A")
        cart = client.get("/api/commerce/v1/customer/cart", headers=headers).json()
        added = client.post(
            "/api/commerce/v1/customer/cart/lines",
            headers=headers,
            json={
                "expected_version": cart["version"],
                "sku_id": sku["id"],
                "quantity": 2,
                "seen_price_version": 1,
            },
        )
        assert added.status_code == 201, added.text
        body = {"expected_version": added.json()["version"], "address": ADDRESS}
        headers["Idempotency-Key"] = "checkout-a"
        checkout = client.post("/api/commerce/v1/customer/checkouts", headers=headers, json=body)
        assert checkout.status_code == 201, checkout.text
        assert checkout.json()["orders"][0]["total_minor"] == 2000
        replay = client.post("/api/commerce/v1/customer/checkouts", headers=headers, json=body)
        assert replay.status_code == 200
        assert replay.json() == checkout.json()
        assert replay.headers["Idempotent-Replay"] == "true"


pytestmark = pytest.mark.database


@pytest.fixture
def commerce(database):
    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine), clock=clock)
    with TestClient(app) as client:
        yield client, engine, clock


def signin(client, username):
    r = client.post(
        "/api/commerce/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def get(client, path, headers):
    r = client.get("/api/commerce/v1" + path, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def post(client, path, headers, payload, key=None, expected=200):
    h = headers | {"Idempotency-Key": key or str(uuid4())}
    r = client.post("/api/commerce/v1" + path, headers=h, json=payload)
    assert r.status_code == expected, r.text
    return r


def purchase(client, headers, quantities=None):
    quantities = quantities or {"A": 2}
    cart = get(client, "/customer/cart", headers)
    for code, quantity in quantities.items():
        cart = post(
            client,
            "/customer/cart/lines",
            headers,
            {
                "expected_version": cart["version"],
                "sku_id": str(seed_id("sku/" + code)),
                "quantity": quantity,
                "seen_price_version": 1,
            },
            expected=201,
        ).json()
    return post(
        client,
        "/customer/checkouts",
        headers,
        {"expected_version": cart["version"], "address": ADDRESS},
        expected=201,
    ).json()


def pay(client, headers, demo, order_id, result="SUCCEEDED", event="pay-event"):
    order = get(client, "/customer/orders/" + order_id, headers)
    attempt = post(
        client,
        "/customer/orders/" + order_id + "/payments",
        headers,
        {"expected_version": order["version"]},
        expected=201,
    ).json()
    outcome = post(
        client,
        "/demo/payments/" + attempt["id"] + "/result",
        demo,
        {"expected_version": attempt["version"], "result": result, "event_id": event},
    )
    return attempt, outcome


def test_split_payment_partial_ship_deliver_receipt(commerce):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    checkout = purchase(client, customer, {"A": 2, "B": 1})
    assert sorted(o["total_minor"] for o in checkout["orders"]) == [2000, 2000]
    ids = checkout["order_ids"]
    for index, oid in enumerate(ids):
        pay(client, customer, demo, oid, event="split-pay-" + str(index))
    aorder = next(o for o in checkout["orders"] if o["shop_id"] == str(seed_id("shop/shopA")))
    oid = aorder["id"]
    shop = str(seed_id("shop/shopA"))
    order = get(client, "/customer/orders/" + oid, customer)
    line = order["lines"][0]["id"]
    parcels = []
    for n in range(2):
        order = get(client, "/customer/orders/" + oid, customer)
        shipment = post(
            client,
            f"/merchant/shops/{shop}/orders/{oid}/shipments",
            owner,
            {
                "expected_version": order["version"],
                "lines": [{"order_line_id": line, "quantity": 1}],
            },
            expected=201,
        ).json()
        parcels.append(shipment)
        order = get(client, "/customer/orders/" + oid, customer)
        assert order["status"] == ("PARTIALLY_SHIPPED" if n == 0 else "SHIPPED")
    post(
        client,
        f"/customer/orders/{oid}/confirm-receipt",
        customer,
        {"expected_version": order["version"]},
        expected=409,
    )
    for n, parcel in enumerate(parcels):
        payload = {
            "expected_version": parcel["version"],
            "event_id": "delivery-" + str(n),
            "kind": "DELIVERED",
            "description": "Simulated delivery",
            "occurred_at": clock.now().isoformat(),
        }
        post(client, f"/demo/shipments/{parcel['id']}/events", demo, payload)
    order = get(client, "/customer/orders/" + oid, customer)
    completed = post(
        client,
        f"/customer/orders/{oid}/confirm-receipt",
        customer,
        {"expected_version": order["version"]},
    ).json()
    assert completed["status"] == "COMPLETED"
    assert completed["after_sale_cases"] == []
    merchant = get(client, f"/merchant/shops/{shop}/orders/{oid}", owner)
    assert merchant["checkout_id"] is None
    assert merchant["shipments"] == completed["shipments"]
    with Session(engine) as db:
        a = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        b = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/B")))
        assert (a.on_hand, a.reserved, b.on_hand, b.reserved) == (3, 0, 2, 0)
        assert db.scalar(select(func.count()).select_from(Shipment)) == 2


def test_payment_failure_retry_snapshot_and_event_replay(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer)["order_ids"][0]
    failed, _ = pay(client, customer, demo, oid, result="FAILED", event="failure")
    attempt, success = pay(client, customer, demo, oid, event="success")
    replay = post(
        client,
        f"/demo/payments/{attempt['id']}/result",
        demo,
        {"expected_version": 1, "result": "SUCCEEDED", "event_id": "success"},
        key="new-http-key",
    )
    assert replay.json() == success.json()
    conflict = post(
        client,
        f"/demo/payments/{attempt['id']}/result",
        demo,
        {"expected_version": 1, "result": "FAILED", "event_id": "success"},
        expected=409,
    )
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    order = get(client, "/customer/orders/" + oid, customer)
    assert order["status"] == "READY_TO_SHIP"
    assert sorted(a["state"] for a in order["payment_attempts"]) == ["FAILED", "SUCCEEDED"]
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.reason == "PAYMENT_CONSUMED")
            )
            == 1
        )


@pytest.mark.parametrize("seconds,expected", [(899, 200), (900, 410), (901, 410)])
def test_payment_expiry_exact_boundary(commerce, seconds, expected):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer)["order_ids"][0]
    order = get(client, "/customer/orders/" + oid, customer)
    attempt = post(
        client,
        f"/customer/orders/{oid}/payments",
        customer,
        {"expected_version": order["version"]},
        expected=201,
    ).json()
    clock.value += timedelta(seconds=seconds)
    payload = {
        "expected_version": attempt["version"],
        "result": "SUCCEEDED",
        "event_id": "boundary",
    }
    response = post(
        client,
        f"/demo/payments/{attempt['id']}/result",
        demo,
        payload,
        key="boundary",
        expected=expected,
    )
    if expected == 410:
        assert response.json()["error"]["code"] == "ORDER_EXPIRED"
        again = post(
            client,
            f"/demo/payments/{attempt['id']}/result",
            demo,
            payload,
            key="boundary",
            expected=410,
        )
        assert again.json() == response.json()
        assert again.headers["Idempotent-Replay"] == "true"
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inv.on_hand, inv.reserved) == ((3, 0) if expected == 200 else (5, 0))
        assert db.get(Order, UUID(oid)).status == (
            "READY_TO_SHIP" if expected == 200 else "CANCELLED"
        )


def test_permissions_before_validation_and_replay(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    other = signin(client, "customer.b")
    staff = signin(client, "staff.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer)["order_ids"][0]
    path = f"/customer/orders/{oid}/cancel"
    wrong = post(client, path, other, {"role": "admin"}, expected=404)
    assert wrong.json()["error"]["details"] == {}
    post(client, path, demo, {}, expected=403)
    post(
        client,
        f"/merchant/shops/{seed_id('shop/shopA')}/inventory/{seed_id('sku/A')}/adjust",
        staff,
        {},
        expected=403,
    )
    order = get(client, "/customer/orders/" + oid, customer)
    payload = {"expected_version": order["version"], "reason": "Test cancellation"}
    response = post(client, path, customer, payload, key="cancel")
    with Session(engine) as db, db.begin():
        db.execute(
            update(CommerceAccount)
            .where(CommerceAccount.username == "customer.a")
            .values(active=False)
        )
    denied = post(client, path, customer, payload, key="cancel", expected=401)
    assert denied.json()["error"]["code"] == "UNAUTHENTICATED"
    assert response.json()["status"] == "CANCELLED"


def test_atomic_stock_price_and_closed_inputs(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    cart = get(client, "/customer/cart", customer)
    for code in ["A", "Z"]:
        cart = post(
            client,
            "/customer/cart/lines",
            customer,
            {
                "expected_version": cart["version"],
                "sku_id": str(seed_id("sku/" + code)),
                "quantity": 1,
                "seen_price_version": 1,
            },
            expected=201,
        ).json()
    rejected = post(
        client,
        "/customer/checkouts",
        customer,
        {"expected_version": cart["version"], "address": ADDRESS},
        expected=409,
    )
    assert rejected.json()["error"]["code"] == "STOCK_UNAVAILABLE"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.scalar(select(func.count()).select_from(StockReservation)) == 0
        assert db.scalar(select(func.count()).select_from(CartLine)) == 2
    for bad in [
        {
            "expected_version": True,
            "sku_id": str(seed_id("sku/A")),
            "quantity": 1,
            "seen_price_version": 1,
        },
        {
            "expected_version": cart["version"],
            "sku_id": str(seed_id("sku/A")),
            "quantity": True,
            "seen_price_version": 1,
        },
        {
            "expected_version": cart["version"],
            "sku_id": str(seed_id("sku/A")),
            "quantity": 1,
            "seen_price_version": 1,
            "role": "OWNER",
        },
    ]:
        post(client, "/customer/cart/lines", customer, bad, expected=400)
    duplicate = client.post(
        "/api/commerce/v1/customer/cart/lines",
        headers=customer | {"Idempotency-Key": "duplicate"},
        content='{"quantity":1,"quantity":2}',
    )
    assert duplicate.status_code == 400
    assert client.get("/api/commerce/v1/catalog/products?limit=2&limit=3").status_code == 400


def test_last_item_real_concurrent_connections(commerce):
    client, engine, _ = commerce
    customers = [signin(client, name) for name in ["customer.a", "customer.b"]]
    bodies = []
    for headers in customers:
        cart = get(client, "/customer/cart", headers)
        added = post(
            client,
            "/customer/cart/lines",
            headers,
            {
                "expected_version": cart["version"],
                "sku_id": str(seed_id("sku/L")),
                "quantity": 1,
                "seen_price_version": 1,
            },
            expected=201,
        ).json()
        bodies.append({"expected_version": added["version"], "address": ADDRESS})
    barrier = Barrier(2)

    def checkout(index):
        barrier.wait()
        return client.post(
            "/api/commerce/v1/customer/checkouts",
            headers=customers[index] | {"Idempotency-Key": "last-item"},
            json=bodies[index],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(checkout, range(2)))
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    assert (
        next(r for r in results if r.status_code == 409).json()["error"]["code"]
        == "STOCK_UNAVAILABLE"
    )
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/L")))
        assert (inv.on_hand, inv.reserved) == (1, 1)
        assert db.scalar(select(func.count()).select_from(Order)) == 1


def test_checkout_expiry_releases_entire_old_multiline_order(commerce):
    client, engine, clock = commerce
    c1 = signin(client, "customer.a")
    c2 = signin(client, "customer.b")
    checkout = purchase(client, c1, {"A": 2, "L": 1})
    assert len(checkout["order_ids"]) == 1
    old_id = checkout["order_ids"][0]
    clock.value += timedelta(minutes=15)
    before = get(client, "/customer/orders/" + old_id, c1)
    assert before["payment_expired"] is True
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).reserved == 2
        )
    fresh = purchase(client, c2, {"L": 1})
    assert fresh["order_ids"] != checkout["order_ids"]
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).reserved == 0
        )
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/L"))).reserved == 1
        )
        assert db.get(Order, UUID(old_id)).cancel_reason_code == "ORDER_EXPIRED"


def test_cancel_expired_stale_version_commits410_and_replays(commerce):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    oid = purchase(client, customer)["order_ids"][0]
    clock.value += timedelta(minutes=15)
    payload = {"expected_version": 999, "reason": "Test cancellation"}
    r = post(
        client,
        f"/customer/orders/{oid}/cancel",
        customer,
        payload,
        key="expiry-cancel",
        expected=410,
    )
    again = post(
        client,
        f"/customer/orders/{oid}/cancel",
        customer,
        payload,
        key="expiry-cancel",
        expected=410,
    )
    assert again.json() == r.json()
    assert again.headers["Idempotent-Replay"] == "true"
    with Session(engine) as db:
        assert db.get(Order, UUID(oid)).status == "CANCELLED"
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).reserved == 0
        )


def test_cart_delete_original_replay_and_catalog_controls(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    cart = get(client, "/customer/cart", customer)
    sku = str(seed_id("sku/A"))
    added = post(
        client,
        "/customer/cart/lines",
        customer,
        {
            "expected_version": cart["version"],
            "sku_id": sku,
            "quantity": 1,
            "seen_price_version": 1,
        },
        expected=201,
    ).json()
    assert added["lines"][0]["product_title"] == "Fictional Product A"
    assert added["lines"][0]["shop_name"] == "shopA"
    body = {"expected_version": added["version"]}
    for index in range(2):
        r = client.request(
            "DELETE",
            f"/api/commerce/v1/customer/cart/lines/{sku}",
            headers=customer | {"Idempotency-Key": "delete-line"},
            json=body,
        )
        assert r.status_code == 204, r.text
        if index:
            assert r.headers["Idempotent-Replay"] == "true"
    product = str(seed_id("product/A"))
    shop = str(seed_id("shop/shopA"))
    p = get(client, f"/merchant/shops/{shop}/products/{product}", owner)
    archived = post(
        client,
        f"/merchant/shops/{shop}/products/{product}/archive",
        owner,
        {"expected_version": p["version"]},
    ).json()
    assert client.get("/api/commerce/v1/catalog/products/" + product).status_code == 404
    post(
        client,
        f"/merchant/shops/{shop}/products/{product}/publish",
        owner,
        {"expected_version": archived["version"]},
    )
    assert client.get("/api/commerce/v1/catalog/products/" + product).status_code == 200


def test_price_confirmation_inventory_guard_and_order_snapshot(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    shop = str(seed_id("shop/shopA"))
    product = str(seed_id("product/A"))
    sku = str(seed_id("sku/A"))
    cart = get(client, "/customer/cart", customer)
    cart = post(
        client,
        "/customer/cart/lines",
        customer,
        {
            "expected_version": cart["version"],
            "sku_id": sku,
            "quantity": 2,
            "seen_price_version": 1,
        },
        expected=201,
    ).json()
    post(
        client,
        f"/merchant/shops/{shop}/products/{product}/skus/{sku}/edit",
        owner,
        {"expected_version": 1, "unit_price_minor": 1234, "active": True},
    )
    rejected = post(
        client,
        "/customer/checkouts",
        customer,
        {"expected_version": cart["version"], "address": ADDRESS},
        expected=409,
    )
    assert rejected.json()["error"]["code"] == "PRICE_CHANGED"
    cart = post(
        client,
        "/customer/cart/lines",
        customer,
        {
            "expected_version": cart["version"],
            "sku_id": sku,
            "quantity": 2,
            "seen_price_version": 2,
        },
    ).json()
    checkout = post(
        client,
        "/customer/checkouts",
        customer,
        {"expected_version": cart["version"], "address": ADDRESS},
        expected=201,
    ).json()
    inv = get(client, f"/merchant/shops/{shop}/inventory/{sku}", owner)
    blocked = post(
        client,
        f"/merchant/shops/{shop}/inventory/{sku}/adjust",
        owner,
        {"expected_version": inv["version"], "delta": -4, "reason": "Test guard"},
        expected=409,
    )
    assert blocked.json()["error"]["code"] == "STOCK_UNAVAILABLE"
    post(
        client,
        f"/merchant/shops/{shop}/products/{product}/edit",
        owner,
        {
            "expected_version": 1,
            "title": "New display title",
            "description": "New display description",
        },
    )
    post(
        client,
        f"/merchant/shops/{shop}/products/{product}/skus/{sku}/edit",
        owner,
        {"expected_version": 2, "unit_price_minor": 2000, "active": False},
    )
    order = get(client, "/customer/orders/" + checkout["order_ids"][0], customer)
    assert order["lines"][0]["title"] == "Fictional Product A"
    assert order["lines"][0]["unit_price_minor"] == 1234
    assert order["total_minor"] == 2468


def test_tracking_recovery_time_and_terminal_guards(commerce):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer, {"A": 1})["order_ids"][0]
    pay(client, customer, demo, oid)
    order = get(client, "/customer/orders/" + oid, customer)
    path = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
    parcel = post(
        client,
        path,
        owner,
        {
            "expected_version": order["version"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        },
        expected=201,
    ).json()
    endpoint = f"/demo/shipments/{parcel['id']}/events"
    version = 1
    for index, kind in enumerate(["EXCEPTION", "IN_TRANSIT", "DELIVERED"]):
        clock.value += timedelta(seconds=1)
        payload = {
            "expected_version": version,
            "event_id": "event-" + str(index),
            "kind": kind,
            "description": "Simulated " + kind,
            "occurred_at": clock.now().isoformat(),
        }
        result = post(client, endpoint, demo, payload).json()
        version = result["version"]
        if index == 0:
            late = payload | {
                "event_id": "late",
                "expected_version": version,
                "kind": "IN_TRANSIT",
                "occurred_at": (clock.now() - timedelta(seconds=2)).isoformat(),
            }
            assert (
                post(client, endpoint, demo, late, expected=409).json()["error"]["code"]
                == "INVALID_EVENT_ORDER"
            )
            future = late | {
                "event_id": "future",
                "occurred_at": (clock.now() + timedelta(seconds=2)).isoformat(),
            }
            assert (
                post(client, endpoint, demo, future, expected=409).json()["error"]["code"]
                == "INVALID_EVENT_ORDER"
            )
    replay = post(
        client, endpoint, demo, payload | {"expected_version": 1}, key="different-http-key"
    )
    assert replay.json() == result
    backwards = payload | {
        "event_id": "backwards",
        "expected_version": version,
        "kind": "IN_TRANSIT",
    }
    assert (
        post(client, endpoint, demo, backwards, expected=409).json()["error"]["code"]
        == "INVALID_STATE"
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(TrackingEvent)) == 4


def test_mutation_failure_rolls_back_every_aggregate(commerce, monkeypatch):
    from app.commerce.service import Commerce

    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    cart = get(client, "/customer/cart", customer)
    for code in ["A", "B"]:
        cart = post(
            client,
            "/customer/cart/lines",
            customer,
            {
                "expected_version": cart["version"],
                "sku_id": str(seed_id("sku/" + code)),
                "quantity": 1,
                "seen_price_version": 1,
            },
            expected=201,
        ).json()
    original = Commerce.audit

    def failed(self, action, *args, **kwargs):
        if action.startswith("customer.checkout.create"):
            raise RuntimeError("Injected safe audit failure")
        return original(self, action, *args, **kwargs)

    monkeypatch.setattr(Commerce, "audit", failed)
    r = post(
        client,
        "/customer/checkouts",
        customer,
        {"expected_version": cart["version"], "address": ADDRESS},
        key="failed-checkout",
        expected=500,
    )
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.scalar(select(func.count()).select_from(Checkout)) == 0
        assert db.scalar(select(func.count()).select_from(StockReservation)) == 0
        assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
        assert db.scalar(select(func.count()).select_from(CartLine)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.key == "failed-checkout")
            )
            == 0
        )


def test_same_checkout_key_concurrency_original_snapshot(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    cart = get(client, "/customer/cart", customer)
    cart = post(
        client,
        "/customer/cart/lines",
        customer,
        {
            "expected_version": cart["version"],
            "sku_id": str(seed_id("sku/A")),
            "quantity": 1,
            "seen_price_version": 1,
        },
        expected=201,
    ).json()
    payload = {"expected_version": cart["version"], "address": ADDRESS}
    barrier = Barrier(2)

    def attempt(_):
        barrier.wait()
        return client.post(
            "/api/commerce/v1/customer/checkouts",
            headers=customer | {"Idempotency-Key": "same-checkout"},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).reserved == 1
        )


def test_production_no_demo_routes_and_closed_unknown_errors():
    client = TestClient(create_app(Settings(app_env="production")))
    assert not any("/demo/" in path for path in client.get("/openapi.json").json()["paths"])
    r = client.get("/api/commerce/v1/demo/pending")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "request_id", "details"}


def test_owner_product_sku_inventory_and_nested_ownership(commerce):
    client, engine, _ = commerce
    owner = signin(client, "owner.a")
    other = signin(client, "owner.b")
    shop = str(seed_id("shop/shopA"))
    create = {
        "title": "Created test product",
        "description": "Fictional description",
        "sku": {
            "sku_code": "TEST-1",
            "options": {"size": "S"},
            "unit_price_minor": 100000000,
            "initial_stock": 99,
        },
    }
    product = post(client, f"/merchant/shops/{shop}/products", owner, create, expected=201).json()
    assert product["status"] == "DRAFT"
    assert client.get("/api/commerce/v1/catalog/products/" + product["id"]).status_code == 404
    second = post(
        client,
        f"/merchant/shops/{shop}/products/{product['id']}/skus",
        owner,
        {
            "expected_version": 1,
            "sku_code": "TEST-2",
            "options": {"size": "L"},
            "unit_price_minor": 100,
            "initial_stock": 2,
        },
        expected=201,
    ).json()
    assert second["version"] == 2 and len(second["skus"]) == 2
    repeated = post(
        client,
        f"/merchant/shops/{shop}/products/{product['id']}/skus",
        owner,
        {
            "expected_version": 2,
            "sku_code": "TEST-3",
            "options": {"size": "L"},
            "unit_price_minor": 100,
            "initial_stock": 2,
        },
        expected=409,
    )
    assert repeated.json()["error"]["code"] == "INVALID_STATE"
    published = post(
        client,
        f"/merchant/shops/{shop}/products/{product['id']}/publish",
        owner,
        {"expected_version": 2},
    ).json()
    assert published["status"] == "PUBLISHED"
    assert client.get("/api/commerce/v1/catalog/products/" + product["id"]).status_code == 200
    foreign = client.get(
        f"/api/commerce/v1/merchant/shops/{seed_id('shop/shopB')}/products/{product['id']}",
        headers=other,
    )
    assert foreign.status_code == 404
    sku = product["skus"][0]["id"]
    inv = get(client, f"/merchant/shops/{shop}/inventory/{sku}", owner)
    updated = post(
        client,
        f"/merchant/shops/{shop}/inventory/{sku}/adjust",
        owner,
        {"expected_version": inv["version"], "delta": -1, "reason": "Fictional count correction"},
    ).json()
    assert updated["on_hand"] == 98


def test_seed_preserves_business_password_and_member_changes(commerce):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    oid = purchase(client, customer, {"A": 1})["order_ids"][0]
    with Session(engine) as db, db.begin():
        actor = db.get(CommerceAccount, seed_id("account/customer.a"))
        before = actor.password_hash
        actor.customer_enabled = False
    with Session(engine) as db:
        seed_commerce(db, "different-valid-test-password", clock.now())
    with Session(engine) as db:
        actor = db.get(CommerceAccount, seed_id("account/customer.a"))
        assert actor.password_hash == before and actor.customer_enabled is False
        assert db.get(Order, UUID(oid)) is not None
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).reserved == 1
        )


def test_pending_lock_timeout_is_safe_and_does_not_write(commerce):
    from sqlalchemy import text

    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    cart = get(client, "/customer/cart", customer)
    with engine.begin() as blocker:
        blocker.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(current_schema() || '-commerce-v1',0))"
            )
        )
        denied = post(
            client,
            "/customer/cart/lines",
            customer,
            {
                "expected_version": cart["version"],
                "sku_id": str(seed_id("sku/A")),
                "quantity": 1,
                "seen_price_version": 1,
            },
            key="busy",
            expected=409,
        )
    assert denied.json()["error"]["code"] == "OPERATION_BUSY"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CartLine)) == 0
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0
        failures = list(
            db.scalars(
                select(BusinessAudit).where(
                    BusinessAudit.safe_metadata["code"].astext == "OPERATION_BUSY"
                )
            )
        )
        assert len(failures) == 1
        assert failures[0].safe_metadata == {"outcome": "FAILED", "code": "OPERATION_BUSY"}


def test_pay_cancel_and_ship_concurrency_preserve_inventory(commerce):
    client, engine, _ = commerce
    c = signin(client, "customer.a")
    demo = signin(client, "demo")
    owner = signin(client, "owner.a")
    oid = purchase(client, c, {"A": 1})["order_ids"][0]
    order = get(client, "/customer/orders/" + oid, c)
    attempt = post(
        client,
        f"/customer/orders/{oid}/payments",
        c,
        {"expected_version": order["version"]},
        expected=201,
    ).json()
    order = get(client, "/customer/orders/" + oid, c)
    barrier = Barrier(2)

    def race(index):
        barrier.wait()
        if index:
            return client.post(
                f"/api/commerce/v1/customer/orders/{oid}/cancel",
                headers=c | {"Idempotency-Key": "race-cancel"},
                json={"expected_version": order["version"], "reason": "Fictional cancellation"},
            )
        return client.post(
            f"/api/commerce/v1/demo/payments/{attempt['id']}/result",
            headers=demo | {"Idempotency-Key": "race-pay"},
            json={"expected_version": 1, "result": "SUCCEEDED", "event_id": "race-pay"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    order = get(client, "/customer/orders/" + oid, c)
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inv.on_hand, inv.reserved) == (
            (4, 0) if order["status"] == "READY_TO_SHIP" else (5, 0)
        )
    if order["status"] == "CANCELLED":
        oid = purchase(client, c, {"A": 1})["order_ids"][0]
        pay(client, c, demo, oid, event="new-race")
        order = get(client, "/customer/orders/" + oid, c)
    barrier = Barrier(2)
    payload = {
        "expected_version": order["version"],
        "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
    }

    def ship(index):
        barrier.wait()
        return client.post(
            f"/api/commerce/v1/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments",
            headers=owner | {"Idempotency-Key": "ship-race-" + str(index)},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(ship, range(2)))
    assert sorted(r.status_code for r in results) == [201, 409]
    with Session(engine) as db:
        assert db.get(OrderLine, UUID(order["lines"][0]["id"])).shipped_qty == 1
        assert (
            db.scalar(
                select(func.count()).select_from(Shipment).where(Shipment.order_id == UUID(oid))
            )
            == 1
        )


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-06 08:00:00+00:00",
        "20261006T080000Z",
        "2026-W41-2T08:00:00Z",
        "2026-10-06T08:00:00",
        "2026-10-06T08:00:00+00:99",
    ],
)
def test_tracking_time_rejects_non_rfc3339_before_mutation(value):
    from app.commerce.errors import CommerceError
    from app.commerce.inputs import timestamp

    with pytest.raises(CommerceError) as error:
        timestamp(value)
    assert error.value.code == "INVALID_REQUEST"


def test_invalid_merchant_path_does_not_disclose_before_identity(commerce):
    client, _, clock = commerce
    path = "/api/commerce/v1/merchant/shops/not-a-uuid/orders"
    assert client.get(path).status_code == 401
    headers = signin(client, "owner.a")
    assert client.get(path, headers=headers).status_code == 404
    clock.value += timedelta(hours=8)
    assert client.get(path, headers=headers).status_code == 401


def test_address_revision_and_shipping_prestate(commerce):
    from app.commerce.models import AddressRevision

    client, engine, _ = commerce
    c = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    checkout = purchase(client, c, {"A": 2})
    oid = checkout["order_ids"][0]
    order = get(client, "/customer/orders/" + oid, c)
    changed = ADDRESS | {"address_line": "Another fictional address"}
    order = post(
        client,
        f"/customer/orders/{oid}/address",
        c,
        {"expected_version": order["version"], "address": changed},
    ).json()
    assert order["address_revision"] == 2 and order["address"] == changed
    with Session(engine) as db:
        assert db.get(Checkout, UUID(checkout["id"])).address_snapshot == ADDRESS
        assert db.scalar(select(func.count()).select_from(AddressRevision)) == 2
    pay(client, c, demo, oid)
    order = get(client, "/customer/orders/" + oid, c)
    order = post(
        client,
        f"/customer/orders/{oid}/address",
        c,
        {"expected_version": order["version"], "address": ADDRESS},
    ).json()
    path = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
    parcel = post(
        client,
        path,
        owner,
        {
            "expected_version": order["version"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        },
        key="before-revoke",
        expected=201,
    ).json()
    order = get(client, "/customer/orders/" + oid, c)
    assert (
        post(
            client,
            f"/customer/orders/{oid}/address",
            c,
            {"expected_version": order["version"], "address": changed},
            expected=409,
        ).json()["error"]["code"]
        == "INVALID_STATE"
    )
    event = parcel["events"][0]["event_id"]
    payload = {
        "expected_version": 1,
        "event_id": event,
        "kind": "IN_TRANSIT",
        "description": "Test collision",
        "occurred_at": parcel["shipped_at"],
    }
    collision = post(client, f"/demo/shipments/{parcel['id']}/events", demo, payload, expected=409)
    assert collision.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_membership_revocation_precedes_shipment_replay(commerce):
    from app.commerce.models import ShopMembership

    client, engine, _ = commerce
    c = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    oid = purchase(client, c, {"A": 1})["order_ids"][0]
    pay(client, c, demo, oid)
    order = get(client, "/customer/orders/" + oid, c)
    path = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
    payload = {
        "expected_version": order["version"],
        "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
    }
    post(client, path, owner, payload, key="membership", expected=201)
    with Session(engine) as db, db.begin():
        db.execute(
            update(ShopMembership)
            .where(ShopMembership.account_id == seed_id("account/owner.a"))
            .values(active=False)
        )
    rejected = post(client, path, owner, payload, key="membership", expected=403)
    assert rejected.json()["error"]["code"] == "CAPABILITY_REQUIRED"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Shipment)) == 1


def test_combined_capabilities_suspended_new_purchase_existing_fulfillment(commerce):
    from app.commerce.models import Shop

    client, engine, _ = commerce
    c = signin(client, "customer.a")
    dual = signin(client, "dual.a")
    demo = signin(client, "demo")
    oid = purchase(client, c, {"A": 1})["order_ids"][0]
    pay(client, c, demo, oid)
    assert client.get("/api/commerce/v1/customer/orders/" + oid, headers=dual).status_code == 404
    order = get(client, f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}", dual)
    with Session(engine) as db, db.begin():
        db.execute(update(Shop).where(Shop.id == seed_id("shop/shopA")).values(status="SUSPENDED"))
    path = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
    post(
        client,
        path,
        dual,
        {
            "expected_version": order["version"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        },
        expected=201,
    )
    assert get(client, "/customer/cart", dual)["lines"] == []
    cart = get(client, "/customer/cart", c)
    rejected = post(
        client,
        "/customer/cart/lines",
        c,
        {
            "expected_version": cart["version"],
            "sku_id": str(seed_id("sku/A")),
            "quantity": 1,
            "seen_price_version": 1,
        },
        expected=409,
    )
    assert rejected.json()["error"]["code"] == "NOT_PURCHASABLE"
    assert (
        client.get("/api/commerce/v1/catalog/products/" + str(seed_id("product/A"))).status_code
        == 404
    )


def test_authority_revoked_while_waiting_is_refreshed_before_write(commerce, monkeypatch):
    from threading import Event

    from sqlalchemy import text

    from app.commerce.service import Commerce

    client, engine, _ = commerce
    c = signin(client, "customer.a")
    cart = get(client, "/customer/cart", c)
    entering = Event()
    original = Commerce.acquire_write

    def acquire(self):
        entering.set()
        return original(self)

    monkeypatch.setattr(Commerce, "acquire_write", acquire)
    blocker = engine.connect()
    transaction = blocker.begin()
    blocker.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || '-commerce-v1',0))")
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.post,
                "/api/commerce/v1/customer/cart/lines",
                headers=c | {"Idempotency-Key": "revoked-wait"},
                json={
                    "expected_version": cart["version"],
                    "sku_id": str(seed_id("sku/A")),
                    "quantity": 1,
                    "seen_price_version": 1,
                },
            )
            assert entering.wait(1)
            with Session(engine) as db, db.begin():
                db.execute(
                    update(CommerceAccount)
                    .where(CommerceAccount.id == seed_id("account/customer.a"))
                    .values(active=False)
                )
            transaction.commit()
            result = pending.result(timeout=3)
        assert result.status_code == 401, result.text
    finally:
        if transaction.is_active:
            transaction.rollback()
        blocker.close()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CartLine)) == 0
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_body_stream_limit_follows_authorization_before_parse_and_locks(commerce):
    client, engine, _ = commerce
    payload = b"x" * 65537
    endpoint = "/api/commerce/v1/customer/cart/lines"
    assert client.post(endpoint, content=payload).status_code == 401
    demo = signin(client, "demo")
    assert client.post(endpoint, headers=demo, content=payload).status_code == 403
    customer = signin(client, "customer.a")
    result = client.post(
        endpoint, headers=customer | {"Idempotency-Key": "too-large"}, content=payload
    )
    assert result.status_code == 400
    assert result.json()["error"]["code"] == "INVALID_REQUEST"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CartLine)) == 0


def test_body_stream_disconnect_returns_closed_error(commerce, monkeypatch):
    from starlette.requests import ClientDisconnect, Request

    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    original = Request.stream

    async def disconnected(request):
        if request.url.path.endswith("/cart/lines"):
            raise ClientDisconnect()
        async for chunk in original(request):
            yield chunk

    monkeypatch.setattr(Request, "stream", disconnected)
    result = client.post(
        "/api/commerce/v1/customer/cart/lines",
        headers=customer | {"Idempotency-Key": "disconnect"},
        json={},
    )
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "INTERNAL_ERROR"
    with Session(engine) as db:
        audit = db.scalar(
            select(BusinessAudit).where(
                BusinessAudit.safe_metadata["code"].astext == "INTERNAL_ERROR"
            )
        )
        assert audit.safe_metadata == {"outcome": "FAILED", "code": "INTERNAL_ERROR"}


def test_shop_payment_results_are_independent(commerce):
    client, engine, _ = commerce
    c = signin(client, "customer.a")
    demo = signin(client, "demo")
    checkout = purchase(client, c, {"A": 2, "B": 1})
    for summary in checkout["orders"]:
        success = summary["shop_id"] == str(seed_id("shop/shopA"))
        pay(
            client,
            c,
            demo,
            summary["id"],
            result="SUCCEEDED" if success else "FAILED",
            event="mixed-" + summary["shop_id"],
        )
    statuses = {
        o["shop_id"]: (o["status"], o["financial_status"])
        for o in get(client, "/customer/checkouts/" + checkout["id"], c)["orders"]
    }
    assert statuses[str(seed_id("shop/shopA"))] == ("READY_TO_SHIP", "PAID")
    assert statuses[str(seed_id("shop/shopB"))] == ("PENDING_PAYMENT", "UNPAID")
    with Session(engine) as db:
        a = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        b = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/B")))
        assert (a.on_hand, a.reserved, b.on_hand, b.reserved) == (3, 0, 3, 1)


@pytest.mark.parametrize("operation", ["demo.payment", "merchant.ship", "demo.tracking"])
def test_audit_failure_rolls_back_payment_shipment_tracking(commerce, monkeypatch, operation):
    from app.commerce.models import PaymentAttempt, SimulationEvent
    from app.commerce.service import Commerce

    client, engine, clock = commerce
    c = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    oid = purchase(client, c, {"A": 1})["order_ids"][0]
    if operation == "demo.payment":
        order = get(client, "/customer/orders/" + oid, c)
        attempt = post(
            client,
            f"/customer/orders/{oid}/payments",
            c,
            {"expected_version": order["version"]},
            expected=201,
        ).json()
        endpoint = f"/demo/payments/{attempt['id']}/result"
        payload = {"expected_version": 1, "result": "SUCCEEDED", "event_id": "failure-pay"}
        headers = demo
    else:
        pay(client, c, demo, oid)
        order = get(client, "/customer/orders/" + oid, c)
        endpoint = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
        payload = {
            "expected_version": order["version"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        }
        headers = owner
        if operation == "demo.tracking":
            parcel = post(client, endpoint, headers, payload, expected=201).json()
            endpoint = f"/demo/shipments/{parcel['id']}/events"
            payload = {
                "expected_version": 1,
                "event_id": "failure-track",
                "kind": "DELIVERED",
                "description": "Simulated delivery",
                "occurred_at": clock.now().isoformat(),
            }
            headers = demo
    before = get(client, "/customer/orders/" + oid, c)
    original = Commerce.audit

    def failed(self, action, *args, **kwargs):
        if action.startswith(operation):
            raise RuntimeError("Injected safe audit failure")
        return original(self, action, *args, **kwargs)

    monkeypatch.setattr(Commerce, "audit", failed)
    r = post(client, endpoint, headers, payload, key="failed-" + operation, expected=500)
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    after = get(client, "/customer/orders/" + oid, c)
    assert after == before
    with Session(engine) as db:
        audits = list(
            db.scalars(
                select(BusinessAudit).where(
                    BusinessAudit.action == operation,
                    BusinessAudit.safe_metadata["code"].astext == "INTERNAL_ERROR",
                )
            )
        )
        assert len(audits) == 1
        assert audits[0].safe_metadata == {"outcome": "FAILED", "code": "INTERNAL_ERROR"}
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inv.on_hand, inv.reserved) == ((5, 1) if operation == "demo.payment" else (4, 0))
        assert (
            db.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.key == "failed-" + operation)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SimulationEvent)
                .where(SimulationEvent.event_id.in_(["failure-pay", "failure-track"]))
            )
            == 0
        )
        if operation == "demo.payment":
            assert db.get(PaymentAttempt, UUID(attempt["id"])).state == "PENDING"


def test_expiry_inventory_adjustment_real_concurrency(commerce):
    client, engine, clock = commerce
    c = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    oid = purchase(client, c, {"A": 2})["order_ids"][0]
    shop = str(seed_id("shop/shopA"))
    sku = str(seed_id("sku/A"))
    inv = get(client, f"/merchant/shops/{shop}/inventory/{sku}", owner)
    clock.value += timedelta(minutes=15)
    barrier = Barrier(2)

    def race(index):
        barrier.wait()
        if index:
            return client.post(
                "/api/commerce/v1/demo/orders/expire",
                headers=demo | {"Idempotency-Key": "expire-race"},
                json={"order_ids": [oid]},
            )
        return client.post(
            f"/api/commerce/v1/merchant/shops/{shop}/inventory/{sku}/adjust",
            headers=owner | {"Idempotency-Key": "adjust-race"},
            json={
                "expected_version": inv["version"],
                "delta": -3,
                "reason": "Fictional inventory correction",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, range(2)))
    assert results[1].status_code == 200
    assert results[0].status_code in {200, 409}
    if results[0].status_code == 409:
        assert results[0].json()["error"]["code"] == "VERSION_CONFLICT"
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert inv.reserved == 0 and inv.on_hand == (2 if results[0].status_code == 200 else 5)
        assert db.get(Order, UUID(oid)).status == "CANCELLED"


def test_actor_row_lock_bounds_business_and_failure_audit(commerce):
    """Audit FK waits use their own bounded timeout after the business rollback."""
    from time import monotonic

    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    cart = get(client, "/customer/cart", customer)
    blocker = engine.connect()
    transaction = blocker.begin()
    blocker.execute(
        select(CommerceAccount.id)
        .where(CommerceAccount.id == seed_id("account/customer.a"))
        .with_for_update()
    )
    pool = ThreadPoolExecutor(max_workers=1)
    started = monotonic()
    pending = pool.submit(
        client.post,
        "/api/commerce/v1/customer/cart/lines",
        headers=customer | {"Idempotency-Key": "actor-lock-busy"},
        json={
            "expected_version": cart["version"],
            "sku_id": str(seed_id("sku/A")),
            "quantity": 1,
            "seen_price_version": 1,
        },
    )
    try:
        result = pending.result(timeout=6)
        assert monotonic() - started < 6
        assert result.status_code == 409, result.text
        assert result.json()["error"]["code"] == "OPERATION_BUSY"
        assert result.json()["error"]["details"] == {}
    finally:
        transaction.rollback()
        blocker.close()
        pool.shutdown(wait=True)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CartLine)) == 0
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inv.on_hand, inv.reserved) == (5, 0)


def test_shipment_rejects_excess_and_foreign_lines_then_replays_original(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    other = signin(client, "customer.b")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer, {"A": 2})["order_ids"][0]
    foreign_id = purchase(client, other, {"A": 1})["order_ids"][0]
    foreign = get(client, "/customer/orders/" + foreign_id, other)
    pay(client, customer, demo, oid)
    order = get(client, "/customer/orders/" + oid, customer)
    path = f"/merchant/shops/{seed_id('shop/shopA')}/orders/{oid}/shipments"
    body = {
        "expected_version": order["version"],
        "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 3}],
    }
    assert (
        post(client, path, owner, body, expected=409).json()["error"]["code"] == "QUANTITY_CONFLICT"
    )
    foreign_body = body | {"lines": [{"order_line_id": foreign["lines"][0]["id"], "quantity": 1}]}
    assert (
        post(client, path, owner, foreign_body, expected=404).json()["error"]["code"] == "NOT_FOUND"
    )
    body["lines"][0]["quantity"] = 2
    created = post(client, path, owner, body, key="original-shipment", expected=201)
    replay = post(client, path, owner, body, key="original-shipment")
    assert replay.json() == created.json()
    assert replay.headers["Idempotent-Replay"] == "true"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Shipment)) == 1
        assert db.get(OrderLine, UUID(order["lines"][0]["id"])).shipped_qty == 2


def test_two_distinct_success_callbacks_consume_inventory_once(commerce):
    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    demo = signin(client, "demo")
    oid = purchase(client, customer, {"A": 1})["order_ids"][0]
    order = get(client, "/customer/orders/" + oid, customer)
    attempt = post(
        client,
        f"/customer/orders/{oid}/payments",
        customer,
        {"expected_version": order["version"]},
        expected=201,
    ).json()
    barrier = Barrier(2)

    def callback(index):
        barrier.wait()
        return client.post(
            f"/api/commerce/v1/demo/payments/{attempt['id']}/result",
            headers=demo | {"Idempotency-Key": f"distinct-success-{index}"},
            json={"expected_version": 1, "result": "SUCCEEDED", "event_id": f"event-{index}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(callback, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    with Session(engine) as db:
        inventory = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert (inventory.on_hand, inventory.reserved) == (4, 0)
        assert (
            db.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.reason == "PAYMENT_CONSUMED")
            )
            == 1
        )
