import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.db.models import (
    APPEND_ONLY_TABLES,
    Approval,
    AuditLog,
    Base,
    ContextVersion,
    DraftRevision,
    GenerationAttempt,
    Inquiry,
    ResolutionRun,
    SourceFetch,
    Team,
    User,
    ValidationResult,
)
from app.db.seed import PASSWORD_HASHER, seed_demo

pytestmark = pytest.mark.database
T0 = datetime(2026, 9, 20, 6, tzinfo=UTC)


def demo(session):
    password = secrets.token_urlsafe(24)
    seed_demo(session, FixedClock(T0), app_env="test", password=password)
    inquiry = session.scalar(select(Inquiry).where(Inquiry.external_inquiry_id == "INQ-DEMO-002"))
    return inquiry, password


def run_record(inquiry, **overrides):
    values = dict(
        inquiry_id=inquiry.id,
        actor_id=inquiry.assigned_agent_id,
        version=1,
        idempotency_key="resolve-test-1",
        request_hash="a" * 64,
        state="SUCCEEDED",
        request_id="req-database-test",
        started_at=T0,
        finished_at=T0,
    )
    values.update(overrides)
    return ResolutionRun(**values)


def test_migration_roundtrip_and_orm_schema_match(database):
    engine, config, _ = database
    with engine.connect() as connection:
        assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_core_mvp"
    command.downgrade(config, "base")
    with engine.connect() as connection:
        assert not set(Base.metadata.tables) & set(inspect(connection).get_table_names())
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())


def test_seed_is_idempotent_and_preserves_password_and_workflow(database):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, password = demo(session)
        user = session.get(User, inquiry.assigned_agent_id)
        stored_hash = user.password_hash
        assert stored_hash != password and PASSWORD_HASHER.verify(stored_hash, password)
        inquiry.state = "ESCALATED"
        inquiry.escalation_reason = "Manual verification required."
        inquiry.lock_version = 4
        seed_demo(
            session,
            FixedClock(T0 + timedelta(hours=1)),
            app_env="test",
            password=secrets.token_urlsafe(24),
        )
        assert user.password_hash == stored_hash
        assert inquiry.state == "ESCALATED" and inquiry.lock_version == 4
        assert session.scalar(select(func.count()).select_from(Team)) == 2
        assert session.scalar(select(func.count()).select_from(User)) == 5
        assert session.scalar(select(func.count()).select_from(Inquiry)) == 12
        assert inquiry.created_at == T0 and inquiry.updated_at == T0


@pytest.mark.parametrize(
    "change", ["duplicate_inquiry", "missing_user", "invalid_state", "admin_team"]
)
def test_database_relationship_and_business_key_constraints(database, change):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            if change == "duplicate_inquiry":
                session.add(
                    Inquiry(
                        source_system=inquiry.source_system,
                        external_inquiry_id=inquiry.external_inquiry_id,
                        external_order_id=None,
                        team_id=inquiry.team_id,
                        assigned_agent_id=inquiry.assigned_agent_id,
                        state="OPEN",
                        created_at=T0,
                        updated_at=T0,
                    )
                )
            elif change == "missing_user":
                inquiry.assigned_agent_id = uuid4()
            elif change == "invalid_state":
                inquiry.state = "SENT"
            else:
                session.scalar(select(User).where(User.role == "ADMIN")).team_id = inquiry.team_id
            session.flush()


@pytest.mark.parametrize("duplicate", ["key", "version"])
def test_resolution_keys_and_versions_are_unique(database, duplicate):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        session.add(run_record(inquiry))
        session.flush()
        overrides = {"version": 2} if duplicate == "key" else {"idempotency_key": "new-key"}
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(run_record(inquiry, **overrides))
            session.flush()


def test_utc_and_required_timestamps(database):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        demo(session)
        with pytest.raises(StatementError, match="aware UTC"), session.begin_nested():
            session.add(
                Team(code="NAIVE", display_name="Invalid", created_at=T0.replace(tzinfo=None))
            )
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(Team(code="NULL", display_name="Invalid", created_at=None))
            session.flush()


@pytest.mark.parametrize(
    "outcome,payload,fetched,error",
    [
        ("EMPTY", {"records": []}, T0, None),
        ("TIMEOUT", None, None, "TIMEOUT"),
        ("NOT_FOUND", None, None, "NOT_FOUND"),
    ],
)
def test_source_outcomes_preserve_empty_and_failure(database, outcome, payload, fetched, error):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        run = run_record(inquiry)
        session.add(run)
        session.flush()
        record = SourceFetch(
            run_id=run.id,
            operation="get_notes",
            target_id=inquiry.external_order_id,
            outcome=outcome,
            source_system="demo_warehouse",
            canonical_payload=payload,
            fetched_at=fetched,
            error_code=error,
            started_at=T0,
            completed_at=T0,
            request_id="req-database-test",
        )
        session.add(record)
        session.flush()
        session.expire(record)
        assert record.outcome == outcome and record.canonical_payload == payload
        assert record.fetched_at == fetched and record.error_code == error


@pytest.mark.parametrize(
    "outcome,payload,fetched,error",
    [
        ("TIMEOUT", {"records": []}, None, "TIMEOUT"),
        ("EMPTY", None, T0, None),
        ("EMPTY", {"records": [{}]}, T0, None),
        ("SUCCESS", {"unexpected": []}, T0, None),
        ("SUCCESS", {"records": []}, T0, None),
    ],
)
def test_failure_cannot_be_fabricated_as_snapshot(database, outcome, payload, fetched, error):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        run = run_record(inquiry)
        session.add(run)
        session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                SourceFetch(
                    run_id=run.id,
                    operation="get_notes",
                    target_id="target",
                    outcome=outcome,
                    source_system="demo_warehouse",
                    canonical_payload=payload,
                    fetched_at=fetched,
                    error_code=error,
                    started_at=T0,
                    completed_at=T0,
                    request_id="req-database-test",
                )
            )
            session.flush()


def historical_chain(session, *, field=None, value=None):
    inquiry, _ = demo(session)
    run = run_record(inquiry, **({"idempotency_key": value} if field == "run_key" else {}))
    session.add(run)
    session.flush()
    context = ContextVersion(
        inquiry_id=inquiry.id,
        run_id=run.id,
        version=1,
        schema_version="core-mvp-v1",
        policy_version="core-policy-v1",
        quality="DEGRADED",
        payload={"fixture": "persistence-only"},
        created_at=T0,
    )
    session.add(context)
    session.flush()
    attempt = GenerationAttempt(
        inquiry_id=inquiry.id,
        context_id=context.id,
        actor_id=inquiry.assigned_agent_id,
        idempotency_key=value if field == "generation_key" else "generate-test",
        request_hash="a" * 64,
        state="SUCCEEDED",
        request_id="req-test",
        started_at=T0,
        finished_at=T0,
    )
    session.add(attempt)
    session.flush()
    draft = DraftRevision(
        inquiry_id=inquiry.id,
        context_id=context.id,
        generation_attempt_id=attempt.id,
        revision=1,
        origin="AI",
        analysis={},
        reply_text=value if field == "reply_text" else "Test persistence record only.",
        text_hash="b" * 64,
        created_at=T0,
    )
    session.add(draft)
    session.flush()
    validation = ValidationResult(
        draft_id=draft.id,
        context_id=context.id,
        policy_version="core-policy-v1",
        validator_version="validation-v1",
        text_hash=draft.text_hash,
        status="PASS",
        errors=[],
        warnings=[],
        evaluated_at=T0,
    )
    session.add(validation)
    session.flush()
    approval = Approval(
        inquiry_id=inquiry.id,
        context_id=context.id,
        draft_id=draft.id,
        validation_id=validation.id,
        reviewer_id=inquiry.assigned_agent_id,
        idempotency_key=value if field == "approval_key" else "approve-test",
        request_hash="c" * 64,
        text_hash=draft.text_hash,
        approved_at=T0,
    )
    audit = AuditLog(
        inquiry_id=inquiry.id,
        actor_id=inquiry.assigned_agent_id,
        event_type="APPROVED",
        request_id="req-test",
        occurred_at=T0,
        safe_metadata={"revision": 1},
    )
    source = SourceFetch(
        run_id=run.id,
        operation="get_notes",
        target_id="notes",
        outcome="EMPTY",
        source_system="demo_warehouse",
        canonical_payload={"records": []},
        fetched_at=T0,
        error_code=None,
        started_at=T0,
        completed_at=T0,
        request_id="req-test",
    )
    session.add_all([approval, audit, source])
    session.flush()
    return inquiry, context, draft, validation, approval, audit, source


@pytest.mark.parametrize("blank", [" ", "\t", "\n", " \r\n\t\f\v "])
@pytest.mark.parametrize("field", ["external_inquiry_id", "external_order_id", "escalation_reason"])
def test_inquiry_rejects_whitespace_only_values(database, field, blank):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            if field == "escalation_reason":
                inquiry.state = "ESCALATED"
            setattr(inquiry, field, blank)
            session.flush()


@pytest.mark.parametrize("blank", [" ", "\t", "\n", " \r\n\t\f\v "])
@pytest.mark.parametrize("field", ["run_key", "generation_key", "reply_text", "approval_key"])
def test_workflow_rejects_whitespace_only_values(database, field, blank):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        with pytest.raises(IntegrityError), session.begin_nested():
            historical_chain(session, field=field, value=blank)


def test_nonblank_reply_preserves_original_whitespace(database):
    engine, _, _ = database
    original = " \t订单记录\n仍需核实。\r\n "
    with Session(engine) as session, session.begin():
        _, _, draft, _, _, _, _ = historical_chain(session, field="reply_text", value=original)
        draft_id = draft.id
    with Session(engine) as session:
        assert session.get(DraftRevision, draft_id).reply_text == original


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_historical_records_cannot_be_updated_or_deleted(database, table):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        historical_chain(session)
        with pytest.raises(IntegrityError, match="append-only"), session.begin_nested():
            session.execute(text(f'UPDATE "{table}" SET id = id'))
        with pytest.raises(IntegrityError, match="append-only"), session.begin_nested():
            session.execute(text(f'DELETE FROM "{table}"'))


def test_only_one_approval_and_restrict_delete(database):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, context, draft, validation, approval, _, _ = historical_chain(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                Approval(
                    inquiry_id=inquiry.id,
                    context_id=context.id,
                    draft_id=draft.id,
                    validation_id=validation.id,
                    reviewer_id=inquiry.assigned_agent_id,
                    idempotency_key="another-key",
                    request_hash="d" * 64,
                    text_hash=approval.text_hash,
                    approved_at=T0,
                )
            )
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.delete(inquiry)
            session.flush()


def test_optimistic_lock_write_rejects_second_actor(database):
    engine, _, _ = database
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        statement = (
            update(Inquiry)
            .where(Inquiry.id == inquiry.id, Inquiry.lock_version == 1)
            .values(lock_version=2)
        )
        assert session.execute(statement).rowcount == 1
        assert session.execute(statement).rowcount == 0


def test_canonical_snapshot_json_keeps_original_source_times(database):
    engine, _, _ = database
    examples = Path(__file__).resolve().parents[3] / "docs/contracts/examples/core-contexts.json"
    case = next(
        c for c in json.loads(examples.read_text(encoding="utf-8"))["cases"] if c["name"] == "STALE"
    )
    payload = next(
        s["payload"] for s in case["snapshots"].values() if s["operation"] == "get_shipment"
    )
    with Session(engine) as session, session.begin():
        inquiry, _ = demo(session)
        run = run_record(inquiry)
        session.add(run)
        session.flush()
        source = SourceFetch(
            run_id=run.id,
            operation="get_shipment",
            target_id=payload["records"][0]["parcel_id"],
            outcome="SUCCESS",
            source_system="demo_logistics",
            canonical_payload=payload,
            fetched_at=T0,
            error_code=None,
            started_at=T0,
            completed_at=T0,
            request_id="req-snapshot-test",
        )
        session.add(source)
        session.flush()
        session.expire(source)
        assert source.canonical_payload == payload
        snapshot = source.canonical_payload["records"][0]
        assert snapshot["source_updated_at"] == "2026-09-17T06:00:00Z"
        assert snapshot["fetched_at"] == "2026-09-20T06:00:00Z"
        assert snapshot["events"][0]["occurred_at"] == "2026-09-17T06:00:00Z"
