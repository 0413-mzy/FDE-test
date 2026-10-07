"""Platform endpoints with authority and object ownership before payload parsing."""

import inspect
import re
from uuid import uuid4

import anyio
from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse

from app.commerce import inputs as inp
from app.commerce import platform_service as domain
from app.commerce.catalog_models import Category, ProductReview
from app.commerce.errors import CommerceError, fail
from app.commerce.history import set_context
from app.commerce.models import AfterSaleCase, CommerceAccount, Product, Shop
from app.commerce.platform_models import Dispute, ModerationAction, ModerationReport
from app.commerce.platform_schemas import RESPONSES
from app.commerce.router import body, bounded_body, path_id, record_failure
from app.commerce.service import Commerce

router = APIRouter(prefix="/api/commerce/v1", tags=["commerce platform"])
ROUTES = (
    [("GET", "/platform/access", "access")]
    + [
        ("GET", "/platform/" + name, "list." + name)
        for name in [
            "accounts",
            "shops",
            "products",
            "reviews",
            "reports",
            "disputes",
            "categories",
        ]
    ]
    + [
        ("GET", "/customer/reports", "customer.reports"),
        ("POST", "/customer/reports", "report.create"),
        ("GET", "/customer/disputes", "customer.disputes"),
        ("POST", "/customer/orders/{order}/after-sales/{case}/dispute", "dispute.create"),
        ("POST", "/customer/disputes/{id}/evidence", "customer.evidence"),
        ("POST", "/customer/disputes/{id}/withdraw", "customer.withdraw"),
        ("GET", "/merchant/shops/{shop}/disputes", "merchant.disputes"),
        ("POST", "/merchant/shops/{shop}/disputes/{id}/evidence", "merchant.evidence"),
        ("POST", "/platform/reports/{id}/decision", "report.decision"),
        ("POST", "/platform/moderation", "moderation"),
        ("POST", "/platform/disputes/{id}/decision", "dispute.decision"),
        ("POST", "/platform/disputes/{id}/refunds", "dispute.refunds"),
        ("POST", "/platform/categories", "category.create"),
        ("POST", "/platform/categories/{id}/edit", "category.edit"),
        ("GET", "/platform/analytics", "analytics"),
        ("GET", "/merchant/shops/{shop}/analytics", "merchant.analytics"),
    ]
)
ROUTES.extend(
    [
        ("GET", "/platform/actions", "list.actions"),
        ("GET", "/platform/disputes/{id}/context", "dispute.context"),
    ]
)
ROUTES.append(
    (
        "GET",
        "/customer/orders/{order}/after-sales/{case}/dispute-eligibility",
        "customer.eligibility",
    )
)
LISTS = {
    "actions": ModerationAction,
    "accounts": CommerceAccount,
    "shops": Shop,
    "products": Product,
    "reviews": ProductReview,
    "reports": ModerationReport,
    "disputes": Dispute,
    "categories": Category,
}


def authority(svc, request, op):
    context = {}
    if op == "access":
        svc.auth()
        return context
    if op.startswith("merchant."):
        svc.auth("merchant", path_id(request, "shop"), owner=op == "merchant.analytics")
    elif op.startswith("customer.") or op in {"report.create", "dispute.create"}:
        svc.auth("customer")
    else:
        domain.authorize(svc)
    if op in {"dispute.create", "customer.eligibility"}:
        order = svc.own_order(path_id(request, "order"))
        case = svc.get(AfterSaleCase, path_id(request, "case"), svc.write)
        if case.order_id != order.id:
            fail("NOT_FOUND", 404)
        context.update(order=order, case=case)
    if "id" in request.path_params:
        cls = (
            ModerationReport
            if op == "report.decision"
            else Category
            if op == "category.edit"
            else Dispute
        )
        row = svc.get(cls, path_id(request, "id"), svc.write)
        if (
            op.startswith("customer.")
            and row.customer_id != svc.actor.id
            or op.startswith("merchant.")
            and row.shop_id != svc.shop.id
        ):
            fail("NOT_FOUND", 404)
        context["row"] = row
    return context


def mutate(svc, op, ctx, payload):
    if op == "report.create":
        return domain.report_create(svc, payload)
    if op == "moderation":
        return domain.moderation(svc, payload)
    if op in {"dispute.create", "customer.eligibility"}:
        return domain.dispute_create(svc, ctx["order"], ctx["case"], payload)
    if op.endswith((".evidence", ".withdraw", ".decision", ".refunds")) and op != "report.decision":
        return domain.dispute_action(
            svc, ctx["row"], op.split(".")[-1], payload, merchant=op.startswith("merchant.")
        )
    if op == "report.decision":
        inp.fields(payload, ["expected_version", "decision", "action", "reason"])
        row = ctx["row"]
        svc.version(row, payload)
        if row.state != "OPEN":
            fail("INVALID_STATE")
        decision = payload["decision"]
        reason = inp.string(payload["reason"], 1, 1000)
        if (
            not isinstance(decision, str)
            or decision not in {"DISMISS", "RESOLVE"}
            or decision == "DISMISS"
            and payload["action"] is not None
        ):
            fail("INVALID_REQUEST", 400)
        if payload["action"] is not None:
            target = domain.target(svc, row.target_type, row.target_id)
            domain.moderation(
                svc,
                dict(
                    target_type=row.target_type,
                    target_id=str(row.target_id),
                    expected_version=target.version,
                    action=payload["action"],
                    reason=reason,
                ),
                row,
            )
        row.state = "DISMISSED" if decision == "DISMISS" else "RESOLVED"
        row.decision_reason = reason
        svc.bump(row)
        return domain.dto(row), 200
    if op == "category.create":
        inp.fields(payload, ["name", "active"])
        row = svc.new(
            Category,
            name=inp.string(payload["name"], 1, 100),
            active=inp.boolean(payload["active"]),
        )
        return domain.dto(row), 201
    if op == "category.edit":
        inp.fields(payload, ["expected_version", "name", "active"])
        row = ctx["row"]
        svc.version(row, payload)
        row.name = inp.string(payload["name"], 1, 100)
        row.active = inp.boolean(payload["active"])
        svc.bump(row)
        return domain.dto(row), 200
    fail("NOT_FOUND", 404)


def read(svc, op, ctx):
    if op in {"access", "customer.eligibility", "dispute.context"} and svc.request.query_params:
        fail("INVALID_REQUEST", 400)
    if op == "dispute.context":
        return domain.dispute_context(svc, ctx["row"])
    if op == "customer.eligibility":
        order = ctx["order"]
        case = ctx["case"]
        return domain.eligibility(svc, order, case)
    if op == "access":
        return {"platform_enabled": domain.enabled(svc)}
    if op.startswith("list."):
        return domain.listing(svc, LISTS[op.split(".")[1]])
    if op == "customer.reports":
        return domain.listing(
            svc, ModerationReport, (ModerationReport.reporter_id == svc.actor.id,)
        )
    if op == "customer.disputes":
        return domain.listing(svc, Dispute, (Dispute.customer_id == svc.actor.id,))
    if op == "merchant.disputes":
        return domain.listing(svc, Dispute, (Dispute.shop_id == svc.shop.id,))
    if op in {"analytics", "merchant.analytics"}:
        return domain.analytics(svc, svc.shop.id if svc.shop else None)
    fail("NOT_FOUND", 404)


def validated_mutate(svc, op, ctx, payload):
    result, status = mutate(svc, op, ctx, payload)
    return RESPONSES[op].model_validate(result).model_dump(mode="json"), status


def handler(method, path, op):
    def endpoint(request: Request, **paths):
        request.state.request_id = str(uuid4())
        db = None
        svc = None
        replay = False
        failure = None
        try:
            db = request.app.state.session_factory()
            with db.begin():
                svc = Commerce(db, request.app.state.clock, request, False)
                ctx = authority(svc, request, op)
                if method == "POST":
                    raw = anyio.from_thread.run(bounded_body, request)
                    svc.acquire_write()
                    ctx = authority(svc, request, op)
                    if request.query_params:
                        fail("INVALID_REQUEST", 400)
                    payload = body(raw)
                    set_context(
                        db,
                        svc.actor,
                        request,
                        payload.get("reason") if isinstance(payload, dict) else None,
                        action="platform:" + op,
                    )
                    result, status, replay = svc.write_result(
                        "platform:" + request.url.path,
                        payload,
                        lambda: validated_mutate(svc, op, ctx, payload),
                    )
                else:
                    result = (
                        RESPONSES[op].model_validate(read(svc, op, ctx)).model_dump(mode="json")
                    )
                    status = 200
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
                record_failure(db, svc, request, "platform:" + op, failure)
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
            inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, annotation=str)
            for n in re.findall(r"{(\w+)}", path)
        ]
    )
    endpoint.__name__ = "platform_" + op.replace(".", "_")
    return endpoint


for method, path, op in ROUTES:
    router.add_api_route(
        path,
        handler(method, path, op),
        methods=[method],
        name="platform." + op,
        response_model=RESPONSES[op],
        openapi_extra={"security": [{"CommerceBearer": []}]},
    )
