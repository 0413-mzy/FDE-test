"""Short durable reservations around external calls, never holding business locks."""

import hashlib
import json
import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select, text

from app.commerce.ai_models import AIAttempt
from app.commerce.ai_provider import PROMPT_VERSION, DeepSeek, ProviderFailure
from app.commerce.errors import fail
from app.commerce.models import Conversation, Message
from app.commerce.router import body, path_id
from app.commerce.service import Commerce


def authority(db, request):
    svc = Commerce(db, request.app.state.clock, request)
    svc.auth("merchant", path_id(request, "shop"))
    if svc.shop.status != "ACTIVE":
        fail("CAPABILITY_REQUIRED", 403)
    row = svc.get(Conversation, path_id(request, "conversation"))
    if row.shop_id != svc.shop.id:
        fail("NOT_FOUND", 404)
    return svc, row


def snapshot(db, conversation, enforce_limit=True):
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
        .limit(501)
    ).all()
    if len(rows) > 500:
        if enforce_limit:
            fail("AI_INPUT_LIMIT", 400)
        return [], "over-limit"
    messages = [{"id": str(r.id), "sender_side": r.sender_side, "body": r.body} for r in rows]
    if sum(len(m["body"]) for m in messages) > 80000:
        if enforce_limit:
            fail("AI_INPUT_LIMIT", 400)
        return [], "over-limit"
    digest = hashlib.sha256(
        json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return messages, digest


def attempt_view(row):
    if row is None:
        return None
    return {
        name: (
            str(value)
            if name == "id"
            else value.isoformat()
            if name in {"created_at", "finished_at"} and value
            else value
        )
        for name in (
            "id",
            "state",
            "message_count",
            "source_ids",
            "model",
            "prompt_version",
            "created_at",
            "finished_at",
            "result",
            "error_code",
            "usage",
        )
        for value in [getattr(row, name)]
    }


def view(db, request, conversation, digest):
    statement = (
        select(AIAttempt)
        .where(AIAttempt.conversation_id == conversation.id)
        .order_by(AIAttempt.created_at.desc(), AIAttempt.id.desc())
    )
    latest = db.scalar(statement.limit(1))
    success = db.scalar(statement.where(AIAttempt.state == "SUCCEEDED").limit(1))
    latest_view = attempt_view(latest)
    if latest and latest.state == "RUNNING" and latest.lease_until <= request.app.state.clock.now():
        latest_view["state"], latest_view["error_code"] = "FAILED", "AI_INTERRUPTED"
    return {
        "available": bool(request.app.state.settings.deepseek_api_key),
        "latest_success": attempt_view(success),
        "latest_attempt": latest_view,
        "stale": bool(success and success.snapshot_hash != digest),
    }


def assistance(request, generate=False, raw=b""):
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    attempt_id = None
    with factory() as db, db.begin():
        svc, conversation = authority(db, request)
        if request.query_params:
            fail("INVALID_REQUEST", 400)
        if generate:
            if body(raw) != {}:
                fail("INVALID_REQUEST", 400)
            key = request.headers.get("Idempotency-Key", "")
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", key):
                fail("INVALID_REQUEST", 400)
            db.execute(text("SET LOCAL lock_timeout='2000ms'"))
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "current_schema() || '-conversation-ai-rate',0))"
                )
            )
            # Serialize only reservation bookkeeping across workers, outside provider calls.
            svc, conversation = authority(db, request)
        messages, digest = snapshot(db, conversation, enforce_limit=generate)
        if not generate:
            return view(db, request, conversation, digest), False
        now = svc.clock.now()
        expired = db.scalars(
            select(AIAttempt).where(AIAttempt.state == "RUNNING", AIAttempt.lease_until <= now)
        ).all()
        for row in expired:
            row.state, row.error_code, row.finished_at = "FAILED", "AI_INTERRUPTED", now
        db.flush()
        previous = db.scalar(
            select(AIAttempt).where(
                AIAttempt.actor_id == svc.actor.id,
                AIAttempt.conversation_id == conversation.id,
                AIAttempt.idempotency_key == key,
            )
        )
        if previous:
            if previous.snapshot_hash != digest:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return view(db, request, conversation, digest), True
        recent = (
            select(func.count())
            .select_from(AIAttempt)
            .where(AIAttempt.created_at > now - timedelta(minutes=1))
        )
        if (
            db.scalar(recent) >= 20
            or db.scalar(recent.where(AIAttempt.actor_id == svc.actor.id)) >= 3
        ):
            fail("AI_RATE_LIMITED", 429)
        success = db.scalar(
            select(AIAttempt).where(
                AIAttempt.conversation_id == conversation.id,
                AIAttempt.snapshot_hash == digest,
                AIAttempt.state == "SUCCEEDED",
                AIAttempt.model == settings.deepseek_model,
                AIAttempt.prompt_version == PROMPT_VERSION,
            )
        )
        if success:
            db.add(
                AIAttempt(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    actor_id=svc.actor.id,
                    idempotency_key=key,
                    snapshot_hash=digest,
                    source_ids=success.source_ids,
                    message_count=success.message_count,
                    model=success.model,
                    prompt_version=success.prompt_version,
                    state="SUCCEEDED",
                    lease_until=now,
                    created_at=now,
                    finished_at=success.finished_at,
                    result=success.result,
                    usage=[],
                    cached_from=success.id,
                )
            )
            db.flush()
            return view(db, request, conversation, digest), True
        if not settings.deepseek_api_key:
            fail("AI_UNAVAILABLE", 503)
        if not messages:
            fail("AI_EMPTY_CONVERSATION", 400)
        if db.scalar(
            select(AIAttempt.id).where(
                AIAttempt.conversation_id == conversation.id, AIAttempt.state == "RUNNING"
            )
        ):
            fail("AI_BUSY", 409)
        active = db.scalar(
            select(func.count()).select_from(AIAttempt).where(AIAttempt.state == "RUNNING")
        )
        if active >= 4:
            fail("AI_RATE_LIMITED", 429)
        attempt_id = uuid4()
        db.add(
            AIAttempt(
                id=attempt_id,
                conversation_id=conversation.id,
                actor_id=svc.actor.id,
                idempotency_key=key,
                snapshot_hash=digest,
                source_ids=[m["id"] for m in messages],
                message_count=len(messages),
                model=settings.deepseek_model,
                prompt_version=PROMPT_VERSION,
                state="RUNNING",
                lease_until=now + timedelta(seconds=120),
                created_at=now,
                usage=[],
            )
        )
    # No Session or transaction exists during external I/O.
    try:
        provider = getattr(request.app.state, "conversation_ai_provider_factory", DeepSeek)(
            settings
        )
        result, usage = provider.generate(messages)
        error = None
    except ProviderFailure as exc:
        result, usage, error = None, exc.usage, exc.code
    except Exception:
        result, usage, error = None, [], "AI_PROVIDER_FAILED"
    with factory() as db, db.begin():
        row = db.scalar(select(AIAttempt).where(AIAttempt.id == attempt_id).with_for_update())
        if row.state == "RUNNING":
            row.result, row.usage, row.error_code = result, usage, error
            row.state, row.finished_at = (
                ("FAILED" if error else "SUCCEEDED"),
                request.app.state.clock.now(),
            )
        elif usage:
            # A recovered expired lease must not resurrect output, but billed usage remains visible.
            row.usage = usage
    # Fresh transaction rechecks sessions, membership and conversation ownership after I/O.
    with factory() as db, db.begin():
        _, conversation = authority(db, request)
        _, digest = snapshot(db, conversation, enforce_limit=False)
        return view(db, request, conversation, digest), False
