"""Explicit matrix rejection variants, using real PostgreSQL isolated schemas."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_commerce import commerce as commerce
from test_commerce import get, pay, post, purchase, signin

from app.commerce.models import Inventory
from app.commerce.seed import seed_id
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.database


def test_unauthenticated_and_foreign_namespace_token_cannot_read_cart_or_orders(commerce):
    client, _, _ = commerce
    for path in ["/customer/cart", "/customer/orders"]:
        for headers in ({}, {"Authorization": "Bearer " + str(uuid4())}):
            response = client.get("/api/commerce/v1" + path, headers=headers)
            assert response.status_code == 401
            assert response.json()["error"]["details"] == {}


def test_foreign_order_read_payment_cancel_and_shop_scope(commerce):
    client, _, _ = commerce
    customer, other, merchant = [signin(client, u) for u in ["customer.a", "customer.b", "owner.b"]]
    order = purchase(client, customer)["orders"][0]
    customer_path = "/customer/orders/" + order["id"]
    assert client.get("/api/commerce/v1" + customer_path, headers=other).status_code == 404
    for suffix in ["/payments", "/cancel"]:
        response = post(
            client, customer_path + suffix, other, {"expected_version": 1}, expected=404
        )
        assert response.json()["error"]["details"] == {}
    merchant_path = f"/merchant/shops/{seed_id('shop/shopB')}/orders/{order['id']}"
    assert client.get("/api/commerce/v1" + merchant_path, headers=merchant).status_code == 404
    post(client, merchant_path + "/shipments", merchant, {}, expected=404)


def test_staff_price_and_demo_order_message_capabilities_denied(commerce):
    client, _, _ = commerce
    customer, staff, demo = [signin(client, u) for u in ["customer.a", "staff.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    shop = order["shop_id"]
    post(
        client,
        f"/merchant/shops/{shop}/products/{seed_id('product/A')}/skus/{seed_id('sku/A')}/edit",
        staff,
        {},
        expected=403,
    )
    for path in [
        "/customer/orders",
        "/customer/conversations",
        f"/merchant/shops/{shop}/orders",
        f"/merchant/shops/{shop}/conversations",
    ]:
        assert client.get("/api/commerce/v1" + path, headers=demo).status_code == 403


def test_unpaid_two_unit_cancel_and_paid_cancel_preserve_stock(commerce):
    client, engine, _ = commerce
    customer, demo = [signin(client, u) for u in ["customer.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    cancelled = post(
        client,
        "/customer/orders/" + order["id"] + "/cancel",
        customer,
        {"expected_version": order["version"], "reason": "Explicit cancellation"},
    ).json()
    assert (cancelled["status"], cancelled["financial_status"]) == ("CANCELLED", "UNPAID")
    with Session(engine) as db:
        stock = db.get(Inventory, seed_id("inventory/A"))
        assert (stock.on_hand, stock.reserved) == (5, 0)
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    path = "/customer/orders/" + order["id"]
    before = get(client, path, customer)
    response = post(
        client,
        path + "/cancel",
        customer,
        {"expected_version": before["version"], "reason": "Must use after-sale"},
        expected=409,
    )
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert get(client, path, customer) == before
    with Session(engine) as db:
        stock = db.get(Inventory, seed_id("inventory/A"))
        assert (stock.on_hand, stock.reserved) == (3, 0)


def test_production_explicit_refund_callback_not_registered():
    with TestClient(create_app(Settings(app_env="production"))) as client:
        response = client.post("/api/commerce/v1/demo/refunds/" + str(uuid4()) + "/result", json={})
        assert response.status_code == 404


def test_valid_support_session_does_not_grant_commerce_access(commerce):
    from test_commerce import PASSWORD

    from app.db.seed import seed_demo

    client, engine, clock = commerce
    with Session(engine) as db, db.begin():
        seed_demo(db, clock, app_env="test", password=PASSWORD)
    login = client.post("/api/v1/auth/login", json={"username": "agent.a", "password": PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    for path in ["/customer/cart", "/customer/orders"]:
        assert client.get("/api/commerce/v1" + path, headers=headers).status_code == 401


def test_refund_event_changed_result_conflicts_and_preserves_completed_order(commerce):
    from test_commerce_step4 import case_base, make_case

    client, _, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    base = case_base(order, case, True)
    approved = post(
        client,
        base + "/decision",
        owner,
        {"expected_version": case["version"], "decision": "APPROVE", "reason": "yes"},
    ).json()
    attempt = post(
        client, base + "/refunds", owner, {"expected_version": approved["version"]}, expected=201
    ).json()
    path = "/demo/refunds/" + attempt["id"] + "/result"
    body = {"expected_version": 1, "result": "SUCCEEDED", "event_id": "immutable-refund-result"}
    original = post(client, path, demo, body, key="refund-original").json()
    before = get(client, "/customer/orders/" + order["id"], customer)
    post(client, path, demo, body | {"result": "FAILED"}, key="refund-original", expected=409)
    response = post(client, path, demo, body | {"result": "FAILED"}, expected=409)
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert post(client, path, demo, body).json() == original
    assert get(client, "/customer/orders/" + order["id"], customer) == before


def test_multiline_mixed_shipped_and_unshipped_case_is_atomic(commerce):
    client, engine, _ = commerce
    customer, owner, demo = [signin(client, u) for u in ["customer.a", "owner.a", "demo"]]
    order = purchase(client, customer, {"A": 1, "L": 1})["orders"][0]
    pay(client, customer, demo, order["id"])
    path = "/customer/orders/" + order["id"]
    current = get(client, path, customer)
    shipped = next(line for line in current["lines"] if line["sku_id"] == str(seed_id("sku/A")))
    post(
        client,
        f"/merchant/shops/{order['shop_id']}/orders/{order['id']}/shipments",
        owner,
        {
            "expected_version": current["version"],
            "lines": [{"order_line_id": shipped["id"], "quantity": 1}],
        },
        expected=201,
    )
    before = get(client, path, customer)
    response = post(
        client,
        path + "/after-sales",
        customer,
        {
            "expected_version": before["version"],
            "type": "UNSHIPPED_REFUND",
            "reason": "Mixed invalid selection",
            "lines": [{"order_line_id": line["id"], "quantity": 1} for line in before["lines"]],
        },
        expected=409,
    )
    assert response.json()["error"]["code"] == "QUANTITY_CONFLICT"
    assert get(client, path, customer) == before
    with Session(engine) as db:
        assert db.get(Inventory, seed_id("inventory/A")).on_hand == 4
        assert db.get(Inventory, seed_id("inventory/L")).on_hand == 0
