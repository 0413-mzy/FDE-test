"""Real PostgreSQL platform authority, moderation, arbitration and financial facts."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_commerce import PASSWORD, get, pay, post, purchase, signin
from test_commerce import commerce as commerce
from test_commerce_step4 import case_base, make_case

from app.commerce.models import CommerceAccount, Inventory, ShopMembership
from app.commerce.platform_models import Dispute, PlatformRole
from app.commerce.platform_seed import seed_platform
from app.commerce.seed import seed_id

pytestmark = pytest.mark.database


@pytest.fixture
def platform(commerce):
    client, engine, clock = commerce
    with Session(engine) as db:
        seed_platform(db, PASSWORD)
    return client, engine, clock


def test_independent_authority_safe_accounts_seed_and_category(platform):
    client, engine, _ = platform
    for name in ["customer.a", "owner.a", "staff.a", "demo"]:
        headers = signin(client, name)
        assert get(client, "/platform/access", headers) == {"platform_enabled": False}
        r = client.get("/api/commerce/v1/platform/accounts", headers=headers)
        assert r.status_code == 403
    platform_headers = signin(client, "platform")
    result = get(client, "/platform/accounts", platform_headers)
    assert result["items"] and all("password_hash" not in r for r in result["items"])
    category = post(
        client,
        "/platform/categories",
        platform_headers,
        {"name": "Office", "active": True},
        key="category",
        expected=201,
    ).json()
    replay = post(
        client,
        "/platform/categories",
        platform_headers,
        {"name": "Office", "active": True},
        key="category",
    ).json()
    assert replay == category
    post(
        client,
        "/platform/categories/" + category["id"] + "/edit",
        platform_headers,
        {"expected_version": 2, "name": "New", "active": False},
        expected=409,
    )
    account = next(a for a in result["items"] if a["username"] == "platform")
    post(
        client,
        "/platform/moderation",
        platform_headers,
        {
            "target_type": "ACCOUNT",
            "target_id": account["id"],
            "expected_version": account["version"],
            "action": "SUSPEND_ACCOUNT",
            "reason": "cannot suspend authority",
        },
        expected=403,
    )
    with Session(engine) as db:
        assert db.scalar(select(PlatformRole)).account_id == UUID(account["id"])
        rows = (
            db.execute(
                text(
                    "SELECT after_data FROM commerce_record_history "
                    "WHERE entity_table='commerce_platform_roles'"
                )
            )
            .scalars()
            .all()
        )
        assert rows and all("password_hash" not in r for r in rows)


def test_reporting_visibility_atomic_moderation_and_ownership(platform):
    client, _, _ = platform
    customer = signin(client, "customer.a")
    other = signin(client, "customer.b")
    admin = signin(client, "platform")
    pid = str(seed_id("product/A"))
    report = post(
        client,
        "/customer/reports",
        customer,
        {"target_type": "PRODUCT", "target_id": pid, "reason": "misleading description"},
        expected=201,
    ).json()
    assert get(client, "/customer/reports", other)["items"] == []
    post(
        client,
        "/customer/reports",
        customer,
        {"target_type": "PRODUCT", "target_id": pid, "reason": "again"},
        expected=409,
    )
    for invalid in [[], {}, True]:
        post(
            client,
            "/platform/reports/" + report["id"] + "/decision",
            admin,
            {"expected_version": 1, "decision": invalid, "action": None, "reason": "invalid"},
            expected=400,
        )
    decision = post(
        client,
        "/platform/reports/" + report["id"] + "/decision",
        admin,
        {
            "expected_version": 1,
            "decision": "RESOLVE",
            "action": "HIDE_PRODUCT",
            "reason": "confirmed misleading",
        },
        key="hide",
    ).json()
    assert decision["state"] == "RESOLVED"
    actions = get(client, "/platform/actions", admin)["items"]
    assert actions[0]["report_id"] == report["id"]
    assert client.get("/api/commerce/v1/shopping/products/" + pid).status_code == 404
    post(
        client,
        "/customer/reports",
        other,
        {"target_type": "PRODUCT", "target_id": pid, "reason": "cannot enumerate hidden"},
        expected=404,
    )
    actions = get(client, "/platform/products", admin)["items"]
    product = next(p for p in actions if p["id"] == pid)
    post(
        client,
        "/platform/moderation",
        admin,
        {
            "target_type": "PRODUCT",
            "target_id": pid,
            "expected_version": product["version"],
            "action": "RESTORE_PRODUCT",
            "reason": "corrected",
        },
        expected=201,
    )
    assert client.get("/api/commerce/v1/shopping/products/" + pid).status_code == 200


def rejected(client):
    customer = signin(client, "customer.a")
    owner = signin(client, "owner.a")
    demo = signin(client, "demo")
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    case = post(
        client,
        case_base(order, case, True) + "/decision",
        owner,
        {"expected_version": case["version"], "decision": "REJECT", "reason": "merchant refusal"},
    ).json()
    return customer, owner, demo, order, case


def test_dispute_freeze_arbitration_controlled_refund_and_reports(platform):
    client, engine, clock = platform
    customer, owner, demo, order, case = rejected(client)
    admin = signin(client, "platform")
    path = "/customer/orders/" + order["id"] + "/after-sales/" + case["id"] + "/dispute"
    dispute = post(
        client,
        path,
        customer,
        {"expected_version": case["version"], "reason": "request platform review"},
        expected=201,
    ).json()
    post(
        client,
        path,
        customer,
        {"expected_version": case["version"], "reason": "duplicate"},
        expected=409,
    )
    for action in ["address", "confirm-receipt"]:
        frozen = post(
            client,
            "/customer/orders/" + order["id"] + "/" + action,
            customer,
            {"expected_version": order["version"]},
            expected=409,
        )
        assert frozen.json()["error"]["code"] == "DISPUTE_OPEN"
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
        case_base(order, case, True) + "/decision",
        owner,
        {
            "expected_version": case["version"],
            "decision": "APPROVE",
            "reason": "cannot bypass open review",
        },
        expected=409,
    )
    post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        owner,
        {"expected_version": 1, "decision": "APPROVE", "reason": "not platform"},
        expected=403,
    )
    decision = post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        admin,
        {"expected_version": 1, "decision": "APPROVE", "reason": "original valid quantity"},
        key="approve",
    ).json()
    assert decision["state"] == "OVERTURNED"
    context = get(client, "/platform/disputes/" + dispute["id"] + "/context", admin)
    assert context["requested_amount_minor"] == 1000 and context["paid_minor"] == 2000
    assert context["lines"][0]["quantity"] == 1 and "address_snapshot" not in context
    replay = post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        admin,
        {"expected_version": 1, "decision": "APPROVE", "reason": "original valid quantity"},
        key="approve",
    ).json()
    assert replay == decision
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        before = inv.on_hand
    attempt = post(
        client,
        "/platform/disputes/" + dispute["id"] + "/refunds",
        admin,
        {"expected_version": decision["version"]},
        expected=201,
    ).json()
    post(
        client,
        "/demo/refunds/" + attempt["id"] + "/result",
        demo,
        {
            "expected_version": attempt["version"],
            "result": "SUCCEEDED",
            "event_id": "platform-refund",
        },
    )
    with Session(engine) as db:
        inv = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A")))
        assert inv.on_hand == before + 1
    start = (clock.now() - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    end = (clock.now() + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    analytics = get(client, "/platform/analytics?start=" + start + "&end=" + end, admin)
    assert (
        analytics["payment_total_minor"] == 2000
        and analytics["refund_total_minor"] == 1000
        and analytics["net_total_minor"] == 1000
    )
    shop = get(
        client,
        "/merchant/shops/" + order["shop_id"] + "/analytics?start=" + start + "&end=" + end,
        owner,
    )
    assert shop["net_total_minor"] == 1000 and shop["simulation"]
    assert (
        client.get(
            "/api/commerce/v1/merchant/shops/"
            + str(seed_id("shop/shopB"))
            + "/analytics?start="
            + start
            + "&end="
            + end,
            headers=owner,
        ).status_code
        == 404
    )


def test_self_arbitration_timeout_and_withdraw(platform):
    client, engine, clock = platform
    customer, owner, _, order, case = rejected(client)
    admin = signin(client, "platform")
    dispute = post(
        client,
        "/customer/orders/" + order["id"] + "/after-sales/" + case["id"] + "/dispute",
        customer,
        {"expected_version": case["version"], "reason": "dispute"},
        expected=201,
    ).json()
    with Session(engine) as db:
        account = db.scalar(select(CommerceAccount).where(CommerceAccount.username == "platform"))
        db.add(
            ShopMembership(
                account_id=account.id, shop_id=UUID(order["shop_id"]), role="STAFF", active=True
            )
        )
        db.commit()
    post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        admin,
        {"expected_version": 1, "decision": "APPROVE", "reason": "conflict"},
        expected=403,
    )
    withdrawn = post(
        client,
        "/customer/disputes/" + dispute["id"] + "/withdraw",
        customer,
        {"expected_version": 1},
    ).json()
    assert withdrawn["state"] == "WITHDRAWN"
    with Session(engine) as db:
        assert db.get(Dispute, UUID(dispute["id"])).decided_by is None


def test_timeout_evidence_ownership_and_strict_inputs(platform):
    client, _, clock = platform
    customer = signin(client, "customer.a")
    other = signin(client, "customer.b")
    owner = signin(client, "owner.a")
    outsider = signin(client, "owner.b")
    demo = signin(client, "demo")
    admin = signin(client, "platform")
    order = purchase(client, customer)["orders"][0]
    pay(client, customer, demo, order["id"])
    case = make_case(client, customer, order["id"])
    base = "/customer/orders/" + order["id"] + "/after-sales/" + case["id"]
    eligible = get(client, base + "/dispute-eligibility", customer)
    assert eligible == {
        "can_dispute": False,
        "dispute_open": False,
        "reason": "DISPUTE_NOT_ELIGIBLE",
    }
    post(
        client,
        base + "/dispute",
        customer,
        {"expected_version": case["version"], "reason": "too soon"},
        expected=409,
    )
    clock.value += timedelta(hours=48)
    customer = signin(client, "customer.a")
    other = signin(client, "customer.b")
    owner = signin(client, "owner.a")
    outsider = signin(client, "owner.b")
    admin = signin(client, "platform")
    assert get(client, base + "/dispute-eligibility", customer)["can_dispute"]
    dispute = post(
        client,
        base + "/dispute",
        customer,
        {"expected_version": case["version"], "reason": "timed out"},
        expected=201,
    ).json()
    path = "/customer/disputes/" + dispute["id"] + "/evidence"
    post(client, path, other, {"expected_version": 1, "body": "not owner"}, expected=404)
    evidence = post(
        client, path, customer, {"expected_version": 1, "body": "customer evidence"}
    ).json()
    merchantpath = (
        "/merchant/shops/" + order["shop_id"] + "/disputes/" + dispute["id"] + "/evidence"
    )
    post(
        client, merchantpath, outsider, {"expected_version": 2, "body": "wrong shop"}, expected=404
    )
    evidence = post(
        client,
        merchantpath,
        owner,
        {"expected_version": evidence["version"], "body": "merchant evidence"},
    ).json()
    assert (
        evidence["customer_evidence"] == "customer evidence"
        and evidence["merchant_evidence"] == "merchant evidence"
    )
    result = post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        admin,
        {"expected_version": evidence["version"], "decision": "UPHOLD", "reason": "refusal upheld"},
    ).json()
    assert result["state"] == "UPHELD"
    for malformed in [[], {}, True]:
        post(
            client,
            "/customer/reports",
            customer,
            {"target_type": malformed, "target_id": str(seed_id("product/A")), "reason": "invalid"},
            expected=400,
        )
    post(client, "/platform/categories", admin, {"name": "x", "active": "yes"}, expected=400)
    assert (
        client.get("/api/commerce/v1/platform/accounts?limit=1&limit=2", headers=admin).status_code
        == 400
    )


def test_concurrent_disputes_one_winner_and_atomic_history(platform):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, engine, _ = platform
    customer, _, _, order, case = rejected(client)
    path = (
        "/api/commerce/v1/customer/orders/"
        + order["id"]
        + "/after-sales/"
        + case["id"]
        + "/dispute"
    )
    barrier = Barrier(2)

    def attempt(key):
        barrier.wait()
        return client.post(
            path,
            headers={**customer, "Idempotency-Key": key},
            json={"expected_version": case["version"], "reason": "concurrent"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, ["first", "second"]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    with Session(engine) as db:
        rows = list(db.scalars(select(Dispute)))
        assert len(rows) == 1
        history = db.execute(
            text(
                "SELECT count(*) FROM commerce_record_history "
                "WHERE entity_table='commerce_disputes' AND operation='INSERT'"
            )
        ).scalar_one()
        assert history == 1


def test_moderation_rollback_preserves_report_product_and_history(platform):
    client, engine, _ = platform
    customer = signin(client, "customer.a")
    admin = signin(client, "platform")
    pid = str(seed_id("product/A"))
    report = post(
        client,
        "/customer/reports",
        customer,
        {"target_type": "PRODUCT", "target_id": pid, "reason": "report"},
        expected=201,
    ).json()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_moderation() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'forced'; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_moderation BEFORE INSERT ON commerce_moderation_actions "
                "FOR EACH ROW EXECUTE FUNCTION reject_moderation()"
            )
        )
    post(
        client,
        "/platform/reports/" + report["id"] + "/decision",
        admin,
        {
            "expected_version": 1,
            "decision": "RESOLVE",
            "action": "HIDE_PRODUCT",
            "reason": "confirmed",
        },
        expected=500,
    )
    assert get(client, "/customer/reports", customer)["items"][0]["state"] == "OPEN"
    assert client.get("/api/commerce/v1/shopping/products/" + pid).status_code == 200
    with Session(engine) as db:
        count = db.execute(
            text(
                "SELECT count(*) FROM commerce_record_history "
                "WHERE entity_table='commerce_product_experiences'"
            )
        ).scalar_one()
        assert count == 0


def test_report_actual_success_timestamps_not_order_creation(platform):
    client, _, clock = platform
    customer = signin(client, "customer.a")
    demo = signin(client, "demo")
    admin = signin(client, "platform")
    order = purchase(client, customer)["orders"][0]
    created = clock.now()
    clock.value += timedelta(minutes=2)
    pay(client, customer, demo, order["id"], result="FAILED", event="failed")
    pay(client, customer, demo, order["id"], event="success")

    def report(start, end):
        from urllib.parse import urlencode

        return get(
            client,
            "/platform/analytics?"
            + urlencode({"start": start.isoformat(), "end": end.isoformat()}),
            admin,
        )

    original = report(created, created + timedelta(minutes=1))
    assert original["orders_created"] == 1 and original["payment_total_minor"] == 0
    actual = report(clock.now(), clock.now() + timedelta(days=1))
    assert actual["orders_created"] == 0 and actual["payment_total_minor"] == 2000
    assert actual["daily"][0]["payment_total_minor"] == 2000
    exclusive = report(created, clock.now())
    assert exclusive["payment_total_minor"] == 0


def test_return_arbitration_uses_original_window_without_premature_stock(platform):
    from test_commerce_step4 import deliver

    client, engine, clock = platform
    customer, owner, demo, admin = [
        signin(client, u) for u in ["customer.a", "owner.a", "demo", "platform"]
    ]
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
    deliver(client, demo, shipment, clock, "delivered-return")
    case = make_case(client, customer, order["id"], "RETURN_REFUND")
    case = post(
        client,
        case_base(order, case, True) + "/decision",
        owner,
        {"expected_version": 1, "decision": "REJECT", "reason": "refused"},
    ).json()
    clock.value += timedelta(days=15)
    customer, admin = [signin(client, u) for u in ["customer.a", "platform"]]
    dispute = post(
        client,
        "/customer/orders/" + order["id"] + "/after-sales/" + case["id"] + "/dispute",
        customer,
        {"expected_version": case["version"], "reason": "original request in window"},
        expected=201,
    ).json()
    with Session(engine) as db:
        before = db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
    approved = post(
        client,
        "/platform/disputes/" + dispute["id"] + "/decision",
        admin,
        {"expected_version": 1, "decision": "APPROVE", "reason": "original valid return"},
    ).json()
    assert approved["case_state"] == "AWAITING_RETURN" and not approved["can_refund"]
    post(
        client,
        "/platform/disputes/" + dispute["id"] + "/refunds",
        admin,
        {"expected_version": approved["version"]},
        expected=409,
    )
    with Session(engine) as db:
        assert (
            db.scalar(select(Inventory).where(Inventory.sku_id == seed_id("sku/A"))).on_hand
            == before
        )


def test_dual_role_evidence_explicit_side_and_bounded_analytics(platform):
    from urllib.parse import urlencode

    client, engine, clock = platform
    customer, owner, _, order, case = rejected(client)
    admin = signin(client, "platform")
    with Session(engine) as db:
        account = db.scalar(select(CommerceAccount).where(CommerceAccount.username == "customer.a"))
        db.add(
            ShopMembership(
                account_id=account.id, shop_id=UUID(order["shop_id"]), role="STAFF", active=True
            )
        )
        db.commit()
    dispute = post(
        client,
        "/customer/orders/" + order["id"] + "/after-sales/" + case["id"] + "/dispute",
        customer,
        {"expected_version": case["version"], "reason": "dual role"},
        expected=201,
    ).json()
    evidence = post(
        client,
        "/merchant/shops/" + order["shop_id"] + "/disputes/" + dispute["id"] + "/evidence",
        customer,
        {"expected_version": 1, "body": "merchant capacity"},
    ).json()
    assert (
        evidence["merchant_evidence"] == "merchant capacity" and evidence["customer_evidence"] == ""
    )
    query = {
        "start": (clock.now() - timedelta(days=1)).isoformat(),
        "end": (clock.now() + timedelta(days=1)).isoformat(),
        "limit": 1,
        "offset": 0,
    }
    first = get(client, "/platform/analytics?" + urlencode(query), admin)
    query["offset"] = 1
    second = get(client, "/platform/analytics?" + urlencode(query), admin)
    assert len(first["shops"]) == 1 and first["shops_has_more"]
    assert first["payment_total_minor"] == second["payment_total_minor"] == 2000
    assert first["backlog"] == second["backlog"] and first["daily"] == second["daily"]
    assert len(first["sales"]) <= 1 and len(second["sales"]) <= 1
