"""Real transactions cover replay, interrupted runs, and authorization races."""

import asyncio
import inspect
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.context.collector import Collection, ProviderBundle
from app.context.recovery import recover
from app.core.clock import FixedClock
from app.core.config import Settings
from app.db.models import (
    AuditLog,
    AuthSession,
    ContextVersion,
    Inquiry,
    ResolutionRun,
    SourceFetch,
    User,
)
from app.db.seed import seed_demo
from app.integrations.errors import ExternalTimeout
from app.integrations.models import OrderSnapshot, SupportInquiry
from app.main import create_app
from app.services.resolution import Reservation, ResolutionService

pytestmark = pytest.mark.database
T0 = datetime(2026, 9, 20, 6, tzinfo=UTC)


class Providers:
    def __init__(self):
        self.calls = []
        self.hook = None
        self.failure = None

    async def get_inquiry(self, target, **kwargs):
        self.calls.append("inquiry")
        if self.hook:
            hook_result = self.hook()
            if inspect.isawaitable(hook_result):
                await hook_result
        return SupportInquiry(
            inquiry_id=target,
            external_order_id="ORD-DEMO-002",
            customer_message="Where is my order?",
            created_at=T0,
        )

    async def get_order(self, target, **kwargs):
        self.calls.append("order")
        if self.failure:
            raise self.failure
        return OrderSnapshot(
            external_order_id=target,
            customer_reference="test",
            status="PAID",
            items=[],
            created_at=T0,
            source_updated_at=T0,
            fetched_at=T0,
            source_system="demo_oms",
            source_record_id=target,
        )

    async def get_parcels(self, target, **kwargs):
        self.calls.append("parcels")
        return []

    async def get_notes(self, target, **kwargs):
        self.calls.append("notes")
        return []


@pytest.fixture
def resolution_app(database):
    engine, _, _ = database
    clock = FixedClock(T0)
    password = secrets.token_urlsafe(24)
    with Session(engine) as session, session.begin():
        seed_demo(session, clock, app_env="test", password=password)
        inquiry_id = session.scalar(
            select(Inquiry.id).where(Inquiry.external_inquiry_id == "INQ-DEMO-002")
        )
    providers = Providers()

    @asynccontextmanager
    async def factory():
        yield ProviderBundle(providers, providers, providers, providers)

    app = create_app(
        Settings(_env_file=None, app_env="test"),
        session_factory=lambda: Session(engine),
        clock=clock,
        provider_factory=factory,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "agent.a", "password": password}
        ).json()
        headers = {"Authorization": "Bearer " + login["token"], "Idempotency-Key": "resolution-one"}
        yield client, app, engine, providers, inquiry_id, headers


def resolve(client, inquiry_id, headers, version=1):
    return client.post(
        f"/api/v1/inquiries/{inquiry_id}/resolve-context",
        headers=headers,
        json={"expected_lock_version": version},
    )


def test_success_replay_history_and_order_staleness(resolution_app):
    client, app, engine, providers, inquiry_id, headers = resolution_app
    first = resolve(client, inquiry_id, headers)
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["lock_version"] == 3
    assert resolve(client, inquiry_id, headers).status_code == 200
    assert len(providers.calls) == 4
    path = f"/api/v1/inquiries/{inquiry_id}"
    assert client.get(path + "/contexts/" + result["context_id"], headers=headers).json()[
        "is_current"
    ]
    assert client.get(path + "/order", headers=headers).json()["freshness"] == "FRESH"
    app.state.clock = FixedClock(T0 + timedelta(hours=1))
    assert client.get(path + "/order", headers=headers).json()["freshness"] == "STALE"
    assert len(providers.calls) == 4
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SourceFetch)) == 4
        assert session.scalar(select(func.count()).select_from(ContextVersion)) == 1
        audits = session.scalars(
            select(AuditLog).where(
                AuditLog.event_type.in_(["RESOLVE_STARTED", "RESOLVE_SUCCEEDED"])
            )
        ).all()
        assert len(audits) == 2
        assert all(
            a.inquiry_id == inquiry_id and str(a.record_id) == result["run_id"] for a in audits
        )


@pytest.mark.parametrize(
    "change,status",
    [
        ("session", 401),
        ("role", 403),
        ("owner", 403),
        ("order", 409),
        ("owner_version", 403),
        ("order_version", 409),
        ("expired", 401),
        ("inactive", 401),
        ("team", 403),
        ("source", 409),
        ("external_inquiry", 409),
    ],
)
def test_mid_collection_changes_discard_facts(resolution_app, change, status):
    client, _, engine, providers, inquiry_id, headers = resolution_app

    def mutate():
        with Session(engine) as session, session.begin():
            inquiry = session.get(Inquiry, inquiry_id)
            if change == "session":
                session.execute(update(AuthSession).values(revoked_at=T0))
            elif change == "expired":
                session.execute(
                    update(AuthSession).values(created_at=T0 - timedelta(hours=1), expires_at=T0)
                )
            elif change == "inactive":
                session.execute(
                    update(User).where(User.id == inquiry.assigned_agent_id).values(is_active=False)
                )
            elif change == "team":
                inquiry.team_id = session.scalar(
                    select(User.team_id).where(User.username == "agent.c")
                )
            elif change == "source":
                inquiry.source_system = "other_support"
            elif change == "external_inquiry":
                inquiry.external_inquiry_id = "INQ-CHANGED"
            elif change == "role":
                session.execute(
                    update(User)
                    .where(User.id == inquiry.assigned_agent_id)
                    .values(role="ADMIN", team_id=None)
                )
            elif change in ("owner", "owner_version"):
                inquiry.assigned_agent_id = session.scalar(
                    select(User.id).where(User.username == "agent.b")
                )
            else:
                inquiry.external_order_id = "ORD-DEMO-003"
            if change.endswith("_version"):
                inquiry.lock_version += 1

    providers.hook = mutate
    response = resolve(client, inquiry_id, headers)
    assert response.status_code == status, response.text
    with Session(engine) as session:
        assert session.scalar(select(ResolutionRun.state)) == "FAILED"
        assert session.scalar(select(func.count()).select_from(SourceFetch)) == 0
        assert session.scalar(select(func.count()).select_from(ContextVersion)) == 0


def test_required_failure_replays_safe_without_calls(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    providers.failure = ExternalTimeout(service="order", operation="get_order", request_id="safe")
    first = resolve(client, inquiry_id, headers)
    assert first.status_code == 504, first.text
    assert resolve(client, inquiry_id, headers).status_code == 504
    assert providers.calls == ["inquiry", "order"]
    with Session(engine) as session:
        assert session.scalar(select(ResolutionRun.state)) == "FAILED"
        assert session.scalar(select(func.count()).select_from(ContextVersion)) == 0


def test_running_replay_busy_and_recovery_blocks_late_finish(resolution_app):
    client, app, engine, _, inquiry_id, headers = resolution_app
    with Session(engine) as session, session.begin():
        service = ResolutionService(session, app.state.clock, "test-start")
        reservation = service.start(
            headers["Authorization"],
            inquiry_id,
            b'{"expected_lock_version":1}',
            "application/json",
            [],
            ["resolution-one"],
        )
    assert isinstance(reservation, Reservation)
    replay = resolve(client, inquiry_id, headers)
    assert replay.status_code == 202
    assert replay.headers["location"].endswith(str(reservation.run_id))
    other = {**headers, "Idempotency-Key": "other"}
    assert resolve(client, inquiry_id, other, 2).json()["error"]["code"] == "BUSY"
    with Session(engine) as session, session.begin():
        operator = session.scalar(select(User.id).where(User.role == "ADMIN"))
        recovered = recover(
            session,
            app.state.clock,
            inquiry_id=inquiry_id,
            run_id=reservation.run_id,
            expected_lock_version=2,
            operator_id=operator,
        )
        assert recovered["lock_version"] == 3
    with Session(engine) as session, session.begin():
        with pytest.raises(ApiError, match="STATE_CONFLICT"):
            ResolutionService(session, app.state.clock, "late").finish(
                headers["Authorization"], reservation, Collection([], "SOURCE_TIMEOUT")
            )
    assert resolve(client, inquiry_id, headers).json()["error"]["code"] == "OPERATION_INTERRUPTED"


def test_final_audit_failure_rolls_back_all_facts_leaving_running(resolution_app):
    client, _, engine, _, inquiry_id, headers = resolution_app

    def reject_final(session, flush_context, instances):
        if any(
            isinstance(item, AuditLog) and item.event_type == "RESOLVE_SUCCEEDED"
            for item in session.new
        ):
            raise RuntimeError("private failure")

    event.listen(Session, "before_flush", reject_final)
    try:
        response = resolve(client, inquiry_id, headers)
    finally:
        event.remove(Session, "before_flush", reject_final)
    assert response.status_code == 500
    with Session(engine) as session:
        assert session.scalar(select(ResolutionRun.state)) == "RUNNING"
        assert session.get(Inquiry, inquiry_id).current_context_id is None
        assert session.scalar(select(func.count()).select_from(SourceFetch)) == 0
        assert session.scalar(select(func.count()).select_from(ContextVersion)) == 0


@pytest.mark.parametrize(
    "body,extra_headers,status",
    [
        (b'{"expected_lock_version":true}', {}, 422),
        (b'{"expected_lock_version":1,"expected_lock_version":2}', {}, 422),
        (b'{"expected_lock_version":1,"external_order_id":"foreign"}', {}, 422),
        (b'{"expected_lock_version":1}', {"Content-Type": "text/plain"}, 422),
        (b'{"expected_lock_version":1}', {"Idempotency-Key": " "}, 422),
    ],
)
def test_invalid_inputs_never_collect(resolution_app, body, extra_headers, status):
    client, _, _, providers, inquiry_id, headers = resolution_app
    response = client.post(
        f"/api/v1/inquiries/{inquiry_id}/resolve-context",
        headers={"Content-Type": "application/json", **headers, **extra_headers},
        content=body,
    )
    assert response.status_code == status
    assert providers.calls == []


def test_unauthorized_precedes_input_and_no_network(resolution_app):
    client, _, _, providers, _, headers = resolution_app
    response = client.post(
        f"/api/v1/inquiries/{uuid4()}/resolve-context?order_id=foreign",
        headers=headers,
        content=b"invalid",
    )
    assert response.status_code == 403
    assert providers.calls == []


def test_historical_context_is_preserved_and_foreign_chain_rejected(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    first = resolve(client, inquiry_id, headers).json()
    second = resolve(client, inquiry_id, {**headers, "Idempotency-Key": "two"}, 3)
    assert second.status_code == 201, second.text
    path = f"/api/v1/inquiries/{inquiry_id}"
    old = client.get(path + "/contexts/" + first["context_id"], headers=headers)
    assert old.status_code == 200 and old.json()["is_current"] is False
    assert client.get(path + "/contexts/" + str(uuid4()), headers=headers).status_code == 404
    assert client.get(path + "/runs/" + str(uuid4()), headers=headers).status_code == 404
    # Deliberately corrupt the mutable run association to simulate stored-chain damage.
    with Session(engine) as session, session.begin():
        run = session.get(ResolutionRun, UUID(second.json()["run_id"]))
        run.inquiry_id = session.scalar(
            select(Inquiry.id).where(Inquiry.external_inquiry_id == "INQ-DEMO-003")
        )
    assert client.get(path + "/order", headers=headers).status_code == 409
    assert len(providers.calls) == 8


def test_unexpected_provider_exception_leaves_recoverable_running(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    providers.failure = RuntimeError("private provider body")
    response = resolve(client, inquiry_id, headers)
    assert response.status_code == 500 and "private provider body" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(ResolutionRun.state)) == "RUNNING"
        assert session.scalar(select(func.count()).select_from(SourceFetch)) == 0


def test_recovery_requires_active_admin_and_exact_version(resolution_app):
    _, app, engine, _, inquiry_id, headers = resolution_app
    with Session(engine) as session, session.begin():
        reservation = ResolutionService(session, app.state.clock, "start").start(
            headers["Authorization"],
            inquiry_id,
            b'{"expected_lock_version":1}',
            "application/json",
            [],
            ["one"],
        )
    with Session(engine) as session, session.begin():
        agent = session.scalar(select(User.id).where(User.username == "agent.a"))
        admin = session.scalar(select(User.id).where(User.role == "ADMIN"))
        with pytest.raises(ApiError, match="FORBIDDEN"):
            recover(
                session,
                app.state.clock,
                inquiry_id=inquiry_id,
                run_id=reservation.run_id,
                expected_lock_version=2,
                operator_id=agent,
            )
        with pytest.raises(ApiError, match="VERSION_CONFLICT"):
            recover(
                session,
                app.state.clock,
                inquiry_id=inquiry_id,
                run_id=reservation.run_id,
                expected_lock_version=1,
                operator_id=admin,
            )
        assert session.get(ResolutionRun, reservation.run_id).state == "RUNNING"


def test_idempotency_version_and_failed_current_clearing(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    first = resolve(client, inquiry_id, headers).json()
    assert resolve(client, inquiry_id, headers, 3).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    other = {**headers, "Idempotency-Key": "two"}
    assert resolve(client, inquiry_id, other, 1).json()["error"]["code"] == "VERSION_CONFLICT"
    providers.failure = ExternalTimeout(service="order", operation="get_order", request_id="safe")
    assert resolve(client, inquiry_id, other, 3).status_code == 504
    path = f"/api/v1/inquiries/{inquiry_id}"
    assert client.get(path + "/order", headers=headers).status_code == 409
    assert (
        client.get(path + "/contexts/" + first["context_id"], headers=headers).json()["is_current"]
        is False
    )
    with Session(engine) as session:
        inquiry = session.get(Inquiry, inquiry_id)
        assert inquiry.current_context_id is None and inquiry.current_draft_id is None
        assert inquiry.lock_version == 5


def test_missing_order_and_terminal_state_never_fetch(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    with Session(engine) as session, session.begin():
        inquiry = session.get(Inquiry, inquiry_id)
        inquiry.external_order_id = None
    assert resolve(client, inquiry_id, headers).status_code == 422
    with Session(engine) as session, session.begin():
        inquiry = session.get(Inquiry, inquiry_id)
        inquiry.external_order_id = "ORD-DEMO-002"
        inquiry.state = "APPROVED"
    assert resolve(client, inquiry_id, headers).json()["error"]["code"] == "STATE_CONFLICT"
    assert providers.calls == []


def test_simultaneous_same_key_replays_committed_reservation(resolution_app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client, _, engine, providers, inquiry_id, headers = resolution_app
    entered, release = Event(), Event()

    async def pause_provider():
        entered.set()
        assert await asyncio.to_thread(release.wait, 10)

    providers.hook = pause_provider
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(resolve, client, inquiry_id, headers)
        try:
            assert entered.wait(5)
            replay = workers.submit(resolve, client, inquiry_id, headers).result(timeout=5)
            assert replay.status_code == 202, replay.text
            with Session(engine) as session:
                assert session.scalar(select(func.count()).select_from(ResolutionRun)) == 1
                assert session.get(Inquiry, inquiry_id).lock_version == 2
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 201
    assert len(providers.calls) == 4


def test_rejected_resolve_audit_is_attributable_and_contains_only_fixed_code(resolution_app):
    client, _, engine, providers, inquiry_id, headers = resolution_app
    malformed = client.post(
        f"/api/v1/inquiries/{inquiry_id}/resolve-context",
        headers=headers,
        json={"expected_lock_version": True, "private": "untrusted"},
    )
    assert malformed.status_code == 422
    assert resolve(client, inquiry_id, headers, 9).status_code == 409
    with Session(engine) as session:
        events = session.scalars(
            select(AuditLog).where(AuditLog.event_type == "RESOLVE_FAILED").order_by(AuditLog.id)
        ).all()
        actor = session.scalar(select(User.id).where(User.username == "agent.a"))
        assert len(events) == 2
        assert all(
            a.inquiry_id == inquiry_id and a.actor_id == actor and a.record_id is None
            for a in events
        )
        assert {a.safe_metadata["error_code"] for a in events} == {
            "INVALID_REQUEST",
            "VERSION_CONFLICT",
        }
        assert all(
            set(a.safe_metadata) == {"error_code", "rejected"}
            and a.safe_metadata["rejected"] is True
            for a in events
        )
        assert session.scalar(select(func.count()).select_from(ResolutionRun)) == 0
        assert session.get(Inquiry, inquiry_id).lock_version == 1
    assert providers.calls == []


def test_supervisor_resolves_same_team_without_assignment(resolution_app):
    from app.core.security import new_token, token_digest

    client, app, engine, _, inquiry_id, _ = resolution_app
    token = new_token()
    with Session(engine) as session, session.begin():
        supervisor = session.scalar(select(User).where(User.role == "SUPERVISOR"))
        inquiry = session.get(Inquiry, inquiry_id)
        assert supervisor.team_id == inquiry.team_id and supervisor.id != inquiry.assigned_agent_id
        session.add(
            AuthSession(
                user_id=supervisor.id,
                token_digest=token_digest(token),
                created_at=T0,
                expires_at=T0 + timedelta(hours=8),
            )
        )
    response = resolve(
        client, inquiry_id, {"Authorization": "Bearer " + token, "Idempotency-Key": "supervisor"}
    )
    assert response.status_code == 201, response.text


def test_recovery_rejects_inactive_operator_wrong_association_and_finished_run(resolution_app):
    client, app, engine, _, inquiry_id, headers = resolution_app
    result = resolve(client, inquiry_id, headers).json()
    with Session(engine) as session, session.begin():
        admin = session.scalar(select(User).where(User.role == "ADMIN"))
        foreign = session.scalar(
            select(Inquiry.id).where(Inquiry.external_inquiry_id == "INQ-DEMO-003")
        )
        with pytest.raises(ApiError, match="RESOURCE_NOT_FOUND"):
            recover(
                session,
                app.state.clock,
                inquiry_id=foreign,
                run_id=UUID(result["run_id"]),
                expected_lock_version=1,
                operator_id=admin.id,
            )
        with pytest.raises(ApiError, match="STATE_CONFLICT"):
            recover(
                session,
                app.state.clock,
                inquiry_id=inquiry_id,
                run_id=UUID(result["run_id"]),
                expected_lock_version=3,
                operator_id=admin.id,
            )
        admin.is_active = False
        session.flush()
        with pytest.raises(ApiError, match="FORBIDDEN"):
            recover(
                session,
                app.state.clock,
                inquiry_id=inquiry_id,
                run_id=UUID(result["run_id"]),
                expected_lock_version=3,
                operator_id=admin.id,
            )
