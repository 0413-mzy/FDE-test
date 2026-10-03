"""Core MVP records; external commerce facts stay in canonical JSON snapshots."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("Product timestamps must be aware UTC values")
        return value


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )
    type_annotation_map = {datetime: UtcDateTime(), dict: JSONB, list: JSONB}


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Team(Record, Base):
    __tablename__ = "teams"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'ADMIN' AND team_id IS NULL) OR "
            "(role IN ('AGENT', 'SUPERVISOR') AND team_id IS NOT NULL)",
            name="role_team",
        ),
        CheckConstraint("lock_version > 0", name="lock_version"),
        CheckConstraint("username ~ '^[A-Za-z0-9._-]{3,64}$'", name="username"),
    )
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        Enum("AGENT", "SUPERVISOR", "ADMIN", native_enum=False, create_constraint=True, name="role")
    )
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    is_active: Mapped[bool]
    created_at: Mapped[datetime]
    lock_version: Mapped[int] = mapped_column(default=1)


class AuthSession(Record, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry"),
        CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="token_digest"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class Inquiry(Record, Base):
    __tablename__ = "inquiries"
    __table_args__ = (
        UniqueConstraint("source_system", "external_inquiry_id"),
        CheckConstraint("lock_version > 0", name="lock_version"),
        CheckConstraint("btrim(external_inquiry_id) <> ''", name="external_inquiry_id"),
        CheckConstraint(
            "external_order_id IS NULL OR btrim(external_order_id) <> ''", name="external_order_id"
        ),
        CheckConstraint(
            "(state = 'ESCALATED' AND escalation_reason IS NOT NULL "
            "AND btrim(escalation_reason) <> '') OR "
            "(state <> 'ESCALATED' AND escalation_reason IS NULL)",
            name="escalation_reason",
        ),
    )
    source_system: Mapped[str] = mapped_column(Text)
    external_inquiry_id: Mapped[str] = mapped_column(Text)
    external_order_id: Mapped[str | None] = mapped_column(Text)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    assigned_agent_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(
        Enum(
            "OPEN",
            "CONTEXT_READY",
            "DRAFTED",
            "APPROVED",
            "ESCALATED",
            native_enum=False,
            create_constraint=True,
            name="state",
        )
    )
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    latest_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resolution_runs.id", ondelete="RESTRICT", use_alter=True)
    )
    current_context_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_versions.id", ondelete="RESTRICT", use_alter=True)
    )
    current_draft_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("draft_revisions.id", ondelete="RESTRICT", use_alter=True)
    )
    lock_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ResolutionRun(Record, Base):
    __tablename__ = "resolution_runs"
    __table_args__ = (
        UniqueConstraint("inquiry_id", "version"),
        UniqueConstraint("inquiry_id", "idempotency_key"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("btrim(idempotency_key) <> ''", name="idempotency_key"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash"),
        CheckConstraint(
            "(state = 'RUNNING' AND finished_at IS NULL) OR "
            "(state <> 'RUNNING' AND finished_at IS NOT NULL)",
            name="finished_at",
        ),
    )
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("inquiries.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int]
    state: Mapped[str] = mapped_column(
        Enum(
            "RUNNING",
            "SUCCEEDED",
            "PARTIAL",
            "FAILED",
            native_enum=False,
            create_constraint=True,
            name="state",
        )
    )
    request_id: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(Text)


class SourceFetch(Record, Base):
    __tablename__ = "source_fetches"
    __table_args__ = (
        UniqueConstraint("run_id", "operation", "target_id"),
        CheckConstraint("completed_at >= started_at", name="time_order"),
        CheckConstraint(
            "(outcome IN ('SUCCESS', 'EMPTY') AND canonical_payload IS NOT NULL "
            "AND fetched_at IS NOT NULL AND error_code IS NULL) OR "
            "(outcome NOT IN ('SUCCESS', 'EMPTY') AND canonical_payload IS NULL "
            "AND fetched_at IS NULL AND error_code IS NOT NULL)",
            name="outcome_payload",
        ),
        CheckConstraint(
            "canonical_payload IS NULL OR "
            "(jsonb_typeof(canonical_payload) = 'object' "
            "AND canonical_payload ? 'records' "
            "AND jsonb_typeof(canonical_payload->'records') = 'array')",
            name="records",
        ),
        CheckConstraint(
            "outcome <> 'EMPTY' OR (operation IN ('get_parcels', 'get_notes') "
            "AND canonical_payload->'records' = '[]'::jsonb)",
            name="empty_result",
        ),
        CheckConstraint(
            "outcome <> 'SUCCESS' OR canonical_payload->'records' <> '[]'::jsonb",
            name="nonempty_success",
        ),
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("resolution_runs.id", ondelete="RESTRICT"))
    operation: Mapped[str] = mapped_column(
        Enum(
            "get_inquiry",
            "get_order",
            "get_parcels",
            "get_shipment",
            "get_notes",
            native_enum=False,
            create_constraint=True,
            name="operation",
        )
    )
    target_id: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(
        Enum(
            "SUCCESS",
            "EMPTY",
            "NOT_FOUND",
            "NO_TRACKING",
            "TIMEOUT",
            "UNAVAILABLE",
            "INVALID_RESPONSE",
            "REJECTED",
            "CONFLICT",
            native_enum=False,
            create_constraint=True,
            name="outcome",
        )
    )
    request_id: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
    fetched_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(Text)
    canonical_payload: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class ContextVersion(Record, Base):
    __tablename__ = "context_versions"
    __table_args__ = (
        UniqueConstraint("inquiry_id", "version"),
        CheckConstraint("version > 0", name="version"),
    )
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("inquiries.id", ondelete="RESTRICT"))
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("resolution_runs.id", ondelete="RESTRICT"), unique=True
    )
    version: Mapped[int]
    schema_version: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    quality: Mapped[str] = mapped_column(
        Enum("COMPLETE", "DEGRADED", native_enum=False, create_constraint=True, name="quality")
    )
    payload: Mapped[dict]


class GenerationAttempt(Record, Base):
    __tablename__ = "generation_attempts"
    __table_args__ = (
        UniqueConstraint("inquiry_id", "idempotency_key"),
        CheckConstraint("btrim(idempotency_key) <> ''", name="idempotency_key"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash"),
        CheckConstraint(
            "(state = 'RUNNING' AND finished_at IS NULL) OR "
            "(state <> 'RUNNING' AND finished_at IS NOT NULL)",
            name="finished_at",
        ),
    )
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("inquiries.id", ondelete="RESTRICT"))
    context_id: Mapped[UUID] = mapped_column(ForeignKey("context_versions.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(
        Enum(
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            native_enum=False,
            create_constraint=True,
            name="state",
        )
    )
    request_id: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(Text)
    analysis: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    model_metadata: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class DraftRevision(Record, Base):
    __tablename__ = "draft_revisions"
    __table_args__ = (
        UniqueConstraint("inquiry_id", "revision"),
        CheckConstraint("revision > 0", name="revision"),
        CheckConstraint("text_hash ~ '^[0-9a-f]{64}$'", name="text_hash"),
        CheckConstraint(
            "length(reply_text) BETWEEN 1 AND 10000 AND btrim(reply_text) <> ''", name="reply_text"
        ),
        CheckConstraint(
            "(origin = 'AI' AND generation_attempt_id IS NOT NULL AND editor_id IS NULL) "
            "OR (origin = 'HUMAN' AND editor_id IS NOT NULL "
            "AND parent_revision_id IS NOT NULL)",
            name="origin_author",
        ),
    )
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("inquiries.id", ondelete="RESTRICT"))
    context_id: Mapped[UUID] = mapped_column(ForeignKey("context_versions.id", ondelete="RESTRICT"))
    generation_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("generation_attempts.id", ondelete="RESTRICT")
    )
    revision: Mapped[int]
    parent_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("draft_revisions.id", ondelete="RESTRICT")
    )
    editor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    origin: Mapped[str] = mapped_column(
        Enum("AI", "HUMAN", native_enum=False, create_constraint=True, name="origin")
    )
    analysis: Mapped[dict]
    reply_text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]


class ValidationResult(Record, Base):
    __tablename__ = "validation_results"
    __table_args__ = (CheckConstraint("text_hash ~ '^[0-9a-f]{64}$'", name="text_hash"),)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("draft_revisions.id", ondelete="RESTRICT"))
    context_id: Mapped[UUID] = mapped_column(ForeignKey("context_versions.id", ondelete="RESTRICT"))
    policy_version: Mapped[str] = mapped_column(Text)
    validator_version: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        Enum("PASS", "FAIL", native_enum=False, create_constraint=True, name="status")
    )
    errors: Mapped[list]
    warnings: Mapped[list]
    evaluated_at: Mapped[datetime]


class Approval(Record, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("inquiry_id", "idempotency_key"),
        CheckConstraint("btrim(idempotency_key) <> ''", name="idempotency_key"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash"),
        CheckConstraint("text_hash ~ '^[0-9a-f]{64}$'", name="text_hash"),
    )
    inquiry_id: Mapped[UUID] = mapped_column(
        ForeignKey("inquiries.id", ondelete="RESTRICT"), unique=True
    )
    context_id: Mapped[UUID] = mapped_column(ForeignKey("context_versions.id", ondelete="RESTRICT"))
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("draft_revisions.id", ondelete="RESTRICT"))
    validation_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_results.id", ondelete="RESTRICT")
    )
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    text_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime]


class AuditLog(Record, Base):
    __tablename__ = "audit_logs"
    inquiry_id: Mapped[UUID | None] = mapped_column(ForeignKey("inquiries.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(
        Enum(
            "LOGIN_SUCCESS",
            "LOGIN_FAILED",
            "LOGOUT",
            "ACCESS_DENIED",
            "RESOLVE_STARTED",
            "RESOLVE_SUCCEEDED",
            "RESOLVE_PARTIAL",
            "RESOLVE_FAILED",
            "GENERATION_STARTED",
            "GENERATION_SUCCEEDED",
            "GENERATION_FAILED",
            "DRAFT_EDITED",
            "VALIDATION_PASSED",
            "VALIDATION_FAILED",
            "APPROVED",
            "ESCALATED",
            "OPERATION_RECOVERED",
            native_enum=False,
            create_constraint=True,
            name="event_type",
        )
    )
    record_id: Mapped[UUID | None]
    request_id: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime]
    safe_metadata: Mapped[dict]


APPEND_ONLY_TABLES = (
    "source_fetches",
    "context_versions",
    "draft_revisions",
    "validation_results",
    "approvals",
    "audit_logs",
)
