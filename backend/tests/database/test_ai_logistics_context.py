import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_commerce import commerce as commerce
from test_commerce import get, post, purchase, signin

from app.commerce.ai_context import logistics_snapshot
from app.commerce.ai_models import AIAttempt
from app.commerce.models import Conversation, Order, Shipment, TrackingEvent

pytestmark = pytest.mark.database


def test_linked_snapshot_stale_and_changes_during_io(commerce):
    client, engine, clock = commerce
    client.app.state.settings.deepseek_api_key = SecretStr("fictional")
    customer, merchant = signin(client, "customer.a"), signin(client, "owner.a")
    order = purchase(client, customer)["orders"][0]
    conversation = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    post(
        client,
        "/customer/conversations/" + conversation["id"] + "/messages",
        customer,
        {"body": "何时能送达？"},
        expected=201,
    )
    path = f"/merchant/shops/{order['shop_id']}/conversations/{conversation['id']}/ai-assistance"
    calls = []

    class Provider:
        def __init__(self, settings):
            pass

        def generate(self, messages, context=None):
            calls.append(context)
            if len(calls) == 2:
                with Session(engine) as db, db.begin():
                    row = db.get(Order, UUID(order["id"]))
                    row.version += 1
            return dict(
                customer_needs="查询物流",
                conditions="未明确",
                commitments="未明确承诺",
                unresolved="到达时间未知",
                draft="暂无预计到达时间，可进一步确认。",
                source_ids=context["source_ids"],
            ), []

    client.app.state.conversation_ai_provider_factory = Provider
    first = post(client, path, merchant, {}, key="first").json()
    assert not first["stale"]
    assert calls[0]["state"] == "NO_SHIPMENTS"
    assert calls[0]["order"]["id"] == order["id"]
    assert "Fictional Street" not in json.dumps(calls)
    with Session(engine) as db, db.begin():
        row = db.get(Order, UUID(order["id"]))
        row.version += 1
    assert get(client, path, merchant)["stale"]
    assert post(client, path, merchant, {}, key="during").json()["stale"]
    assert len(calls) == 2
    clock.value += timedelta(seconds=1)
    third = post(client, path, merchant, {}, key="fresh").json()
    assert not third["stale"]
    clock.value += timedelta(seconds=61)
    post(client, path, merchant, {}, key="cache")
    assert len(calls) == 3
    with Session(engine) as db:
        attempts = db.scalars(select(AIAttempt)).all()
        assert all(a.logistics_context is not None for a in attempts)


def test_bounded_legacy_and_unlinked_snapshot(commerce):
    client, engine, clock = commerce
    customer = signin(client, "customer.a")
    order = purchase(client, customer)["orders"][0]
    linked = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    unlinked = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": None},
        expected=201,
    ).json()
    with Session(engine) as db, db.begin():
        for number in range(11):
            shipment = Shipment(
                id=uuid4(),
                order_id=UUID(order["id"]),
                tracking_number=(
                    "AB 12" if number == 10 else "S7" if number == 9 else f"TRACKSECRET{number}"
                ),
                status="SHIPPED",
                simulation=True,
                shipped_at=clock.now() + timedelta(seconds=number),
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
            db.add(shipment)
            db.flush()
            for sequence in range(1, 22):
                db.add(
                    TrackingEvent(
                        id=uuid4(),
                        shipment_id=shipment.id,
                        event_id=str(uuid4()),
                        kind="SHIPPED",
                        description=(
                            "Fictional Street a@example.com TRACKSECRET10 TRACKSECRET9 AB 12 S7"
                        ),
                        occurred_at=clock.now(),
                        sequence=sequence,
                        source="SIMULATED_CARRIER",
                        status_applied=None,
                        version=1,
                        created_at=clock.now(),
                        updated_at=clock.now(),
                    )
                )
        db.flush()
        context, digest = logistics_snapshot(db, db.get(Conversation, UUID(linked["id"])))
        assert len(context["shipments"]) == 5 and context["shipments_truncated"]
        assert all(len(p["events"]) == 8 and p["events_truncated"] for p in context["shipments"])
        assert all(e["status_applied"] is None for p in context["shipments"] for e in p["events"])
        assert "Fictional Street" not in json.dumps(context)
        assert "example.com" not in json.dumps(context)
        assert "TRACKSECRET" not in json.dumps(context)
        assert "AB 12" not in json.dumps(context)
        assert "S7" not in json.dumps(context)
        excluded = db.scalar(
            select(Shipment).where(
                Shipment.order_id == UUID(order["id"]),
                Shipment.id.not_in([UUID(p["id"]) for p in context["shipments"]]),
            )
        )
        excluded.version += 1
        db.flush()
        assert logistics_snapshot(db, db.get(Conversation, UUID(linked["id"])))[1] != digest
        assert (
            logistics_snapshot(db, db.get(Conversation, UUID(unlinked["id"])))[0]["state"]
            == "NO_LINKED_ORDER"
        )
        conversation = db.get(Conversation, UUID(linked["id"]))
        conversation = SimpleNamespace(
            order_id=conversation.order_id, customer_id=uuid4(), shop_id=conversation.shop_id
        )
        with pytest.raises(Exception) as error:
            logistics_snapshot(db, conversation)
        assert "NOT_FOUND" in str(error.value)
        db.rollback()


def test_linked_real_http_redacts_known_message_and_output_secrets(commerce):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from app.commerce.ai_provider import DeepSeek

    client, engine, clock = commerce
    client.app.state.settings.deepseek_api_key = SecretStr("fictional")
    customer, merchant = signin(client, "customer.a"), signin(client, "owner.a")
    order = purchase(client, customer)["orders"][0]
    conversation = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    with Session(engine) as db, db.begin():
        db.add(
            Shipment(
                id=uuid4(),
                order_id=UUID(order["id"]),
                tracking_number="AB 12",
                status="SHIPPED",
                simulation=True,
                shipped_at=clock.now(),
                version=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
    post(
        client,
        "/customer/conversations/" + conversation["id"] + "/messages",
        customer,
        {"body": "Test Customer Fictional Street AB 12 何时送到？"},
        expected=201,
    )
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            result = dict(
                customer_needs="查询物流",
                conditions="未明确",
                commitments="未明确承诺",
                unresolved="预计到达未明确",
                draft="Test Customer Fictional Street AB 12",
                source_ids=[],
            )
            self.wfile.write(
                json.dumps(
                    {
                        "usage": {},
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": json.dumps(result)}}
                        ],
                    }
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    client.app.state.conversation_ai_provider_factory = lambda settings: DeepSeek(
        settings, endpoint=f"http://127.0.0.1:{server.server_port}"
    )
    try:
        path = (
            f"/merchant/shops/{order['shop_id']}/conversations/{conversation['id']}/ai-assistance"
        )
        result = post(client, path, merchant, {}, key="privacy-http").json()
        assert result["latest_success"]
        for secret in ["Test Customer", "Fictional Street", "AB 12"]:
            assert secret not in json.dumps(received)
            assert secret not in json.dumps(result)
    finally:
        server.shutdown()
        server.server_close()


def test_logistics_fence_retries_and_bounds_instability(commerce, monkeypatch):
    import app.commerce.ai_context as context_module
    from app.commerce.errors import CommerceError

    client, engine, _ = commerce
    customer = signin(client, "customer.a")
    order = purchase(client, customer)["orders"][0]
    conversation = post(
        client,
        "/customer/conversations",
        customer,
        {"shop_id": order["shop_id"], "order_id": order["id"]},
        expected=201,
    ).json()
    original = context_module.dependency_fence
    calls = []

    def changing(db, row):
        calls.append(1)
        if len(calls) == 2:
            with Session(engine) as writer, writer.begin():
                writer.get(Order, UUID(order["id"])).version += 1
        return original(db, row)

    monkeypatch.setattr(context_module, "dependency_fence", changing)
    with Session(engine) as db:
        row = db.get(Conversation, UUID(conversation["id"]))
        context, _ = logistics_snapshot(db, row)
        assert len(calls) == 4 and context["order"]["version"] == order["version"] + 1
        monkeypatch.setattr(context_module, "dependency_fence", lambda db, row: [uuid4()])
        with pytest.raises(CommerceError) as failure:
            logistics_snapshot(db, row)
        assert failure.value.code == "AI_BUSY"
