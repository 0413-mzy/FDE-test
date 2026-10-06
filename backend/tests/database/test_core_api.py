import base64
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.security import token_digest
from app.db.models import AuditLog, AuthSession, Inquiry, Team, User
from app.db.seed import seed_demo
from app.integrations.sandbox.providers import (
    SandboxLogisticsProvider,
    SandboxMessageProvider,
    SandboxOrderProvider,
    SandboxWarehouseProvider,
)
from app.main import create_app
from app.services.core_access import CoreAccess

pytestmark = pytest.mark.database
T0 = datetime(2026, 9, 20, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Stage 3 must never invoke a Provider")

    for provider, methods in (
        (SandboxOrderProvider, ("get_order", "get_parcels")),
        (SandboxLogisticsProvider, ("get_shipment",)),
        (SandboxWarehouseProvider, ("get_notes",)),
        (SandboxMessageProvider, ("get_inquiry", "send_reply")),
    ):
        for method in methods:
            monkeypatch.setattr(provider, method, forbidden_call)
    yield
    assert calls == []


@pytest.fixture
def access_app(database):
    engine, _, _ = database
    password = secrets.token_urlsafe(24)
    with Session(engine) as session, session.begin():
        seed_demo(session, FixedClock(T0), app_env="test", password=password)
        ids = {record.external_inquiry_id: record.id for record in session.scalars(select(Inquiry))}
    application = create_app(
        Settings(_env_file=None, app_env="test", cors_allowed_origins=["http://localhost:5173"]),
        session_factory=lambda: Session(engine),
        clock=FixedClock(T0),
    )
    with TestClient(application) as client:
        yield client, application, engine, password, ids


def sign_in(client, password, username="agent.a"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"X-Request-Id": "req-api-login"},
    )
    assert response.status_code == 200, response.text
    return response, {"Authorization": "Bearer " + response.json()["token"]}


def test_main_database_upgrade_preserves_live_session_and_inquiry_permissions(access_app, database):
    client, _, engine, password, ids = access_app
    _, migrations, _ = database
    command.downgrade(migrations, "0001_core_mvp")
    login, headers = sign_in(client, password)
    with Session(engine) as session:
        digest = token_digest(login.json()["token"])
        before = session.scalar(select(AuthSession).where(AuthSession.token_digest == digest))
        session_id, expires_at = before.id, before.expires_at

    command.upgrade(migrations, "head")

    with Session(engine) as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
            ScriptDirectory.from_config(migrations).get_current_head()
        )
        after = session.get(AuthSession, session_id)
        assert after.token_digest == digest and after.expires_at == expires_at
    assert client.get("/api/v1/auth/me", headers=headers).json() == login.json()["user"]
    listing = client.get("/api/v1/inquiries", headers=headers)
    assert listing.status_code == 200 and listing.json()["total"] == 10
    assert {item["id"] for item in listing.json()["items"]} == {
        str(value) for key, value in ids.items() if int(key[-3:]) <= 10
    }
    own = f"/api/v1/inquiries/{ids['INQ-DEMO-002']}"
    assert client.get(own, headers=headers).status_code == 200
    for external_id in ("INQ-DEMO-011", "INQ-DEMO-012"):
        assert (
            client.get(f"/api/v1/inquiries/{ids[external_id]}", headers=headers).status_code == 403
        )
    order = client.get(own + "/order", headers=headers)
    assert order.status_code == 409 and order.json()["error"]["code"] == "CONTEXT_REQUIRED"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    sign_in(client, password)


def test_login_stores_only_digest_and_safe_audit_with_fixed_expiry(access_app, caplog):
    client, _, engine, password, _ = access_app
    response, headers = sign_in(client, password)
    payload = response.json()
    token = payload["token"]
    assert len(base64.urlsafe_b64decode(token + "=")) == 32
    assert payload["expires_at"] == "2026-09-20T14:00:00Z"
    assert payload["token_type"] == "Bearer"
    assert set(payload["user"]) == {"id", "username", "role", "team_id"}
    assert response.headers["cache-control"] == "no-store"
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200 and me.json() == payload["user"]
    with Session(engine) as session:
        auth = session.scalar(select(AuthSession))
        audit = session.scalar(select(AuditLog))
        assert auth.token_digest == token_digest(token)
        assert auth.created_at == T0 and auth.expires_at == T0 + timedelta(hours=8)
        assert audit.event_type == "LOGIN_SUCCESS" and audit.actor_id == auth.user_id
        assert audit.occurred_at == T0 and audit.safe_metadata == {}
        assert token not in str(auth.__dict__) + str(audit.__dict__)
    assert token not in caplog.text and password not in response.text + caplog.text


@pytest.mark.parametrize("mode", ["unknown", "wrong_password", "inactive", "corrupt_hash"])
def test_login_failures_have_same_envelope_no_session_and_persist_safe_audit(access_app, mode):
    client, _, engine, password, _ = access_app
    if mode in {"inactive", "corrupt_hash"}:
        with Session(engine) as session, session.begin():
            user = session.scalar(select(User).where(User.username == "agent.a"))
            if mode == "inactive":
                user.is_active = False
            else:
                user.password_hash = "corrupt hash"
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Request-Id": "req-failure"},
        json={
            "username": "unknown.user" if mode == "unknown" else "agent.a",
            "password": secrets.token_urlsafe(24) if mode == "wrong_password" else password,
        },
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTHENTICATION_FAILED",
            "message": "用户名或密码无效。",
            "request_id": "req-failure",
            "details": {},
        }
    }
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0
        audit = session.scalar(select(AuditLog))
        assert audit.event_type == "LOGIN_FAILED" and audit.actor_id is None
        assert audit.safe_metadata == {"error_code": "AUTHENTICATION_FAILED"}
        assert password not in str(audit.__dict__)


def test_logout_revokes_only_current_session_and_is_atomic(access_app):
    client, application, engine, password, _ = access_app
    first, header1 = sign_in(client, password)
    _, header2 = sign_in(client, password)
    application.state.clock = FixedClock(T0 + timedelta(hours=1))
    response = client.post("/api/v1/auth/logout", headers=header1)
    assert response.status_code == 204 and response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/auth/me", headers=header1).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=header1).status_code == 401
    assert client.get("/api/v1/auth/me", headers=header2).status_code == 200
    with Session(engine) as session:
        auth = session.scalar(
            select(AuthSession).where(
                AuthSession.token_digest == token_digest(first.json()["token"])
            )
        )
        assert auth.revoked_at == T0 + timedelta(hours=1)
        assert (
            session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.event_type == "LOGOUT")
            )
            == 1
        )


def test_expiry_is_exact_and_does_not_slide(access_app):
    client, application, engine, password, _ = access_app
    _, headers = sign_in(client, password)
    application.state.clock = FixedClock(T0 + timedelta(hours=8) - timedelta(microseconds=1))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    application.state.clock = FixedClock(T0 + timedelta(hours=8))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    with Session(engine) as session:
        assert session.scalar(select(AuthSession)).expires_at == T0 + timedelta(hours=8)


@pytest.mark.parametrize("change", ["inactive", "team", "admin"])
def test_every_request_uses_current_identity_role_and_team(access_app, change):
    client, _, engine, password, ids = access_app
    _, headers = sign_in(client, password)
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.username == "agent.a"))
        if change == "inactive":
            user.is_active = False
        elif change == "team":
            user.team_id = session.scalar(select(Team.id).where(Team.code == "DEMO-TEAM-2"))
        else:
            user.role = "ADMIN"
            user.team_id = None
    detail = client.get(f"/api/v1/inquiries/{ids['INQ-DEMO-002']}", headers=headers)
    assert detail.status_code == (401 if change == "inactive" else 403)
    if change != "inactive":
        listing = client.get("/api/v1/inquiries", headers=headers)
        assert listing.json()["items"] == [] and listing.json()["total"] == 0


@pytest.mark.parametrize(
    "username,total",
    [
        ("agent.a", 10),
        ("agent.b", 1),
        ("agent.c", 1),
        ("supervisor", 11),
        ("admin", 0),
    ],
)
def test_permission_filtered_list_has_stable_pagination_and_minimal_fields(
    access_app, username, total
):
    client, _, _, password, ids = access_app
    _, headers = sign_in(client, password, username)
    response = client.get("/api/v1/inquiries?limit=2&offset=0", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == total and payload["limit"] == 2 and payload["offset"] == 0
    values = [item["id"] for item in payload["items"]]
    assert values == sorted(values, reverse=True)
    for item in payload["items"]:
        assert "escalation_reason" not in item and "question" not in item
        assert "team_id" not in item and "assigned_agent_id" not in item
    if username == "agent.a":
        allowed = {str(value) for key, value in ids.items() if int(key[-3:]) <= 10}
        all_items = client.get("/api/v1/inquiries?limit=100", headers=headers).json()["items"]
        assert {item["id"] for item in all_items} == allowed
        second = client.get("/api/v1/inquiries?limit=2&offset=2", headers=headers).json()["items"]
        assert not set(values) & {item["id"] for item in second}
        assert client.get("/api/v1/inquiries?offset=100", headers=headers).json()["items"] == []


@pytest.mark.parametrize(
    "username,external_id,status",
    [
        ("agent.a", "INQ-DEMO-002", 200),
        ("agent.a", "INQ-DEMO-011", 403),
        ("agent.a", "INQ-DEMO-012", 403),
        ("supervisor", "INQ-DEMO-011", 200),
        ("supervisor", "INQ-DEMO-012", 403),
        ("admin", "INQ-DEMO-002", 403),
    ],
)
def test_detail_ownership_checks_before_disclosing_business_data(
    access_app, username, external_id, status
):
    client, _, _, password, ids = access_app
    _, headers = sign_in(client, password, username)
    response = client.get(f"/api/v1/inquiries/{ids[external_id]}", headers=headers)
    assert response.status_code == status
    if status == 200:
        assert response.json()["external_inquiry_id"] == external_id
        assert response.json()["escalation_reason"] is None
        assert "customer_message" not in response.json()
    else:
        assert external_id not in response.text and str(ids[external_id]) not in response.text


def test_unknown_and_forbidden_inquiries_are_indistinguishable_and_safely_audited(access_app):
    client, _, engine, password, ids = access_app
    _, headers = sign_in(client, password)
    headers["X-Request-Id"] = "req-same-denial"
    replies = [
        client.get(f"/api/v1/inquiries/{identity}?role=ADMIN", headers=headers)
        for identity in (ids["INQ-DEMO-011"], ids["INQ-DEMO-012"], uuid4())
    ]
    assert all(response.status_code == 403 for response in replies)
    assert all(response.json() == replies[0].json() for response in replies)
    with Session(engine) as session:
        denials = session.scalars(
            select(AuditLog).where(AuditLog.event_type == "ACCESS_DENIED")
        ).all()
        assert len(denials) == 3
        assert all(row.inquiry_id is None and row.record_id is None for row in denials)
        assert all(row.safe_metadata == {"error_code": "FORBIDDEN"} for row in denials)


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "limit=true",
        "limit=1.0",
        "limit=1&limit=2",
        "role=ADMIN",
    ],
)
def test_closed_query_validation_follows_authentication(access_app, query):
    client, _, _, password, _ = access_app
    invalid_token = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    assert client.get("/api/v1/inquiries?" + query, headers=invalid_token).status_code == 401
    _, headers = sign_in(client, password)
    assert client.get("/api/v1/inquiries?" + query, headers=headers).status_code == 422


def test_body_and_path_validation_follow_identity_without_changing_state(access_app):
    client, _, engine, password, ids = access_app
    _, headers = sign_in(client, password)
    assert client.get("/api/v1/inquiries/invalid", headers=headers).status_code == 422
    path = f"/api/v1/inquiries/{ids['INQ-DEMO-002']}"
    assert client.request("GET", path, headers=headers, json={"role": "ADMIN"}).status_code == 422
    assert client.post("/api/v1/auth/logout", headers=headers, json={}).status_code == 422
    assert client.get("/api/v1/auth/me?role=ADMIN", headers=headers).status_code == 422
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.get(Inquiry, ids["INQ-DEMO-002"]).lock_version == 1
        assert session.scalar(select(AuthSession)).revoked_at is None


def test_order_placeholder_checks_binding_and_never_fetches_or_creates_context(access_app):
    client, _, engine, password, ids = access_app
    _, headers = sign_in(client, password)
    path = f"/api/v1/inquiries/{ids['INQ-DEMO-002']}/order"
    assert client.get(path, headers=headers).json()["error"]["code"] == "CONTEXT_REQUIRED"
    assert client.get(path, headers=headers).status_code == 409
    assert (
        client.get(f"/api/v1/inquiries/{ids['INQ-DEMO-011']}/order", headers=headers).status_code
        == 403
    )
    with Session(engine) as session, session.begin():
        session.get(Inquiry, ids["INQ-DEMO-002"]).external_order_id = None
    response = client.get(path, headers=headers)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "ORDER_REFERENCE_MISSING"
    )
    with Session(engine) as session:
        record = session.get(Inquiry, ids["INQ-DEMO-002"])
        assert record.state == "OPEN" and record.current_context_id is None


def test_failure_during_audit_flush_rolls_back_login_and_logout(access_app, monkeypatch):
    client, _, engine, password, _ = access_app
    first, headers = sign_in(client, password)

    def invalid_audit(self, *args, **kwargs):
        self.session.add(
            AuditLog(
                event_type="NOT_ALLOWED", request_id="req-test", occurred_at=T0, safe_metadata={}
            )
        )

    monkeypatch.setattr(CoreAccess, "audit", invalid_audit)
    response = client.post("/api/v1/auth/login", json={"username": "agent.a", "password": password})
    assert response.status_code == 500 and password not in response.text
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 500
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 1
        auth = session.scalar(
            select(AuthSession).where(
                AuthSession.token_digest == token_digest(first.json()["token"])
            )
        )
        assert auth.revoked_at is None
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_identity_session_and_inquiry_locks_prevent_mid_request_changes(access_app):
    client, _, engine, password, ids = access_app
    _, headers = sign_in(client, password)
    with Session(engine) as reader, reader.begin():
        service = CoreAccess(reader, FixedClock(T0), "req-lock")
        user, auth = service.authenticate(headers["Authorization"])
        user_id = user.id
        service.read_inquiry(headers["Authorization"], str(ids["INQ-DEMO-002"]), b"", [])
        for statement in (
            update(User).where(User.id == user.id).values(is_active=False),
            update(AuthSession).where(AuthSession.id == auth.id).values(revoked_at=T0),
            update(Inquiry).where(Inquiry.id == ids["INQ-DEMO-002"]).values(lock_version=2),
        ):
            with Session(engine) as writer, writer.begin():
                writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(OperationalError):
                    writer.execute(statement)
                writer.rollback()
    # Locks are released at transaction exit; the same write can now proceed.
    with Session(engine) as writer, writer.begin():
        writer.execute(update(User).where(User.id == user_id).values(is_active=False))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
