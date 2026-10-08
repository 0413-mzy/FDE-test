"""Manual simulated carrier transitions on real PostgreSQL, isolated per test."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_commerce import commerce as commerce
from test_commerce import get, pay, post, purchase, signin

from app.commerce.models import Shipment, TrackingEvent


def parcel(commerce):
    client, engine, clock = commerce
    customer, owner, demo = [signin(client, name) for name in ("customer.a", "owner.a", "demo")]
    oid = purchase(client, customer, {"A": 1})["order_ids"][0]
    pay(client, customer, demo, oid)
    order = get(client, "/customer/orders/" + oid, customer)
    shipment = post(
        client,
        f"/merchant/shops/{order['shop_id']}/orders/{oid}/shipments",
        owner,
        {
            "expected_version": order["version"],
            "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
        },
        expected=201,
    ).json()
    return client, engine, clock, customer, owner, demo, order, shipment


def event(client, clock, demo, shipment, kind, **extra):
    clock.value += timedelta(seconds=1)
    body = dict(
        expected_version=shipment["version"],
        event_id=str(uuid4()),
        kind=kind,
        description="Fictional simulation",
        occurred_at=clock.now().isoformat(),
        location="Fictional depot",
        reason=None,
    )
    body.update(extra)
    return client.post(
        f"/api/commerce/v1/demo/shipments/{shipment['id']}/events",
        headers=demo | {"Idempotency-Key": str(uuid4())},
        json=body,
    ), body


def advance(client, clock, demo, shipment, kinds):
    for kind in kinds:
        response, _ = event(client, clock, demo, shipment, kind)
        assert response.status_code == 200, response.text
        shipment = shipment | response.json()
    return shipment


def test_normal_stages_safe_demo_reads_and_receipt_separation(commerce):
    client, _, clock, customer, owner, demo, order, shipment = parcel(commerce)
    shipment = advance(
        client,
        clock,
        demo,
        shipment,
        ["COLLECTED", "IN_TRANSIT", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"],
    )
    detail = get(client, "/demo/shipments/" + shipment["id"], demo)
    assert detail["status"] == "DELIVERED"
    assert "order_id" not in detail and "lines" not in detail and "address" not in detail
    assert shipment["id"] in [
        s["id"] for s in get(client, "/demo/shipments?status=DELIVERED", demo)["items"]
    ]
    for headers in (customer, owner):
        assert client.get("/api/commerce/v1/demo/shipments", headers=headers).status_code == 403
    e = detail["events"][-1]
    assert (
        e["location"] == "Fictional depot"
        and e["actor_id"]
        and e["created_at"]
        and e["status_applied"] is True
    )
    current = get(client, "/customer/orders/" + order["id"], customer)
    assert current["status"] == "SHIPPED"
    merchant = get(client, f"/merchant/shops/{order['shop_id']}/orders/{order['id']}", owner)
    assert current["shipments"] == merchant["shipments"]
    assert (
        post(
            client,
            f"/customer/orders/{order['id']}/confirm-receipt",
            customer,
            {"expected_version": current["version"]},
        ).json()["status"]
        == "COMPLETED"
    )


def test_invalid_jump_and_exception_recovery(commerce):
    client, _, clock, _, _, demo, _, s = parcel(commerce)
    for kind in ["IN_TRANSIT", "DELIVERED", "OUT_FOR_DELIVERY"]:
        r, _ = event(client, clock, demo, s, kind)
        assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    s = advance(client, clock, demo, s, ["COLLECTED", "IN_TRANSIT"])
    r, _ = event(client, clock, demo, s, "EXCEPTION", reason="TRANSPORT_DELAY")
    assert r.status_code == 200, r.text
    s |= r.json()
    detail = get(client, "/demo/shipments/" + s["id"], demo)
    assert (detail["exception_reason"], detail["exception_from_status"]) == (
        "TRANSPORT_DELAY",
        "IN_TRANSIT",
    )
    r, _ = event(client, clock, demo, s, "OUT_FOR_DELIVERY")
    assert r.status_code == 409
    s = advance(client, clock, demo, s, ["IN_TRANSIT", "OUT_FOR_DELIVERY"])
    r, _ = event(client, clock, demo, s, "EXCEPTION", reason="DELIVERY_FAILED")
    assert r.status_code == 200, r.text
    s |= r.json()
    s = advance(client, clock, demo, s, ["OUT_FOR_DELIVERY", "DELIVERED"])
    r, _ = event(client, clock, demo, s, "COLLECTED")
    assert r.status_code == 409


def test_late_fact_append_only_and_no_future_stage_fabrication(commerce):
    client, engine, clock, _, _, demo, _, s = parcel(commerce)
    s = advance(client, clock, demo, s, ["COLLECTED"])
    late_time = clock.now()
    s = advance(client, clock, demo, s, ["IN_TRANSIT", "OUT_FOR_DELIVERY"])
    r, _ = event(client, clock, demo, s, "COLLECTED", occurred_at=late_time.isoformat())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OUT_FOR_DELIVERY" and r.json()["status_applied"] is False
    s |= r.json()
    for kind in ["DELIVERED", "EXCEPTION"]:
        r, _ = event(
            client,
            clock,
            demo,
            s,
            kind,
            occurred_at=late_time.isoformat(),
            reason="TRANSPORT_DELAY" if kind == "EXCEPTION" else None,
        )
        assert r.status_code == 409
    s = advance(client, clock, demo, s, ["DELIVERED"])
    r, _ = event(client, clock, demo, s, "IN_TRANSIT", occurred_at=late_time.isoformat())
    assert r.status_code == 200 and r.json()["status"] == "DELIVERED"
    with Session(engine) as db:
        row = db.get(Shipment, UUID(s["id"]))
        assert row.delivered_at is not None
        events = list(db.scalars(select(TrackingEvent).where(TrackingEvent.shipment_id == row.id)))
        assert len(events) == 7 and sum(e.status_applied is False for e in events) == 2


def test_exact_event_replay_conflict_and_concurrency(commerce):
    client, engine, clock, _, _, demo, _, s = parcel(commerce)
    clock.value += timedelta(seconds=1)
    body = dict(
        expected_version=1,
        event_id="concurrent-event",
        kind="COLLECTED",
        description="simulation",
        location="depot",
        reason=None,
        occurred_at=clock.now().isoformat(),
    )
    barrier = Barrier(2)

    def send(index):
        barrier.wait()
        return client.post(
            f"/api/commerce/v1/demo/shipments/{s['id']}/events",
            headers=demo | {"Idempotency-Key": str(index)},
            json=body,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
    r, _ = event(
        client, clock, demo, s, "COLLECTED", **{k: v for k, v in body.items() if k != "kind"}
    )
    assert r.status_code == 200 and r.json() == results[0].json()
    r, _ = event(
        client,
        clock,
        demo,
        s,
        "COLLECTED",
        **{k: v for k, v in (body | {"location": "changed"}).items() if k != "kind"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with Session(engine) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(TrackingEvent).where(TrackingEvent.shipment_id == UUID(s["id"]))
                    )
                )
            )
            == 2
        )
    s |= results[0].json()
    body |= {"expected_version": s["version"], "kind": "IN_TRANSIT"}
    barrier = Barrier(2)

    def distinct(index):
        barrier.wait()
        return client.post(
            f"/api/commerce/v1/demo/shipments/{s['id']}/events",
            headers=demo | {"Idempotency-Key": f"distinct-{index}"},
            json=body | {"event_id": f"distinct-{index}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(distinct, range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (
        next(r for r in results if r.status_code == 409).json()["error"]["code"]
        == "VERSION_CONFLICT"
    )


def test_legacy_unknown_exception_is_honest_and_recoverable(commerce):
    client, engine, clock, _, _, demo, _, s = parcel(commerce)
    with Session(engine) as db, db.begin():
        row = db.get(Shipment, UUID(s["id"]))
        row.status = "EXCEPTION"
        row.exception_reason = None
        row.exception_from_status = None
    detail = get(client, "/demo/shipments/" + s["id"], demo)
    assert detail["exception_reason"] is None
    r, _ = event(client, clock, demo, s, "IN_TRANSIT")
    assert r.status_code == 200 and r.json()["status"] == "IN_TRANSIT"


def test_tracking_permissions_and_closed_inputs(commerce):
    client, _, clock, customer, owner, demo, order, s = parcel(commerce)
    route = "/api/commerce/v1/demo/shipments/" + s["id"] + "/events"
    for headers in (customer, owner):
        assert client.post(route, headers=headers, json={}).status_code == 403
    other = signin(client, "customer.b")
    assert (
        client.get(
            f"/api/commerce/v1/customer/orders/{order['id']}/shipments/{s['id']}", headers=other
        ).status_code
        == 404
    )
    for extra in (
        {"reason": "DELIVERY_FAILED"},
        {"location": 1},
        {"unexpected": 1},
        {"reason": []},
    ):
        r, _ = event(client, clock, demo, s, "COLLECTED", **extra)
        assert r.status_code == 400
    r, _ = event(client, clock, demo, s, "EXCEPTION", reason="DELIVERY_FAILED")
    assert r.status_code == 409
    r, _ = event(
        client,
        clock,
        demo,
        s,
        "COLLECTED",
        occurred_at=(clock.now() + timedelta(days=1)).isoformat(),
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_EVENT_ORDER"
    assert (
        client.get("/api/commerce/v1/demo/shipments?status=UNKNOWN", headers=demo).status_code
        == 400
    )
    assert client.get("/api/commerce/v1/demo/shipments?limit=101", headers=demo).status_code == 400


def test_historical_original_request_still_replays(commerce):
    from app.commerce.models import SimulationEvent
    from app.commerce.service import digest

    client, engine, clock, _, _, demo, _, s = parcel(commerce)
    body = dict(
        expected_version=1,
        event_id="historical-original",
        kind="IN_TRANSIT",
        description="historical simulation",
        occurred_at=clock.now().isoformat().replace("+00:00", "Z"),
    )
    original = dict(id=s["id"], status="IN_TRANSIT", version=2, simulation=True)
    with Session(engine) as db, db.begin():
        db.add(
            SimulationEvent(
                id=uuid4(),
                source="SIMULATED_CARRIER",
                event_id=body["event_id"],
                target_id=UUID(s["id"]),
                request_hash=digest(
                    {
                        "target_id": s["id"],
                        **{
                            k: v
                            for k, v in body.items()
                            if k not in {"expected_version", "event_id"}
                        },
                    }
                ),
                response_payload=original,
                response_status=200,
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        db.add(
            TrackingEvent(
                id=uuid4(),
                shipment_id=UUID(s["id"]),
                event_id=body["event_id"],
                kind="IN_TRANSIT",
                description=body["description"],
                occurred_at=clock.now(),
                sequence=2,
                source="SIMULATED_CARRIER",
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
    response = client.post(
        f"/api/commerce/v1/demo/shipments/{s['id']}/events",
        headers=demo | {"Idempotency-Key": "historical-original"},
        json=body,
    )
    assert response.status_code == 200 and response.json() == original
    assert response.headers["Idempotent-Replay"] == "true"
    detail = get(client, "/demo/shipments/" + s["id"], demo)
    old = detail["events"][-1]
    assert (
        old["actor_id"] is None and old["status_applied"] is None and old["request_version"] is None
    )


def test_new_optional_absent_metadata_has_safe_stored_replay(commerce):
    client, _, clock, _, _, demo, _, s = parcel(commerce)
    clock.value += timedelta(seconds=1)
    body = dict(
        expected_version=1,
        event_id="optional-absent",
        kind="COLLECTED",
        description="simulation",
        occurred_at=clock.now().isoformat(),
    )
    response = client.post(
        f"/api/commerce/v1/demo/shipments/{s['id']}/events",
        headers=demo | {"Idempotency-Key": "optional-absent"},
        json=body,
    )
    assert response.status_code == 200
    detail = get(client, "/demo/shipments/" + s["id"], demo)
    event = detail["events"][-1]
    repeat = {
        key: event[key]
        for key in ["event_id", "kind", "description", "occurred_at", "location", "reason"]
    } | {"expected_version": event["request_version"]}
    replay = client.post(
        f"/api/commerce/v1/demo/shipments/{s['id']}/events",
        headers=demo | {"Idempotency-Key": "optional-repeat"},
        json=repeat,
    )
    assert replay.status_code == 200 and replay.json() == response.json()


def test_state_and_version_history_are_one_atomic_transition(commerce):
    from app.commerce.history import RecordHistory

    client, engine, clock, _, _, demo, _, s = parcel(commerce)
    r, _ = event(client, clock, demo, s, "COLLECTED")
    assert r.status_code == 200
    with Session(engine) as db:
        updates = list(
            db.scalars(
                select(RecordHistory).where(
                    RecordHistory.entity_table == "commerce_shipments",
                    RecordHistory.entity_id == UUID(s["id"]),
                    RecordHistory.operation == "UPDATE",
                )
            )
        )
        assert len(updates) == 1
        assert updates[0].before_data["version"] == 1
        assert updates[0].after_data["version"] == 2
        assert updates[0].after_data["status"] == "COLLECTED"
        assert "exception_reason" in updates[0].after_data
        inserts = list(
            db.scalars(
                select(RecordHistory).where(
                    RecordHistory.entity_table == "commerce_tracking_events"
                )
            )
        )
        assert (
            "location" in inserts[-1].after_data
            and inserts[-1].after_data["status_applied"] is True
        )
