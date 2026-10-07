"""Closed additive onboarding routes with authority checks before body reads."""

import inspect
import re
from datetime import timedelta
from uuid import uuid4

import anyio
from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse

from app.commerce import mailbox
from app.commerce import onboarding as domain
from app.commerce.errors import CommerceError, fail
from app.commerce.history import set_context
from app.commerce.onboarding_models import (
    AddressBook,
    AnonymousRequest,
    AuthRateEvent,
    MerchantApplication,
)
from app.commerce.onboarding_schemas import RESPONSES
from app.commerce.router import body, bounded_body, path_id, query, record_failure
from app.commerce.service import Commerce, digest

router = APIRouter(prefix="/api/commerce/v1", tags=["commerce onboarding"])
PUBLIC = {
    "register",
    "verify-email",
    "verification-request",
    "password-reset/request",
    "password-reset/confirm",
}
ROUTES = [
    ("POST", "/auth/" + op, op)
    for op in [
        "register",
        "verify-email",
        "verification-request",
        "password-reset/request",
        "password-reset/confirm",
    ]
] + [
    ("GET", "/account/profile", "profile.get"),
    ("POST", "/account/profile", "profile"),
    ("POST", "/account/email", "email"),
    ("POST", "/account/password", "password"),
    ("GET", "/customer/addresses", "addresses"),
    ("POST", "/customer/addresses", "address.create"),
    ("POST", "/customer/addresses/{id}/edit", "address.edit"),
    ("POST", "/customer/addresses/{id}/delete", "address.delete"),
    ("GET", "/customer/merchant-applications", "applications"),
    ("POST", "/customer/merchant-applications", "application.create"),
    ("POST", "/customer/merchant-applications/{id}/withdraw", "application.withdraw"),
    ("GET", "/review/merchant-applications", "review.applications"),
    ("POST", "/review/merchant-applications/{id}/decision", "application.decision"),
]


def authority(svc, request, op):
    if op in PUBLIC:
        return None
    svc.auth(
        "customer"
        if op.startswith(("address", "application")) and op != "application.decision"
        else None
    )
    if op in {"review.applications", "application.decision"}:
        info = domain.profile(svc)
        if not info or not info.review_enabled:
            fail("CAPABILITY_REQUIRED", 403)
    if "id" not in request.path_params:
        return None
    cls = AddressBook if op.startswith("address") else MerchantApplication
    row = svc.get(cls, path_id(request, "id"), svc.write)
    if (
        cls is AddressBook
        and not row.active
        or op != "application.decision"
        and row.customer_id != svc.actor.id
    ):
        fail("NOT_FOUND", 404)
    return row


def rate(svc, op, payload):
    ip = digest(svc.request.client.host if svc.request.client else "unknown")
    target = payload.get("email") if isinstance(payload, dict) else None
    target = digest(target.strip().lower()) if isinstance(target, str) else None
    db = svc.db
    count = db.scalar(
        select(func.count())
        .select_from(AuthRateEvent)
        .where(
            AuthRateEvent.purpose == op,
            AuthRateEvent.ip_digest == ip,
            AuthRateEvent.created_at > svc.now - timedelta(minutes=10),
        )
    )
    email_count = (
        db.scalar(
            select(func.count())
            .select_from(AuthRateEvent)
            .where(
                AuthRateEvent.purpose == op,
                AuthRateEvent.email_digest == target,
                AuthRateEvent.created_at > svc.now - timedelta(minutes=15),
            )
        )
        if target
        else 0
    )
    if count >= 20 or email_count >= 5:
        return False
    svc.new(AuthRateEvent, purpose=op, ip_digest=ip, email_digest=target)
    return True


def anonymous(svc, op, payload):
    keys = svc.request.headers.getlist("idempotency-key")
    if len(keys) != 1 or not re.fullmatch(r"[!-~]{1,200}", keys[0]):
        fail("IDEMPOTENCY_KEY_REQUIRED" if not keys else "INVALID_REQUEST", 400)
    request_hash = svc.onboarding_fingerprint(payload)
    old = svc.db.scalar(
        select(AnonymousRequest).where(
            AnonymousRequest.operation == op, AnonymousRequest.key == keys[0]
        )
    )
    if old:
        if old.request_hash != request_hash:
            fail("IDEMPOTENCY_CONFLICT")
        return old.response_payload, old.response_status, True
    result, status = domain.public(svc, op, payload)
    svc.new(
        AnonymousRequest,
        operation=op,
        key=keys[0],
        request_hash=request_hash,
        response_payload=result,
        response_status=status,
    )
    return result, status, False


def read(svc, request, op):
    if op == "profile.get":
        if request.query_params:
            fail("INVALID_REQUEST", 400)
        return domain.profile_view(svc)
    limit, offset, params = query(request, ("state",) if op == "review.applications" else ())
    if op == "addresses":
        stmt = select(AddressBook).where(
            AddressBook.customer_id == svc.actor.id, AddressBook.active.is_(True)
        )
        view = domain.address_view
    else:
        stmt = select(MerchantApplication)
        view = domain.application_view
        if op == "applications":
            stmt = stmt.where(MerchantApplication.customer_id == svc.actor.id)
        if "state" in params:
            if params["state"] not in {"PENDING", "APPROVED", "REJECTED", "WITHDRAWN"}:
                fail("INVALID_REQUEST", 400)
            stmt = stmt.where(MerchantApplication.state == params["state"])
    cls = AddressBook if op == "addresses" else MerchantApplication
    rows = list(
        svc.db.scalars(
            stmt.order_by(cls.created_at.desc(), cls.id.desc()).offset(offset).limit(limit + 1)
        )
    )
    return dict(
        items=[view(row) for row in rows[:limit]],
        limit=limit,
        offset=offset,
        has_more=len(rows) > limit,
    )


def handler(method, path, op):
    def endpoint(request: Request, **parameters):
        request.state.request_id = str(uuid4())
        db = None
        svc = None
        replay = False
        failure = None
        status = 200
        try:
            if (
                request.headers.get("origin") is not None
                and request.headers["origin"] not in request.app.state.settings.cors_allowed_origins
            ):
                fail("CAPABILITY_REQUIRED", 403)
            db = request.app.state.session_factory()
            if op in PUBLIC:
                raw = anyio.from_thread.run(bounded_body, request)
                with db.begin():
                    limiter = Commerce(db, request.app.state.clock, request, True)
                    try:
                        rate_payload = body(raw)
                    except CommerceError:
                        rate_payload = {}
                    allowed = rate(limiter, op, rate_payload)
                if not allowed:
                    fail("RATE_LIMITED", 429)
            with db.begin():
                svc = Commerce(db, request.app.state.clock, request)
                svc.letters = []
                svc.onboarding_fingerprint = lambda value: (
                    mailbox.fingerprint(request.app.state.settings, value)
                    if op in PUBLIC or op == "email"
                    else digest(value)
                )
                row = authority(svc, request, op)
                if method == "GET":
                    result = read(svc, request, op)
                else:
                    raw = raw if op in PUBLIC else anyio.from_thread.run(bounded_body, request)
                    svc.acquire_write()
                    row = authority(svc, request, op)
                    payload = body(raw)
                    if op == "application.decision" and isinstance(payload, dict):
                        set_context(db, svc.actor, request, payload.get("reason"))
                    if request.query_params:
                        fail("INVALID_REQUEST", 400)
                    if op in {
                        "register",
                        "verification-request",
                        "password-reset/request",
                        "email",
                    }:
                        try:
                            mailbox.check_delivery(request.app.state.settings)
                        except OSError:
                            fail("MAILBOX_UNAVAILABLE", 503)
                    delivery_operation = (
                        "delivery:" + op + ":" + (str(svc.actor.id) if svc.actor else "anonymous")
                    )
                    delivery_key = request.headers.get("idempotency-key", "")
                    delivery_failure = db.scalar(
                        select(AnonymousRequest).where(
                            AnonymousRequest.operation == delivery_operation,
                            AnonymousRequest.key == delivery_key,
                        )
                    )
                    if delivery_failure:
                        if delivery_failure.request_hash != svc.onboarding_fingerprint(payload):
                            fail("IDEMPOTENCY_CONFLICT")
                        if delivery_failure.response_status == 102:
                            fail("OPERATION_BUSY")
                        if delivery_failure.response_status == 503:
                            fail("MAILBOX_DELIVERY_FAILED", 503)
                    if op in PUBLIC:
                        result, status, replay = anonymous(svc, op, payload)
                    elif op == "password":
                        result, status = domain.mutate(svc, op, row, payload)
                    else:
                        result, status, replay = svc.write_result(
                            "onboarding:" + request.url.path,
                            payload,
                            lambda: domain.mutate(svc, op, row, payload),
                        )
                    if svc.letters:
                        svc.new(
                            AnonymousRequest,
                            operation=delivery_operation,
                            key=delivery_key,
                            request_hash=svc.onboarding_fingerprint(payload),
                            response_payload={"pending": True},
                            response_status=102,
                        )
                if not replay:
                    result = RESPONSES[op].model_validate(result).model_dump(mode="json")
            for letter in svc.letters:
                try:
                    mailbox.deliver(request.app.state.settings, letter)
                except OSError:
                    with db.begin():
                        marker = db.scalar(
                            select(AnonymousRequest)
                            .where(
                                AnonymousRequest.operation == delivery_operation,
                                AnonymousRequest.key == delivery_key,
                            )
                            .with_for_update()
                        )
                        marker.response_status = 503
                        marker.response_payload = {"failed": True}
                    fail("MAILBOX_DELIVERY_FAILED", 503)
            if svc.letters:
                with db.begin():
                    marker = db.scalar(
                        select(AnonymousRequest)
                        .where(
                            AnonymousRequest.operation == delivery_operation,
                            AnonymousRequest.key == delivery_key,
                        )
                        .with_for_update()
                    )
                    marker.response_status = 202
                    marker.response_payload = {"delivered": True}
        except CommerceError as error:
            status = error.status
            result = error.payload(request.state.request_id)
            failure = error.code
        except DBAPIError as error:
            status = (
                409
                if getattr(error.orig, "sqlstate", None) in {"55P03", "40P01", "40001", "23505"}
                else 500
            )
            failure = "OPERATION_BUSY" if status == 409 else "INTERNAL_ERROR"
            result = CommerceError(status, failure).payload(request.state.request_id)
        except Exception:
            status = 500
            failure = "INTERNAL_ERROR"
            result = CommerceError(status, failure).payload(request.state.request_id)
        finally:
            if failure:
                record_failure(db, svc, request, "onboarding:" + op, failure)
            if db:
                db.close()
        response = JSONResponse(result, status_code=status)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-Id"] = request.state.request_id
        if replay:
            response.headers["Idempotent-Replay"] = "true"
        return response

    endpoint.__signature__ = inspect.Signature(
        [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)]
        + [
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=str)
            for name in re.findall(r"{(\w+)}", path)
        ]
    )
    endpoint.__name__ = "onboarding_" + op.replace("/", "_").replace(".", "_")
    return endpoint


for method, path, op in ROUTES:
    router.add_api_route(
        path,
        handler(method, path, op),
        methods=[method],
        response_model=RESPONSES[op],
        name="onboarding." + op,
        openapi_extra={"security": [] if op in PUBLIC else [{"CommerceBearer": []}]},
    )
