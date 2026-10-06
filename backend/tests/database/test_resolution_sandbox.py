"""Product transactions with actual independent Sandbox HTTP, never its database."""

import os
import secrets
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.core.config import Settings
from app.db.models import ContextVersion, Inquiry, ResolutionRun, SourceFetch
from app.db.seed import seed_demo
from app.main import create_app

pytestmark = [pytest.mark.database, pytest.mark.integration]
T0 = datetime(2026, 9, 20, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    "number,state,flag",
    [
        (1, "SUCCEEDED", "MISSING_INFORMATION"),
        (2, "SUCCEEDED", "UNKNOWN_FRESHNESS"),
        (4, "SUCCEEDED", "UNKNOWN_FRESHNESS"),
        (5, "SUCCEEDED", "UNKNOWN_FRESHNESS"),
        (6, "SUCCEEDED", "UNKNOWN_FRESHNESS"),
        (7, "SUCCEEDED", "STALE_DATA"),
        (8, "PARTIAL", "PARTIAL_SOURCE_FAILURE"),
        (9, "PARTIAL", "PARTIAL_SOURCE_FAILURE"),
        (10, "PARTIAL", "PARTIAL_SOURCE_FAILURE"),
        (11, "SUCCEEDED", "CONFLICTING_SOURCES"),
        (12, "FAILED", None),
    ],
)
def test_real_product_resolution_persists_source_quality(database, request, number, state, flag):
    url = request.config.getoption("--sandbox-url") or os.environ.get("INTEGRATION_SANDBOX_URL")
    if not url:
        pytest.skip("Product/Sandbox real HTTP requires --sandbox-url")
    engine, _, _ = database
    password = secrets.token_urlsafe(24)
    external_id = f"INQ-DEMO-{number:03}"
    with Session(engine) as session, session.begin():
        seed_demo(session, FixedClock(T0), app_env="test", password=password)
        inquiry_id = session.scalar(
            select(Inquiry.id).where(Inquiry.external_inquiry_id == external_id)
        )
    application = create_app(
        Settings(_env_file=None, app_env="test", sandbox_base_url=url),
        session_factory=lambda: Session(engine),
        clock=FixedClock(T0),
    )
    path = f"/api/v1/inquiries/{inquiry_id}"
    username = "agent.b" if number == 11 else "agent.c" if number == 12 else "agent.a"
    with TestClient(application) as client:
        login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200
        headers = {
            "Authorization": "Bearer " + login.json()["token"],
            "Idempotency-Key": "stage4-real-http",
        }
        response = client.post(
            path + "/resolve-context", headers=headers, json={"expected_lock_version": 1}
        )
        assert response.status_code == (404 if state == "FAILED" else 201), response.text
        with Session(engine) as session:
            run = session.scalar(
                select(ResolutionRun).where(ResolutionRun.inquiry_id == inquiry_id)
            )
            assert run.state == state and run.version == 1
            assert run.finished_at == T0
            fetches = session.scalars(select(SourceFetch).where(SourceFetch.run_id == run.id)).all()
            assert fetches and all(row.completed_at == T0 for row in fetches)
            persisted = session.scalar(
                select(ContextVersion).where(ContextVersion.run_id == run.id)
            )
            record = session.get(Inquiry, inquiry_id)
            assert record.lock_version == 3
            run_id = run.id
            if state == "FAILED":
                assert (
                    persisted is None
                    and record.current_context_id is None
                    and record.state == "OPEN"
                )
                assert run.error_code == "SOURCE_NOT_FOUND"
                assert response.json()["error"]["code"] == "SOURCE_NOT_FOUND"
            else:
                assert persisted is not None and record.current_context_id == persisted.id
                assert persisted.quality == "DEGRADED" and flag in persisted.payload["risk_flags"]
                assert record.state == "CONTEXT_READY"
                context_id = persisted.id
                stored = persisted.payload
            for fetch in fetches:
                if fetch.outcome not in {"SUCCESS", "EMPTY"}:
                    assert fetch.canonical_payload is None and fetch.fetched_at is None
                    assert fetch.error_code == fetch.outcome
        run_view = client.get(path + f"/runs/{run_id}", headers=headers)
        assert run_view.status_code == 200 and run_view.json()["state"] == state
        replay = client.post(
            path + "/resolve-context", headers=headers, json={"expected_lock_version": 1}
        )
        assert replay.status_code == (404 if state == "FAILED" else 200)
        if state != "FAILED":
            context = client.get(path + f"/contexts/{context_id}", headers=headers)
            assert context.status_code == 200 and context.json()["is_current"] is True
            assert context.json()["context"] == stored
            order = client.get(path + "/order", headers=headers)
            assert order.status_code == 200 and order.json()["context_id"] == str(context_id)
            assert order.json()["order"]["external_order_id"] == f"ORD-DEMO-{number:03}"
            assert "freshness" in order.json()
        with Session(engine) as session:
            assert (
                len(
                    session.scalars(
                        select(ResolutionRun).where(ResolutionRun.inquiry_id == inquiry_id)
                    ).all()
                )
                == 1
            )
