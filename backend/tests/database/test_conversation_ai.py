from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commerce.ai_models import AIAttempt
from app.commerce.ai_provider import ProviderFailure
from app.commerce.models import Shop
from app.commerce.seed import seed_commerce
from app.core.config import Settings
from app.main import create_app

PASSWORD = "test-commerce-secret-123"


class Clock:
    def now(self):
        return datetime.now(UTC)


def test_persistence_auth_cache_stale_failure(database):
    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
        shops = db.scalars(select(Shop).order_by(Shop.name)).all()
        shop = str(shops[0].id)
    app = create_app(
        Settings(app_env="test", deepseek_api_key="fictional"),
        session_factory=lambda: Session(engine),
        clock=clock,
    )
    calls = []

    class Provider:
        def __init__(self, settings):
            pass

        def generate(self, messages):
            calls.append(messages)
            if len(calls) > 1:
                raise ProviderFailure("AI_TIMEOUT", [{"prompt_tokens": 2}])
            return dict(
                customer_needs="咨询",
                conditions="未明确",
                commitments="未明确",
                unresolved="待回答",
                draft="您好，请具体说明",
                source_ids=[messages[0]["id"]],
            ), [{"prompt_tokens": 10}]

    app.state.conversation_ai_provider_factory = Provider
    with TestClient(app) as client:

        def login(name):
            r = client.post(
                "/api/commerce/v1/auth/login", json={"username": name, "password": PASSWORD}
            )
            assert r.status_code == 200, r.text
            return {"Authorization": "Bearer " + r.json()["token"], "Idempotency-Key": "one"}

        customer = login("customer.a")
        c = client.post(
            "/api/commerce/v1/customer/conversations",
            headers=customer,
            json={"shop_id": shop, "order_id": None},
        )
        assert c.status_code in (200, 201), c.text
        cid = c.json()["id"]
        msg = f"/api/commerce/v1/customer/conversations/{cid}/messages"
        assert (
            client.post(
                msg, headers={**customer, "Idempotency-Key": "message1"}, json={"body": "咨询商品"}
            ).status_code
            == 201
        )
        merchant = login("owner.a")
        own = client.get("/api/commerce/v1/merchant/shops", headers=merchant).json()["items"]
        shop = own[0]["shop_id"]
        path = f"/api/commerce/v1/merchant/shops/{shop}/conversations/{cid}/ai-assistance"
        assert client.get(path, headers=customer).status_code == 403
        first = client.post(path, headers=merchant, json={})
        assert first.status_code == 200, first.text
        assert first.json()["latest_success"]["message_count"] == 1
        assert client.post(path, headers=merchant, json={}).headers["Idempotent-Replay"] == "true"
        assert len(calls) == 1
        cached = client.post(path, headers={**merchant, "Idempotency-Key": "cached"}, json={})
        assert cached.headers["Idempotent-Replay"] == "true"
        assert len(calls) == 1
        assert (
            client.post(
                msg,
                headers={**customer, "Idempotency-Key": "message2"},
                json={"body": "还有一个问题"},
            ).status_code
            == 201
        )
        assert client.get(path, headers=merchant).json()["stale"]
        failed = client.post(path, headers={**merchant, "Idempotency-Key": "two"}, json={})
        assert failed.json()["latest_attempt"]["state"] == "FAILED"
        assert failed.json()["latest_success"]["id"] == cached.json()["latest_success"]["id"]
        assert client.post(path, headers=merchant, json={}).status_code == 409
        assert (
            client.post(
                path, headers={**merchant, "Idempotency-Key": "cached"}, json={}
            ).status_code
            == 409
        )
        assert (
            client.post(
                path, headers={**merchant, "Idempotency-Key": "bad"}, json={"messages": []}
            ).status_code
            == 400
        )
    with Session(engine) as db:
        rows = db.scalars(select(AIAttempt).where(AIAttempt.conversation_id == UUID(cid))).all()
        assert len(rows) == 3 and any(r.usage for r in rows if r.state == "FAILED")


def test_running_lease_recovery_and_authority_recheck(database):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    from sqlalchemy import update

    from app.commerce.models import ShopMembership
    from app.commerce.seed import seed_id

    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    app = create_app(
        Settings(app_env="test", deepseek_api_key="fictional"),
        session_factory=lambda: Session(engine),
        clock=clock,
    )
    entered, release = Event(), Event()
    calls = []

    class Provider:
        def __init__(self, settings):
            pass

        def generate(self, messages):
            calls.append(messages)
            entered.set()
            assert release.wait(10)
            return dict(
                customer_needs="需求",
                conditions="未明确",
                commitments="未明确",
                unresolved="问题",
                draft="可进一步确认",
                source_ids=[messages[0]["id"]],
            ), [{"prompt_tokens": 4}]

    app.state.conversation_ai_provider_factory = Provider
    with TestClient(app) as client:

        def login(name):
            r = client.post(
                "/api/commerce/v1/auth/login", json={"username": name, "password": PASSWORD}
            )
            return {"Authorization": "Bearer " + r.json()["token"], "Idempotency-Key": "one"}

        customer, merchant = login("customer.a"), login("owner.a")
        cid = client.post(
            "/api/commerce/v1/customer/conversations",
            headers=customer,
            json={"shop_id": str(seed_id("shop/shopA")), "order_id": None},
        ).json()["id"]
        msg = f"/api/commerce/v1/customer/conversations/{cid}/messages"
        client.post(msg, headers={**customer, "Idempotency-Key": "msg"}, json={"body": "询问"})
        shop_id = seed_id("shop/shopA")
        path = f"/api/commerce/v1/merchant/shops/{shop_id}/conversations/{cid}/ai-assistance"
        other = login("owner.b")
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path, headers=login("demo")).status_code == 403
        with ThreadPoolExecutor() as pool:
            first = pool.submit(client.post, path, headers=merchant, json={})
            assert entered.wait(5)
            running = client.get(path, headers=merchant).json()
            assert running["latest_attempt"]["state"] == "RUNNING"
            assert (
                client.post(
                    path, headers={**merchant, "Idempotency-Key": "parallel"}, json={}
                ).status_code
                == 409
            )
            assert (
                client.post(path, headers=merchant, json={}).headers["Idempotent-Replay"] == "true"
            )
            # Membership writes are not blocked during provider I/O; authority must be rechecked.
            with Session(engine) as db, db.begin():
                db.execute(
                    update(ShopMembership)
                    .where(ShopMembership.account_id == seed_id("account/owner.a"))
                    .values(active=False)
                )
            release.set()
            assert first.result().status_code == 403
        assert len(calls) == 1
        with Session(engine) as db, db.begin():
            db.execute(
                update(ShopMembership)
                .where(ShopMembership.account_id == seed_id("account/owner.a"))
                .values(active=True)
            )
            old = db.scalar(select(AIAttempt))
            old.state = "RUNNING"
            old.lease_until = clock.now() - timedelta(seconds=1)
            old.result = None
        recovered_view = client.get(path, headers=merchant).json()
        assert recovered_view["latest_attempt"]["state"] == "FAILED"
        recovered = client.post(
            path, headers={**merchant, "Idempotency-Key": "recover"}, content=b" { } "
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["latest_success"]["state"] == "SUCCEEDED"
        assert len(calls) == 2


def test_additive_migration_preserves_rows_and_durable_limits(database):
    from alembic import command
    from sqlalchemy import func

    from app.commerce.models import CommerceAccount, Message
    from app.commerce.seed import seed_id

    engine, config, _ = database
    command.downgrade(config, "0008_commerce_platform")
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
        ids = set(db.scalars(select(CommerceAccount.id)))
    command.upgrade(config, "head")
    with Session(engine) as db:
        assert set(db.scalars(select(CommerceAccount.id))) == ids
    app = create_app(
        Settings(app_env="test", deepseek_api_key=None),
        session_factory=lambda: Session(engine),
        clock=clock,
    )

    class Failure:
        def __init__(self, settings):
            pass

        def generate(self, messages):
            raise ProviderFailure("AI_TIMEOUT", [])

    app.state.conversation_ai_provider_factory = Failure
    with TestClient(app) as client:

        def login(name):
            r = client.post(
                "/api/commerce/v1/auth/login", json={"username": name, "password": PASSWORD}
            )
            return {"Authorization": "Bearer " + r.json()["token"], "Idempotency-Key": "one"}

        customer, merchant = login("customer.a"), login("owner.a")
        shop = seed_id("shop/shopA")
        cid = client.post(
            "/api/commerce/v1/customer/conversations",
            headers=customer,
            json={"shop_id": str(shop), "order_id": None},
        ).json()["id"]
        path = f"/api/commerce/v1/merchant/shops/{shop}/conversations/{cid}/ai-assistance"
        assert client.get(path, headers=merchant).json()["available"] is False
        assert client.post(path, headers=merchant, json={}).status_code == 503
        app.state.settings.deepseek_api_key = Settings(
            deepseek_api_key="fictional"
        ).deepseek_api_key
        assert client.post(path, headers=merchant, json={}).status_code == 400
        client.post(
            f"/api/commerce/v1/customer/conversations/{cid}/messages",
            headers=customer,
            json={"body": "一个问题"},
        )
        for i in range(3):
            assert (
                client.post(
                    path, headers={**merchant, "Idempotency-Key": f"fail{i}"}, json={}
                ).json()["latest_attempt"]["state"]
                == "FAILED"
            )
        # A reconstructed app with the same database still observes the account quota.
        app2 = create_app(app.state.settings, session_factory=lambda: Session(engine), clock=clock)
        app2.state.conversation_ai_provider_factory = Failure
        with TestClient(app2) as other:
            assert (
                other.post(
                    path, headers={**merchant, "Idempotency-Key": "over-limit"}, json={}
                ).status_code
                == 429
            )
        from uuid import uuid4

        with Session(engine) as db, db.begin():
            original = db.scalar(select(AIAttempt).limit(1))
            for i in range(17):
                db.add(
                    AIAttempt(
                        id=uuid4(),
                        actor_id=seed_id("account/owner.b"),
                        conversation_id=original.conversation_id,
                        idempotency_key=f"global-{i}",
                        snapshot_hash=original.snapshot_hash,
                        source_ids=original.source_ids,
                        message_count=1,
                        model=original.model,
                        prompt_version=original.prompt_version,
                        state="FAILED",
                        lease_until=clock.now(),
                        created_at=clock.now(),
                        finished_at=clock.now(),
                        usage=[],
                        error_code="AI_TIMEOUT",
                    )
                )
        staff = login("staff.a")
        with TestClient(app2) as other:
            assert other.post(path, headers=staff, json={}).status_code == 429
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Message)) == 1


def test_fresh_cache_keys_are_bounded_but_exact_replay_and_other_actor_work(database):
    from sqlalchemy import func

    from app.commerce.seed import seed_id

    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    app = create_app(
        Settings(app_env="test", deepseek_api_key="fictional"),
        session_factory=lambda: Session(engine),
        clock=clock,
    )
    calls = []

    class Provider:
        def __init__(self, settings):
            pass

        def generate(self, messages):
            calls.append(messages)
            return dict(
                customer_needs="问题",
                conditions="未明确",
                commitments="未明确承诺",
                unresolved="待确认",
                draft="可进一步确认",
                source_ids=[messages[0]["id"]],
            ), [{"prompt_tokens": 4}]

    app.state.conversation_ai_provider_factory = Provider
    with TestClient(app) as client:

        def login(name):
            r = client.post(
                "/api/commerce/v1/auth/login", json={"username": name, "password": PASSWORD}
            )
            return {"Authorization": "Bearer " + r.json()["token"], "Idempotency-Key": "one"}

        customer, merchant, staff = login("customer.a"), login("owner.a"), login("staff.a")
        shop = seed_id("shop/shopA")
        cid = client.post(
            "/api/commerce/v1/customer/conversations",
            headers=customer,
            json={"shop_id": str(shop), "order_id": None},
        ).json()["id"]
        msg = f"/api/commerce/v1/customer/conversations/{cid}/messages"
        client.post(msg, headers=customer, json={"body": "问题"})
        path = f"/api/commerce/v1/merchant/shops/{shop}/conversations/{cid}/ai-assistance"
        assert client.post(path, headers=merchant, json={}).status_code == 200
        for key in ("cache-1", "cache-2"):
            assert (
                client.post(path, headers={**merchant, "Idempotency-Key": key}, json={}).status_code
                == 200
            )
        for i in range(25):
            assert (
                client.post(
                    path, headers={**merchant, "Idempotency-Key": f"excess-{i}"}, json={}
                ).status_code
                == 429
            )
        assert client.post(path, headers=merchant, json={}).headers["Idempotent-Replay"] == "true"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(AIAttempt)) == 3
        assert len(calls) == 1
        client.post(
            msg, headers={**customer, "Idempotency-Key": "new-message"}, json={"body": "另一问题"}
        )
        assert client.post(path, headers=staff, json={}).status_code == 200
        assert len(calls) == 2
        from uuid import uuid4

        with Session(engine) as db, db.begin():
            original = db.scalar(
                select(AIAttempt).where(AIAttempt.actor_id == seed_id("account/staff.a"))
            )
            for i in range(16):
                db.add(
                    AIAttempt(
                        id=uuid4(),
                        actor_id=seed_id("account/owner.b"),
                        conversation_id=original.conversation_id,
                        idempotency_key=f"global-cache-limit-{i}",
                        snapshot_hash=original.snapshot_hash,
                        source_ids=original.source_ids,
                        message_count=original.message_count,
                        model=original.model,
                        prompt_version=original.prompt_version,
                        state="FAILED",
                        lease_until=clock.now(),
                        created_at=clock.now(),
                        finished_at=clock.now(),
                        usage=[],
                        error_code="AI_TIMEOUT",
                    )
                )
        # A third merchant with no own requests cannot insert a cache reservation at global20.
        assert client.post(path, headers=login("dual.a"), json={}).status_code == 429
        assert client.post(path, headers=staff, json={}).headers["Idempotent-Replay"] == "true"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(AIAttempt)) == 20
        assert len(calls) == 2
