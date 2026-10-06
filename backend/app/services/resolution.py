"""Short transactions reserve and atomically publish authorized immutable context."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.api.errors import ApiError
from app.context.builder import build_context
from app.context.collector import FetchRecord
from app.context.models import CaseContext
from app.db.models import (
    AuditLog,
    ContextVersion,
    GenerationAttempt,
    Inquiry,
    ResolutionRun,
    SourceFetch,
)
from app.services.core_access import CoreAccess, closed_query, inquiry_scope, no_input

ERROR_STATUS = {
    "SOURCE_NOT_FOUND": 404,
    "SOURCE_TIMEOUT": 504,
    "SOURCE_UNAVAILABLE": 503,
    "SOURCE_CONFLICT": 409,
    "ORDER_REFERENCE_MISSING": 422,
    "AUTHORIZATION_CHANGED": 403,
    "BINDING_CHANGED": 409,
    "OPERATION_INTERRUPTED": 409,
}


def uuid(value):
    try:
        return UUID(str(value))
    except ValueError:
        raise ApiError(422, "INVALID_REQUEST") from None


def resolve_input(body, content_type, query, keys):
    closed_query(query, set())
    if content_type.split(";", 1)[0].strip().lower() != "application/json" or len(body) > 4096:
        raise ApiError(422, "INVALID_REQUEST")
    try:
        data = json.loads(
            body, object_pairs_hook=lambda pairs: closed_query(pairs, {"expected_lock_version"})
        )
    except (ValueError, UnicodeError, RecursionError):
        raise ApiError(422, "INVALID_REQUEST") from None
    if (
        not isinstance(data, dict)
        or set(data) != {"expected_lock_version"}
        or type(data["expected_lock_version"]) is not int
        or data["expected_lock_version"] < 1
    ):
        raise ApiError(422, "INVALID_REQUEST")
    if len(keys) != 1 or not keys[0].strip() or not 1 <= len(keys[0]) <= 200:
        raise ApiError(422, "INVALID_REQUEST")
    return data["expected_lock_version"], keys[0]


@dataclass(frozen=True)
class Reservation:
    inquiry_id: UUID
    run_id: UUID
    actor_id: UUID
    version: int
    lock_version: int
    source_system: str
    external_inquiry_id: str
    external_order_id: str
    team_id: UUID
    assigned_agent_id: UUID


class ResolutionService(CoreAccess):
    def audit(self, event, actor_id=None, **metadata):
        if not event.startswith("RESOLVE_"):
            return super().audit(event, actor_id, **metadata)
        run_id = UUID(metadata["run_id"])
        run = self.session.get(ResolutionRun, run_id)
        self.session.add(
            AuditLog(
                inquiry_id=run.inquiry_id,
                record_id=run_id,
                actor_id=actor_id,
                event_type=event,
                request_id=self.request_id,
                occurred_at=self.clock.now(),
                safe_metadata=metadata,
            )
        )

    def authorized(self, header, inquiry_id, *, exclusive=False):
        user, _ = self.authenticate(header)
        inquiry = self.session.scalar(
            select(Inquiry)
            .where(Inquiry.id == uuid(inquiry_id), inquiry_scope(user))
            .with_for_update(read=not exclusive)
        )
        if inquiry is None:
            self.audit("ACCESS_DENIED", user.id, error_code="FORBIDDEN")
            raise ApiError(403, "FORBIDDEN")
        return user, inquiry

    def busy(self, inquiry):
        return any(
            self.session.scalar(
                select(model.id)
                .where(model.inquiry_id == inquiry.id, model.state == "RUNNING")
                .limit(1)
            )
            is not None
            for model in (ResolutionRun, GenerationAttempt)
        )

    def run_view(self, inquiry, run):
        context = self.session.scalar(
            select(ContextVersion).where(
                ContextVersion.run_id == run.id, ContextVersion.inquiry_id == inquiry.id
            )
        )
        return {
            "run_id": str(run.id),
            "state": run.state,
            "context_id": str(context.id) if context else None,
            "context_version": context.version if context else None,
            "quality": context.quality if context else None,
            "lock_version": inquiry.lock_version,
        }

    def failure(self, run):
        return ApiError(
            ERROR_STATUS.get(run.error_code, 502), run.error_code, {"run_id": str(run.id)}
        )

    def reject(self, user, inquiry, error):
        self.session.add(
            AuditLog(
                inquiry_id=inquiry.id,
                actor_id=user.id,
                record_id=None,
                event_type="RESOLVE_FAILED",
                request_id=self.request_id,
                occurred_at=self.clock.now(),
                safe_metadata={"error_code": error.code, "rejected": True},
            )
        )
        raise error

    def start(self, header, inquiry_id, body, content_type, query, keys):
        user, inquiry = self.authorized(header, inquiry_id, exclusive=True)
        try:
            version, key = resolve_input(body, content_type, query, keys)
        except ApiError as error:
            self.reject(user, inquiry, error)
        digest = hashlib.sha256(
            json.dumps(
                {"actor_id": str(user.id), "expected_lock_version": version},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        prior = self.session.scalar(
            select(ResolutionRun).where(
                ResolutionRun.inquiry_id == inquiry.id, ResolutionRun.idempotency_key == key
            )
        )
        if prior:
            if prior.request_hash != digest:
                self.reject(user, inquiry, ApiError(409, "IDEMPOTENCY_CONFLICT"))
            if prior.state == "FAILED":
                raise self.failure(prior)
            return (202 if prior.state == "RUNNING" else 200, self.run_view(inquiry, prior))
        if version != inquiry.lock_version:
            self.reject(user, inquiry, ApiError(409, "VERSION_CONFLICT"))
        if self.busy(inquiry):
            self.reject(user, inquiry, ApiError(409, "BUSY"))
        if inquiry.state in ("APPROVED", "ESCALATED"):
            self.reject(user, inquiry, ApiError(409, "STATE_CONFLICT"))
        if not inquiry.external_order_id:
            self.reject(user, inquiry, ApiError(422, "ORDER_REFERENCE_MISSING"))
        next_version = (
            self.session.scalar(
                select(func.max(ResolutionRun.version)).where(
                    ResolutionRun.inquiry_id == inquiry.id
                )
            )
            or 0
        ) + 1
        run = ResolutionRun(
            id=uuid4(),
            inquiry_id=inquiry.id,
            actor_id=user.id,
            version=next_version,
            idempotency_key=key,
            request_hash=digest,
            state="RUNNING",
            request_id=self.request_id,
            started_at=self.clock.now(),
        )
        self.session.add(run)
        self.session.flush()
        inquiry.latest_run_id = run.id
        inquiry.current_context_id = inquiry.current_draft_id = None
        inquiry.state = "OPEN"
        inquiry.lock_version += 1
        inquiry.updated_at = self.clock.now()
        self.audit("RESOLVE_STARTED", user.id, run_id=str(run.id))
        return Reservation(
            inquiry.id,
            run.id,
            user.id,
            next_version,
            inquiry.lock_version,
            inquiry.source_system,
            inquiry.external_inquiry_id,
            inquiry.external_order_id,
            inquiry.team_id,
            inquiry.assigned_agent_id,
        )

    def finish(self, header, reservation, collection):
        auth_error = None
        try:
            user, _ = self.authenticate(header)
        except ApiError as error:
            auth_error = error
            user = None
        inquiry = self.session.scalar(
            select(Inquiry).where(Inquiry.id == reservation.inquiry_id).with_for_update()
        )
        run = self.session.scalar(
            select(ResolutionRun)
            .where(
                ResolutionRun.id == reservation.run_id,
                ResolutionRun.inquiry_id == reservation.inquiry_id,
            )
            .with_for_update()
        )
        if (
            run is None
            or inquiry is None
            or run.actor_id != reservation.actor_id
            or run.version != reservation.version
            or run.state != "RUNNING"
            or inquiry.latest_run_id != run.id
        ):
            raise ApiError(409, "STATE_CONFLICT")
        allowed = (
            user is not None
            and user.id == reservation.actor_id
            and (
                (user.role == "SUPERVISOR" and user.team_id == inquiry.team_id)
                or (
                    user.role == "AGENT"
                    and user.team_id == inquiry.team_id
                    and user.id == inquiry.assigned_agent_id
                )
            )
        )
        binding = (
            inquiry.source_system,
            inquiry.external_inquiry_id,
            inquiry.external_order_id,
            inquiry.team_id,
            inquiry.assigned_agent_id,
        ) == (
            reservation.source_system,
            reservation.external_inquiry_id,
            reservation.external_order_id,
            reservation.team_id,
            reservation.assigned_agent_id,
        )
        if not allowed or not binding:
            run.state = "FAILED"
            run.error_code = "AUTHORIZATION_CHANGED" if not allowed else "BINDING_CHANGED"
            run.finished_at = self.clock.now()
            inquiry.current_context_id = inquiry.current_draft_id = None
            inquiry.state = "OPEN"
            inquiry.lock_version += 1
            inquiry.updated_at = self.clock.now()
            self.audit(
                "RESOLVE_FAILED",
                reservation.actor_id,
                run_id=str(run.id),
                error_code=run.error_code,
            )
            return auth_error or ApiError(
                403 if not allowed else 409,
                "FORBIDDEN" if not allowed else "BINDING_CHANGED",
                {"run_id": str(run.id)},
            )
        if inquiry.lock_version != reservation.lock_version:
            raise ApiError(409, "STATE_CONFLICT")
        for fetch in collection.fetches:
            self.session.add(
                SourceFetch(
                    id=fetch.id,
                    run_id=run.id,
                    operation=fetch.operation,
                    target_id=fetch.target_id,
                    source_system=fetch.source_system,
                    outcome=fetch.outcome,
                    started_at=fetch.started_at,
                    completed_at=fetch.completed_at,
                    fetched_at=fetch.fetched_at,
                    error_code=fetch.error_code,
                    canonical_payload=fetch.payload,
                    request_id=self.request_id,
                )
            )
        self.session.flush()
        run.state = collection.run_state
        run.error_code = collection.error_code
        run.finished_at = self.clock.now()
        if not collection.error_code:
            context = build_context(
                context_id=uuid4(),
                inquiry_id=inquiry.id,
                run_id=run.id,
                version=run.version,
                team_id=inquiry.team_id,
                assigned_agent_id=inquiry.assigned_agent_id,
                external_order_id=inquiry.external_order_id,
                fetches=collection.fetches,
                now=self.clock.now(),
            )
            record = ContextVersion(
                id=context.context_id,
                inquiry_id=inquiry.id,
                run_id=run.id,
                version=run.version,
                schema_version=context.schema_version,
                policy_version=context.policy_version,
                created_at=context.created_at,
                quality=context.quality,
                payload=context.model_dump(mode="json"),
            )
            self.session.add(record)
            self.session.flush()
            inquiry.current_context_id = record.id
            inquiry.state = "CONTEXT_READY"
        inquiry.lock_version += 1
        inquiry.updated_at = self.clock.now()
        self.audit("RESOLVE_" + run.state, user.id, run_id=str(run.id), error_code=run.error_code)
        self.session.flush()
        return self.failure(run) if run.error_code else self.run_view(inquiry, run)

    def context_chain(self, inquiry, context_id):
        record = self.session.scalar(
            select(ContextVersion).where(
                ContextVersion.id == uuid(context_id), ContextVersion.inquiry_id == inquiry.id
            )
        )
        if record is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND")
        run = self.session.get(ResolutionRun, record.run_id)
        context = CaseContext.model_validate_json(json.dumps(record.payload))
        if (
            run is None
            or run.inquiry_id != inquiry.id
            or run.state not in ("SUCCEEDED", "PARTIAL")
            or run.version != record.version
            or context.context_version != record.version
            or context.context_id != record.id
            or context.inquiry_id != inquiry.id
            or context.run_id != run.id
        ):
            raise ApiError(409, "CONTEXT_REQUIRED")
        fetches = self.session.scalars(
            select(SourceFetch).where(SourceFetch.run_id == run.id)
        ).all()
        rebuilt = build_context(
            context_id=record.id,
            inquiry_id=inquiry.id,
            run_id=run.id,
            version=record.version,
            team_id=context.authorization_scope.team_id,
            assigned_agent_id=context.authorization_scope.assigned_agent_id,
            external_order_id=context.authorization_scope.external_order_id,
            fetches=[
                FetchRecord(
                    f.id,
                    f.operation,
                    f.target_id,
                    f.source_system,
                    f.outcome,
                    f.started_at,
                    f.completed_at,
                    f.fetched_at,
                    f.error_code,
                    f.canonical_payload,
                )
                for f in fetches
            ],
            now=context.created_at,
            policy=context.freshness_policy,
        )
        # Snapshot pointers and values must refer to this exact persisted source chain.
        rebuilt_payload = rebuilt.model_dump(mode="json")
        stored_payload = context.model_dump(mode="json")
        for payload in (rebuilt_payload, stored_payload):
            payload["source_outcomes"].sort(key=lambda item: item["fetch_id"])
        if rebuilt_payload != stored_payload:
            raise ApiError(409, "CONTEXT_REQUIRED")
        return record, context, fetches

    def read(self, header, inquiry_id, body, query, *, run_id=None, context_id=None, order=False):
        _, inquiry = self.authorized(header, inquiry_id)
        no_input(body, query)
        if run_id is not None:
            run = self.session.scalar(
                select(ResolutionRun).where(
                    ResolutionRun.id == uuid(run_id), ResolutionRun.inquiry_id == inquiry.id
                )
            )
            if run is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND")
            view = self.run_view(inquiry, run)
            return {
                "id": str(run.id),
                "state": run.state,
                "version": run.version,
                "context_id": view["context_id"],
                "error_code": run.error_code,
                "lock_version": inquiry.lock_version,
                "busy": self.busy(inquiry),
            }
        if order:
            if not inquiry.external_order_id:
                raise ApiError(422, "ORDER_REFERENCE_MISSING")
            if inquiry.current_context_id is None:
                raise ApiError(409, "CONTEXT_REQUIRED")
            context_id = inquiry.current_context_id
        record, context, fetches = self.context_chain(inquiry, context_id)
        if not order:
            return {
                "context": context.model_dump(mode="json"),
                "is_current": inquiry.current_context_id == record.id,
            }
        scope = context.authorization_scope
        if inquiry.latest_run_id != record.run_id or (
            scope.external_order_id,
            scope.team_id,
            scope.assigned_agent_id,
        ) != (inquiry.external_order_id, inquiry.team_id, inquiry.assigned_agent_id):
            raise ApiError(409, "CONTEXT_REQUIRED")
        source = next(f for f in fetches if f.operation == "get_inquiry")
        if (
            source.source_system != inquiry.source_system
            or source.target_id != inquiry.external_inquiry_id
        ):
            raise ApiError(409, "CONTEXT_REQUIRED")
        order_payload = next(
            f.canonical_payload["records"][0] for f in fetches if f.operation == "get_order"
        )
        evidence = next(e for e in context.evidence if e.id == context.order.status_evidence_id)
        now = self.clock.now()
        freshness = (
            "UNKNOWN"
            if evidence.source_updated_at is None
            or evidence.fetched_at > now
            or evidence.source_updated_at > now
            else "STALE"
            if (now - evidence.fetched_at).total_seconds()
            > context.freshness_policy.fetch_max_age_seconds
            or (now - evidence.source_updated_at).total_seconds()
            > context.freshness_policy.source_max_age_seconds.order
            else "FRESH"
        )
        return {
            "context_id": str(record.id),
            "context_version": record.version,
            "order": order_payload,
            "freshness": freshness,
        }
