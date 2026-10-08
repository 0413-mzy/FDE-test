"""Commerce HTTP namespace, with authorization before closed input parsing."""

import inspect
import json
import re
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Request
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse, Response

from app.commerce import after_sales, views
from app.commerce import inputs as inp
from app.commerce.catalog_models import ProductExperience
from app.commerce.errors import CommerceError, fail
from app.commerce.history import set_context
from app.commerce.models import (
    AfterSaleCase,
    BusinessAudit,
    Checkout,
    Conversation,
    Inventory,
    Message,
    Order,
    PaymentAttempt,
    Product,
    RefundAttempt,
    Shipment,
    Shop,
    ShopMembership,
)
from app.commerce.schemas import RESPONSES
from app.commerce.service import ORDER_STATES, Commerce

PREFIX = "/api/commerce/v1"
router = APIRouter(prefix=PREFIX, tags=["commerce"])
demo_router = APIRouter(prefix=PREFIX, tags=["commerce simulation"])


def path_id(request, key):
    value = request.path_params[key]
    try:
        result = UUID(value)
    except (ValueError, TypeError):
        fail("NOT_FOUND", 404)
    if str(result) != value:
        fail("NOT_FOUND", 404)
    return result


def query(request, extras=()):
    pairs = list(request.query_params.multi_items())
    if len({k for k, _ in pairs}) != len(pairs) or any(
        k not in {"limit", "offset", *extras} for k, _ in pairs
    ):
        fail("INVALID_REQUEST", 400)
    values = dict(pairs)
    try:
        if (
            not values.get("limit", "20").isascii()
            or not values.get("limit", "20").isdecimal()
            or not values.get("offset", "0").isascii()
            or not values.get("offset", "0").isdecimal()
        ):
            fail("INVALID_REQUEST", 400)
        limit = int(values.get("limit", 20))
        offset = int(values.get("offset", 0))
    except ValueError:
        fail("INVALID_REQUEST", 400)
    if not 1 <= limit <= 100 or offset < 0:
        fail("INVALID_REQUEST", 400)
    return limit, offset, values


def page(db, statement, project, request, extras=()):
    limit, offset, values = query(request, extras)
    if "status" in values:
        if values["status"] not in ORDER_STATES:
            fail("INVALID_REQUEST", 400)
        statement = statement.where(Order.status == values["status"])
    results = list(db.scalars(statement.limit(limit + 1).offset(offset)))
    return {
        "items": [project(r) for r in results[:limit]],
        "limit": limit,
        "offset": offset,
        "has_more": len(results) > limit,
    }


async def bounded_body(request):
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 65536:
            fail("INVALID_REQUEST", 400)
        chunks.append(chunk)
    return b"".join(chunks)


def body(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail("INVALID_REQUEST", 400)
            result[key] = value
        return result

    try:
        if len(raw) > 65536:
            fail("INVALID_REQUEST", 400)
        return json.loads(
            raw or b"{}",
            object_pairs_hook=unique,
            parse_constant=lambda _: fail("INVALID_REQUEST", 400),
        )
    except (ValueError, UnicodeDecodeError):
        fail("INVALID_REQUEST", 400)


def setup_authority(svc, request, operation):
    """Resolve every nested object before interpreting body or HTTP idempotency."""
    context = {}
    if operation.startswith("catalog") or operation == "login":
        return context
    if operation.startswith("customer"):
        svc.auth("customer")
        if "order" in request.path_params:
            context["order"] = svc.own_order(path_id(request, "order"))
        if "checkout" in request.path_params:
            checkout = svc.get(Checkout, path_id(request, "checkout"))
            if checkout.customer_id != svc.actor.id:
                fail("NOT_FOUND", 404)
            context["checkout"] = checkout
        if operation.startswith("customer.cart") or operation == "customer.checkout.create":
            context["cart"] = svc.my_cart()
        if operation == "customer.cart.delete":
            sku = path_id(request, "sku")
            context["sku_id"] = sku
    elif operation.startswith("merchant"):
        owner = (
            operation.startswith("merchant.product")
            or operation.startswith("merchant.sku")
            or operation.startswith("merchant.inventory")
            or operation.startswith("merchant.case.")
            and not operation.endswith("detail")
        )
        svc.auth("merchant", owner=owner)
        svc.auth(
            "merchant", path_id(request, "shop") if "shop" in request.path_params else None, owner
        )
        if "product" in request.path_params:
            context["product"] = svc.own_product(path_id(request, "product"))
        if "sku" in request.path_params:
            context["sku"] = svc.own_sku(path_id(request, "sku"), context.get("product"))
        if "order" in request.path_params:
            context["order"] = svc.own_order(path_id(request, "order"), True)
        if operation.startswith("merchant.inventory"):
            context["inventory"] = views.rows(svc.db, Inventory, sku_id=context["sku"].id)[0]
            if svc.write:
                svc.db.refresh(context["inventory"], with_for_update=True)
    elif operation.startswith("demo"):
        svc.auth("demo")
        if "attempt" in request.path_params:
            context["attempt"] = svc.get(
                RefundAttempt if operation == "demo.refund" else PaymentAttempt,
                path_id(request, "attempt"),
                svc.write,
            )
        if "shipment" in request.path_params:
            context["shipment"] = svc.get(Shipment, path_id(request, "shipment"), svc.write)
    else:
        svc.auth()
    if "shipment" in request.path_params and not operation.startswith("demo"):
        shipment = svc.get(Shipment, path_id(request, "shipment"))
        if shipment.order_id != context["order"].id:
            fail("NOT_FOUND", 404)
        context["shipment"] = shipment
    if "conversation" in request.path_params:
        row = svc.get(Conversation, path_id(request, "conversation"))
        if (
            row.customer_id != svc.actor.id
            if operation.startswith("customer")
            else row.shop_id != svc.shop.id
        ):
            fail("NOT_FOUND", 404)
        context["conversation"] = row
    if "case" in request.path_params:
        row = svc.get(AfterSaleCase, path_id(request, "case"), svc.write)
        if row.order_id != context["order"].id:
            fail("NOT_FOUND", 404)
        context["case"] = row
    return context


def read(svc, request, operation, context):
    db = svc.db
    if operation in {"customer.conversations", "merchant.conversations"}:
        statement = (
            select(Conversation)
            .where(
                Conversation.customer_id == svc.actor.id
                if operation.startswith("customer")
                else Conversation.shop_id == svc.shop.id
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
        return page(db, statement, views.conversation, request)
    if operation.endswith("messages"):
        statement = (
            select(Message)
            .where(Message.conversation_id == context["conversation"].id)
            .order_by(Message.created_at, Message.id)
        )
        return page(db, statement, views.message, request)
    if operation.endswith("case.detail"):
        query(request)
        if request.query_params:
            fail("INVALID_REQUEST", 400)
        return views.case(db, context["case"])
    if operation == "me":
        return views.account(db, svc.actor)
    if operation.startswith("catalog"):
        if operation == "catalog.detail":
            p = svc.get(Product, path_id(request, "product"))
            info = db.scalar(select(ProductExperience).where(ProductExperience.product_id == p.id))
            if (
                p.status != "PUBLISHED"
                or db.get(Shop, p.shop_id).status != "ACTIVE"
                or (info and info.moderation_hidden)
            ):
                fail("NOT_FOUND", 404)
            return views.product(db, p)
        _, _, values = query(request, ("shop_id", "q"))
        statement = (
            select(Product)
            .join(Shop)
            .outerjoin(ProductExperience, ProductExperience.product_id == Product.id)
            .where(
                Product.status == "PUBLISHED",
                Shop.status == "ACTIVE",
                (ProductExperience.id.is_(None) | ProductExperience.moderation_hidden.is_(False)),
            )
        )
        if "shop_id" in values:
            statement = statement.where(Product.shop_id == inp.identifier(values["shop_id"]))
        if "q" in values:
            q = inp.string(values["q"], 1, 100)
            statement = statement.where(
                Product.title.contains(q, autoescape=True)
                | Product.description.contains(q, autoescape=True)
            )
        return page(
            db,
            statement.order_by(Product.created_at.desc(), Product.id.desc()),
            lambda p: views.product(db, p),
            request,
            ("shop_id", "q"),
        )
    if operation == "merchant.shops":
        statement = (
            select(ShopMembership)
            .where(ShopMembership.account_id == svc.actor.id, ShopMembership.active.is_(True))
            .order_by(ShopMembership.created_at.desc(), ShopMembership.id.desc())
        )
        return page(db, statement, lambda m: views.membership(db, m), request)
    if operation == "merchant.products":
        statement = (
            select(Product)
            .where(Product.shop_id == svc.shop.id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        return page(db, statement, lambda p: views.product(db, p, True), request)
    if operation == "merchant.product.detail":
        return views.product(db, context["product"], True)
    if operation == "merchant.inventory":
        return views.inventory(context["inventory"])
    if operation == "customer.cart":
        return views.cart(db, context["cart"])
    if operation == "customer.checkout.detail":
        return views.checkout(db, context["checkout"], svc.now)
    if operation in {"customer.orders", "merchant.orders"}:
        statement = (
            select(Order)
            .where(
                Order.customer_id == svc.actor.id
                if operation.startswith("customer")
                else Order.shop_id == svc.shop.id
            )
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        return page(db, statement, lambda o: views.summary(o, svc.now, db), request, ("status",))
    if operation in {"customer.order.detail", "merchant.order.detail"}:
        return views.order(db, context["order"], svc.now, operation.startswith("merchant"))
    if operation in {"customer.shipment", "merchant.shipment"}:
        return views.shipment(db, context["shipment"])
    if operation == "demo.shipment":
        return views.demo_shipment(db, context["shipment"])
    if operation == "demo.shipments":
        limit, offset, values = query(request, ("status",))
        state = values.get("status")
        if state not in {
            None,
            "SHIPPED",
            "COLLECTED",
            "IN_TRANSIT",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "EXCEPTION",
        }:
            fail("INVALID_REQUEST", 400)
        statement = select(Shipment)
        if state:
            statement = statement.where(Shipment.status == state)
        rows = list(
            db.scalars(
                statement.order_by(Shipment.created_at.desc(), Shipment.id.desc())
                .limit(limit + 1)
                .offset(offset)
            )
        )
        return {
            "items": [views.demo_shipment(db, s) for s in rows[:limit]],
            "limit": limit,
            "offset": offset,
            "has_more": len(rows) > limit,
        }
    if operation == "demo.pending":
        limit, offset, values = query(request, ("kind",))
        kind = values.get("kind")
        if kind not in {None, "PAYMENT", "REFUND", "SHIPMENT"}:
            fail("INVALID_REQUEST", 400)
        items = []
        if kind in {None, "PAYMENT"}:
            items.extend(
                {
                    "id": str(a.id),
                    "kind": "PAYMENT",
                    "state": a.state,
                    "version": a.version,
                    "simulation": True,
                    "created_at": views.iso(a.created_at),
                }
                for a in db.scalars(select(PaymentAttempt).where(PaymentAttempt.state == "PENDING"))
            )
        if kind in {None, "REFUND"}:
            items.extend(
                {
                    "id": str(a.id),
                    "kind": "REFUND",
                    "state": a.state,
                    "version": a.version,
                    "simulation": True,
                    "created_at": views.iso(a.created_at),
                }
                for a in db.scalars(select(RefundAttempt).where(RefundAttempt.state == "PENDING"))
            )
        if kind in {None, "SHIPMENT"}:
            items.extend(
                {
                    "id": str(s.id),
                    "kind": "SHIPMENT",
                    "state": s.status,
                    "version": s.version,
                    "simulation": True,
                    "created_at": views.iso(s.created_at),
                }
                for s in db.scalars(select(Shipment).where(Shipment.status != "DELIVERED"))
            )
        items.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
        return {
            "items": items[offset : offset + limit],
            "limit": limit,
            "offset": offset,
            "has_more": len(items) > offset + limit,
        }
    fail("NOT_FOUND", 404)


def mutate(svc, operation, context, payload):
    if operation == "customer.conversation.create":
        return after_sales.conversation_create(svc, payload)
    if operation.endswith("message.create"):
        return after_sales.message_create(
            svc, context["conversation"], payload, operation.startswith("merchant")
        )
    if operation == "customer.case.create":
        return after_sales.create_case(svc, context["order"], payload)
    if ".case." in operation:
        return after_sales.case_action(
            svc, context["order"], context["case"], operation.rsplit(".", 1)[1], payload
        )
    if operation == "demo.refund":
        return after_sales.refund_result(svc, context["attempt"], payload)
    if operation == "logout":
        inp.fields(payload, [])
        svc.session.revoked_at = svc.now
        svc.bump(svc.session)
        svc.audit("LOGOUT", svc.actor.id)
        return None, 204
    if operation == "merchant.product.create":
        return svc.product_action(None, "create", payload)
    if operation.startswith("merchant.product."):
        return svc.product_action(context["product"], operation.rsplit(".", 1)[1], payload)
    if operation == "merchant.sku.edit":
        return svc.sku_edit(context["sku"], payload)
    if operation == "merchant.inventory.adjust":
        return svc.adjust(context["inventory"], payload)
    if operation == "customer.cart.set":
        return svc.cart_line(context["cart"], payload)
    if operation == "customer.cart.delete":
        return svc.cart_line(context["cart"], payload, context["sku_id"])
    if operation == "customer.checkout.create":
        return svc.checkout(context["cart"], payload)
    if operation.startswith("customer.order."):
        return svc.order_action(context["order"], operation.rsplit(".", 1)[1], payload)
    if operation == "merchant.ship":
        return svc.ship(context["order"], payload)
    if operation == "demo.payment":
        return svc.payment_result(context["attempt"], payload)
    if operation == "demo.tracking":
        return svc.tracking(context["shipment"], payload)
    if operation == "demo.expire":
        return svc.expire_orders(payload)
    fail("NOT_FOUND", 404)


def record_failure(db, svc, request, operation, code):
    """Best effort independent audit; an unavailable audit never masks the primary error."""
    if db is None:
        return
    try:
        db.rollback()
        with db.begin():
            db.execute(text("SET LOCAL lock_timeout='2000ms'"))
            db.execute(text("SET LOCAL statement_timeout='2500ms'"))
            db.add(
                BusinessAudit(
                    id=uuid4(),
                    actor_id=svc.actor.id if svc and svc.actor else None,
                    action=operation,
                    request_id=request.state.request_id,
                    safe_metadata={
                        "outcome": "FAILED"
                        if code in {"INTERNAL_ERROR", "OPERATION_BUSY"}
                        else "DENIED",
                        "code": code,
                    },
                    created_at=request.app.state.clock.now(),
                    updated_at=request.app.state.clock.now(),
                    version=1,
                )
            )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def handler(operation, method, path):
    def endpoint(request: Request, **path_parameters):
        write = method != "GET"
        request.state.request_id = str(uuid4())
        db = None
        svc = None
        status = 200
        replay = False
        failure_code = None
        try:
            if (
                request.headers.get("origin") is not None
                and request.headers["origin"] not in request.app.state.settings.cors_allowed_origins
            ):
                fail("CAPABILITY_REQUIRED", 403)
            db = request.app.state.session_factory()
            with db.begin():
                svc = Commerce(db, request.app.state.clock, request, False)
                context = setup_authority(svc, request, operation)
                if write:
                    raw = anyio.from_thread.run(bounded_body, request)
                    svc.acquire_write()
                    context = setup_authority(svc, request, operation)
                svc.now = request.app.state.clock.now()
                if write:
                    payload = body(raw)
                    if operation in {
                        "customer.case.create",
                        "merchant.case.decision",
                        "merchant.inventory.adjust",
                        "customer.order.cancel",
                    } and isinstance(payload, dict):
                        set_context(db, svc.actor, request, payload.get("reason"))
                    query(request)
                    if operation == "login":
                        result, status = svc.login(payload)
                    elif operation == "logout":
                        result, status = mutate(svc, operation, context, payload)
                    else:
                        op = operation + ":" + request.url.path
                        result, status, replay = svc.write_result(
                            op, payload, lambda: mutate(svc, operation, context, payload)
                        )
                else:
                    if request.query_params and operation in {
                        "me",
                        "customer.cart",
                        "merchant.inventory",
                        "catalog.detail",
                        "merchant.product.detail",
                        "customer.checkout.detail",
                        "customer.order.detail",
                        "merchant.order.detail",
                        "customer.shipment",
                        "merchant.shipment",
                    }:
                        fail("INVALID_REQUEST", 400)
                    if not request.query_params and not operation.endswith(
                        ("products", "orders", "shops", "pending")
                    ):
                        pass
                    elif operation.endswith(("detail", "inventory", "cart", "shipment")):
                        if request.query_params:
                            fail("INVALID_REQUEST", 400)
                    result = read(svc, request, operation, context)
                dto = RESPONSES[operation]
                if status < 400 and dto is not None and not replay:
                    result = dto.model_validate(result).model_dump(mode="json")
        except CommerceError as error:
            status = error.status
            result = error.payload(request.state.request_id)
            failure_code = error.code
        except DBAPIError as error:
            if db is not None:
                db.rollback()
            sqlstate = getattr(error.orig, "sqlstate", None)
            status = 409 if sqlstate in {"55P03", "40P01", "40001"} else 500
            failure_code = "OPERATION_BUSY" if status == 409 else "INTERNAL_ERROR"
            result = CommerceError(status, failure_code).payload(request.state.request_id)
        except Exception:
            if db is not None:
                db.rollback()
            status = 500
            failure_code = "INTERNAL_ERROR"
            result = CommerceError(500, "INTERNAL_ERROR").payload(request.state.request_id)
        finally:
            if failure_code is not None:
                record_failure(db, svc, request, operation, failure_code)
            if db is not None:
                db.close()
        response = (
            Response(status_code=204) if status == 204 else JSONResponse(result, status_code=status)
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-Id"] = request.state.request_id
        if replay:
            response.headers["Idempotent-Replay"] = "true"
        if status == 201 and isinstance(result, dict) and result.get("id"):
            if operation == "customer.checkout.create":
                response.headers["Location"] = PREFIX + "/customer/checkouts/" + result["id"]
            elif operation == "merchant.product.create":
                response.headers["Location"] = request.url.path + "/" + result["id"]
            elif operation == "customer.case.create":
                response.headers["Location"] = request.url.path + "/" + result["id"]
            elif operation == "merchant.ship":
                response.headers["Location"] = request.url.path + "/" + result["id"]
        return response

    endpoint.__signature__ = inspect.Signature(
        [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)]
        + [
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=str)
            for name in re.findall(r"{(\w+)}", path)
        ]
    )
    endpoint.__name__ = operation.replace(".", "_")
    return endpoint


ROUTES = [
    ("POST", "/auth/login", "login"),
    ("GET", "/auth/me", "me"),
    ("POST", "/auth/logout", "logout"),
    ("GET", "/catalog/products", "catalog.list"),
    ("GET", "/catalog/products/{product}", "catalog.detail"),
    ("GET", "/merchant/shops", "merchant.shops"),
    ("GET", "/merchant/shops/{shop}/products", "merchant.products"),
    ("POST", "/merchant/shops/{shop}/products", "merchant.product.create"),
    ("GET", "/merchant/shops/{shop}/products/{product}", "merchant.product.detail"),
    ("POST", "/merchant/shops/{shop}/products/{product}/edit", "merchant.product.edit"),
    ("POST", "/merchant/shops/{shop}/products/{product}/publish", "merchant.product.publish"),
    ("POST", "/merchant/shops/{shop}/products/{product}/archive", "merchant.product.archive"),
    ("POST", "/merchant/shops/{shop}/products/{product}/skus", "merchant.product.skus"),
    ("POST", "/merchant/shops/{shop}/products/{product}/skus/{sku}/edit", "merchant.sku.edit"),
    ("GET", "/merchant/shops/{shop}/inventory/{sku}", "merchant.inventory"),
    ("POST", "/merchant/shops/{shop}/inventory/{sku}/adjust", "merchant.inventory.adjust"),
    ("GET", "/customer/cart", "customer.cart"),
    ("POST", "/customer/cart/lines", "customer.cart.set"),
    ("DELETE", "/customer/cart/lines/{sku}", "customer.cart.delete"),
    ("POST", "/customer/checkouts", "customer.checkout.create"),
    ("GET", "/customer/checkouts/{checkout}", "customer.checkout.detail"),
    ("GET", "/customer/orders", "customer.orders"),
    ("GET", "/customer/orders/{order}", "customer.order.detail"),
    ("POST", "/customer/orders/{order}/address", "customer.order.address"),
    ("POST", "/customer/orders/{order}/cancel", "customer.order.cancel"),
    ("POST", "/customer/orders/{order}/payments", "customer.order.payments"),
    ("POST", "/customer/orders/{order}/confirm-receipt", "customer.order.confirm-receipt"),
    ("GET", "/merchant/shops/{shop}/orders", "merchant.orders"),
    ("GET", "/merchant/shops/{shop}/orders/{order}", "merchant.order.detail"),
    ("POST", "/merchant/shops/{shop}/orders/{order}/shipments", "merchant.ship"),
    ("GET", "/customer/orders/{order}/shipments/{shipment}", "customer.shipment"),
    ("GET", "/merchant/shops/{shop}/orders/{order}/shipments/{shipment}", "merchant.shipment"),
]
ROUTES.extend(
    [
        ("POST", "/customer/conversations", "customer.conversation.create"),
        ("GET", "/customer/conversations", "customer.conversations"),
        ("GET", "/merchant/shops/{shop}/conversations", "merchant.conversations"),
        ("GET", "/customer/conversations/{conversation}/messages", "customer.messages"),
        ("POST", "/customer/conversations/{conversation}/messages", "customer.message.create"),
        (
            "GET",
            "/merchant/shops/{shop}/conversations/{conversation}/messages",
            "merchant.messages",
        ),
        (
            "POST",
            "/merchant/shops/{shop}/conversations/{conversation}/messages",
            "merchant.message.create",
        ),
        ("POST", "/customer/orders/{order}/after-sales", "customer.case.create"),
        ("GET", "/customer/orders/{order}/after-sales/{case}", "customer.case.detail"),
        ("GET", "/merchant/shops/{shop}/orders/{order}/after-sales/{case}", "merchant.case.detail"),
        ("POST", "/customer/orders/{order}/after-sales/{case}/withdraw", "customer.case.withdraw"),
        ("POST", "/customer/orders/{order}/after-sales/{case}/return", "customer.case.return"),
        (
            "POST",
            "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/decision",
            "merchant.case.decision",
        ),
        (
            "POST",
            "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/receive-return",
            "merchant.case.receive-return",
        ),
        (
            "POST",
            "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/refunds",
            "merchant.case.refunds",
        ),
    ]
)

for method, path, operation in ROUTES:
    router.add_api_route(
        path,
        handler(operation, method, path),
        methods=[method],
        name=operation,
        response_model=RESPONSES[operation],
        openapi_extra={
            "security": []
            if operation in {"login", "catalog.list", "catalog.detail"}
            else [{"CommerceBearer": []}]
        },
    )
for method, path, operation in [
    ("GET", "/demo/pending", "demo.pending"),
    ("POST", "/demo/payments/{attempt}/result", "demo.payment"),
    ("POST", "/demo/refunds/{attempt}/result", "demo.refund"),
    ("GET", "/demo/shipments", "demo.shipments"),
    ("GET", "/demo/shipments/{shipment}", "demo.shipment"),
    ("POST", "/demo/shipments/{shipment}/events", "demo.tracking"),
    ("POST", "/demo/orders/expire", "demo.expire"),
]:
    demo_router.add_api_route(
        path,
        handler(operation, method, path),
        methods=[method],
        name=operation,
        response_model=RESPONSES[operation],
        openapi_extra={
            "security": []
            if operation in {"login", "catalog.list", "catalog.detail"}
            else [{"CommerceBearer": []}]
        },
    )
