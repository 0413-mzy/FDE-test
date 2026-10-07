"""Shopping HTTP endpoints, bounded upload and authorization before decoding."""

import inspect
import json
from uuid import uuid4

import anyio
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse, Response

from app.commerce.catalog_models import Category, Favorite, ProductImage, ProductReview
from app.commerce.catalog_schemas import (
    CategoryView,
    FavoriteView,
    MerchantProductCardView,
    ProductCardView,
    ReviewView,
    ShopView,
)
from app.commerce.catalog_service import MAX_RAW, Catalog
from app.commerce.errors import CommerceError, fail
from app.commerce.models import OrderLine, Product, Shop
from app.commerce.router import path_id, query, record_failure
from app.commerce.schemas import Page

router = APIRouter(prefix="/api/commerce/v1", tags=["shopping"])


async def bounded(request, max_size=65536):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > max_size:
            fail("INVALID_REQUEST", 400)

    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                fail("INVALID_REQUEST", 400)
            result[k] = v
        return result

    try:
        return json.loads(
            raw or b"{}",
            object_pairs_hook=unique,
            parse_constant=lambda _: fail("INVALID_REQUEST", 400),
        )
    except (ValueError, UnicodeDecodeError):
        fail("INVALID_REQUEST", 400)


def authority(svc, request, op):
    context = {}
    if op.startswith("customer."):
        svc.auth("customer")
    elif op.startswith("merchant."):
        svc.auth("merchant", path_id(request, "shop_id"), owner=op != "merchant.reviews")
        if svc.shop.status != "ACTIVE" and request.method != "GET":
            fail("SHOP_SUSPENDED", 409)
    if "product_id" in request.path_params:
        context["product"] = (
            svc.own_product(path_id(request, "product_id"))
            if op.startswith("merchant.")
            else svc.public_product(path_id(request, "product_id"))
        )
    if "image_id" in request.path_params:
        image = svc.get(ProductImage, path_id(request, "image_id"))
        p = svc.get(Product, image.product_id)
        if op == "image":
            if not svc.eligible(p):
                svc.auth("merchant", p.shop_id, owner=True)
                # Authenticated owners can inspect private drafts, never public cache.
        elif image.product_id != context["product"].id:
            fail("NOT_FOUND", 404)
        context["image"] = image
    if op in {"customer.review.create", "customer.review.get"}:
        order = svc.own_order(path_id(request, "order_id"))
        line = svc.get(OrderLine, path_id(request, "line_id"))
        if line.order_id != order.id:
            fail("NOT_FOUND", 404)
        context.update(order=order, line=line)
    if "review_id" in request.path_params:
        review = svc.get(ProductReview, path_id(request, "review_id"))
        if (
            op.startswith("customer.")
            and review.customer_id != svc.actor.id
            or op.startswith("merchant.")
            and review.shop_id != svc.shop.id
        ):
            fail("NOT_FOUND", 404)
        context["review"] = review
    return context


def read(svc, request, op, c):
    extras = (
        ("q", "shop_id", "category_id", "min_price_minor", "max_price_minor", "in_stock", "sort")
        if op == "products"
        else ()
    )
    limit, offset, values = query(request, extras)
    if (
        op in {"detail", "merchant.experience", "image", "customer.review.get"}
        and request.query_params
    ):
        fail("INVALID_REQUEST", 400)
    if op == "customer.review.get":
        review = svc.db.scalar(
            select(ProductReview).filter_by(order_line_id=c["line"].id, customer_id=svc.actor.id)
        )
        if review is None:
            fail("NOT_FOUND", 404)
        return svc.review_view(review), ReviewView
    if op == "products":
        items = svc.shopping_products(values)
        return {
            "items": items[:limit],
            "limit": limit,
            "offset": offset,
            "has_more": len(items) > limit,
        }, ProductCardView
    if op in {"detail", "merchant.experience"}:
        return svc.card(
            c["product"], op.startswith("merchant.")
        ), MerchantProductCardView if op.startswith("merchant.") else ProductCardView
    if op == "categories":
        items = [
            {"id": str(r.id), "name": r.name, "active": r.active, "version": r.version}
            for r in svc.db.scalars(
                select(Category)
                .filter_by(active=True)
                .order_by(Category.name, Category.id)
                .limit(limit + 1)
                .offset(offset)
            )
        ]
        dto = CategoryView
    elif op == "shops":
        items = [
            {"id": str(r.id), "name": r.name, "status": r.status, "version": r.version}
            for r in svc.db.scalars(
                select(Shop)
                .filter_by(status="ACTIVE")
                .order_by(Shop.name, Shop.id)
                .limit(limit + 1)
                .offset(offset)
            )
        ]
        dto = ShopView
    elif op == "customer.favorites":
        items = [
            svc.favorite_view(r)
            for r in svc.db.scalars(
                select(Favorite)
                .filter_by(customer_id=svc.actor.id, active=True)
                .order_by(Favorite.created_at.desc(), Favorite.id)
                .limit(limit + 1)
                .offset(offset)
            )
        ]
        dto = FavoriteView
    else:
        statement = select(ProductReview).order_by(
            ProductReview.created_at.desc(), ProductReview.id
        )
        if op == "reviews":
            statement = statement.filter_by(product_id=c["product"].id, visible=True)
        else:
            statement = statement.filter_by(shop_id=svc.shop.id)
        items = [
            svc.review_view(r, op == "reviews")
            for r in svc.db.scalars(statement.limit(limit + 1).offset(offset))
        ]
        dto = ReviewView
    return {
        "items": items[:limit],
        "limit": limit,
        "offset": offset,
        "has_more": len(items) > limit,
    }, dto


def mutate(svc, op, c, b):
    if op == "customer.favorite":
        return svc.set_favorite(b), FavoriteView
    if op == "merchant.experience.set":
        return svc.set_experience(c["product"], b), MerchantProductCardView
    if op == "merchant.image.upload":
        return svc.upload(c["product"], b), MerchantProductCardView
    if op == "merchant.image.delete":
        return svc.delete_image(c["product"], c["image"], b), MerchantProductCardView
    if op in {"customer.review.create", "customer.review.get"}:
        return svc.create_review(c["order"], c["line"], b), ReviewView
    return svc.edit_review(c["review"], b, op == "merchant.review.reply"), ReviewView


def endpoint(op, method, path):
    def run(request: Request, **params):
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
            with db.begin():
                svc = Catalog(db, request.app.state.clock, request)
                c = authority(svc, request, op)
                if method != "GET":
                    b = anyio.from_thread.run(
                        bounded,
                        request,
                        ((MAX_RAW + 2) // 3) * 4 + 8192 if op == "merchant.image.upload" else 65536,
                    )
                    svc.acquire_write()
                    c = authority(svc, request, op)
                    if request.query_params:
                        fail("INVALID_REQUEST", 400)

                    def action():
                        (value, code), dto = mutate(svc, op, c, b)
                        return dto.model_validate(value).model_dump(mode="json"), code

                    result, status, replay = svc.write_result(
                        "catalog:" + op + ":" + request.url.path, b, action
                    )
                elif op == "image":
                    image = c["image"]
                    return Response(
                        image.content,
                        media_type=image.mime,
                        headers={
                            "X-Content-Type-Options": "nosniff",
                            "Cache-Control": "no-store",
                            "X-Request-Id": request.state.request_id,
                        },
                    )
                else:
                    result, dto = read(svc, request, op, c)
                    if "items" in result:
                        result["items"] = [
                            dto.model_validate(i).model_dump(mode="json") for i in result["items"]
                        ]
                    else:
                        result = dto.model_validate(result).model_dump(mode="json")
        except CommerceError as error:
            status = error.status
            failure = error.code
            result = error.payload(request.state.request_id)
        except DBAPIError as error:
            status = (
                409 if getattr(error.orig, "sqlstate", None) in {"55P03", "40P01", "40001"} else 500
            )
            failure = "OPERATION_BUSY" if status == 409 else "INTERNAL_ERROR"
            result = CommerceError(status, failure).payload(request.state.request_id)
        except Exception:
            status = 500
            failure = "INTERNAL_ERROR"
            result = CommerceError(status, failure).payload(request.state.request_id)
        finally:
            if failure and db is not None:
                record_failure(db, svc, request, op, failure)
            if db is not None:
                db.close()
        response = JSONResponse(
            result,
            status_code=status,
            headers={"Cache-Control": "no-store", "X-Request-Id": request.state.request_id},
        )
        if replay:
            response.headers["Idempotent-Replay"] = "true"
        return response

    run.__signature__ = inspect.Signature(
        [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)]
        + [
            inspect.Parameter(part[1:-1], inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
            for part in path.split("/")
            if part.startswith("{")
        ]
    )
    models = {
        "categories": Page[CategoryView],
        "shops": Page[ShopView],
        "products": Page[ProductCardView],
        "detail": ProductCardView,
        "reviews": Page[ReviewView],
        "customer.favorites": Page[FavoriteView],
        "customer.favorite": FavoriteView,
        "merchant.reviews": Page[ReviewView],
        "customer.review.get": ReviewView,
        "customer.review.create": ReviewView,
        "customer.review.edit": ReviewView,
        "merchant.review.reply": ReviewView,
        "merchant.experience": MerchantProductCardView,
        "merchant.experience.set": MerchantProductCardView,
        "merchant.image.upload": MerchantProductCardView,
        "merchant.image.delete": MerchantProductCardView,
    }
    router.add_api_route(
        path,
        run,
        methods=[method],
        name="catalog." + op,
        response_model=models.get(op),
        openapi_extra={
            "security": (
                [{}, {"CommerceBearer": []}]
                if op == "image"
                else [{"CommerceBearer": []}]
                if op.startswith(("customer.", "merchant."))
                else []
            )
        },
        responses={200: {"content": {"image/png": {}}}} if op == "image" else None,
    )


for operation, method, path in [
    ("customer.review.get", "GET", "/customer/orders/{order_id}/lines/{line_id}/review"),
    ("categories", "GET", "/shopping/categories"),
    ("shops", "GET", "/shopping/shops"),
    ("products", "GET", "/shopping/products"),
    ("detail", "GET", "/shopping/products/{product_id}"),
    ("reviews", "GET", "/shopping/products/{product_id}/reviews"),
    ("image", "GET", "/shopping/images/{image_id}"),
    ("customer.favorites", "GET", "/customer/favorites"),
    ("customer.favorite", "POST", "/customer/favorites"),
    ("customer.review.create", "POST", "/customer/orders/{order_id}/lines/{line_id}/review"),
    ("customer.review.edit", "POST", "/customer/reviews/{review_id}/edit"),
    ("merchant.reviews", "GET", "/merchant/shops/{shop_id}/reviews"),
    ("merchant.review.reply", "POST", "/merchant/shops/{shop_id}/reviews/{review_id}/reply"),
    ("merchant.experience", "GET", "/merchant/shops/{shop_id}/products/{product_id}/experience"),
    (
        "merchant.experience.set",
        "POST",
        "/merchant/shops/{shop_id}/products/{product_id}/experience",
    ),
    (
        "merchant.image.upload",
        "POST",
        "/merchant/shops/{shop_id}/products/{product_id}/experience/images",
    ),
    (
        "merchant.image.delete",
        "POST",
        "/merchant/shops/{shop_id}/products/{product_id}/experience/images/{image_id}/delete",
    ),
]:
    endpoint(operation, method, path)
