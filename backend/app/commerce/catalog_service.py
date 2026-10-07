"""Shopping operations share commerce authority, mutex and atomic idempotency."""

import base64
import binascii
import hashlib
import io
import warnings

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from app.commerce import inputs as inp
from app.commerce import views
from app.commerce.catalog_models import (
    Category,
    Favorite,
    ProductExperience,
    ProductImage,
    ProductReview,
)
from app.commerce.errors import fail
from app.commerce.models import SKU, Inventory, Order, Product, Shipment, ShipmentLine, Shop
from app.commerce.service import Commerce

MAX_RAW = 3 * 1024 * 1024
MAX_PIXELS = 16000000


class Catalog(Commerce):
    def experience(self, p):
        return self.db.scalar(select(ProductExperience).filter_by(product_id=p.id))

    def eligible(self, p):
        exp = self.experience(p)
        return (
            p.status == "PUBLISHED"
            and self.get(Shop, p.shop_id).status == "ACTIVE"
            and not (exp and exp.moderation_hidden)
        )

    def public_product(self, identifier):
        p = self.get(Product, identifier)
        if not self.eligible(p):
            fail("NOT_FOUND", 404)
        return p

    def card(self, p, merchant=False):
        result = views.product(self.db, p, merchant)
        exp = self.experience(p)
        category = self.db.get(Category, exp.category_id) if exp and exp.category_id else None
        rating, review_count = self.db.execute(
            select(func.avg(ProductReview.rating), func.count(ProductReview.id)).where(
                ProductReview.product_id == p.id, ProductReview.visible.is_(True)
            )
        ).one()
        result.update(
            category_id=str(category.id) if category else None,
            category_name=category.name if category else None,
            images=[
                {
                    "id": str(i.id),
                    "url": "/api/commerce/v1/shopping/images/" + str(i.id),
                    "alt": i.alt,
                    "position": i.position,
                }
                for i in self.db.scalars(
                    select(ProductImage)
                    .options(load_only(ProductImage.id, ProductImage.alt, ProductImage.position))
                    .filter_by(product_id=p.id)
                    .order_by(ProductImage.position)
                )
            ],
            rating=float(rating) if rating is not None else None,
            review_count=review_count,
        )
        return result

    def review_view(self, r, public=False):
        order = self.get(Order, r.order_id)
        return {
            "id": str(r.id),
            "product_id": str(r.product_id),
            "shop_id": str(r.shop_id),
            "order_id": str(r.order_id) if not public else "",
            "order_line_id": str(r.order_line_id) if not public else "",
            "rating": r.rating,
            "body": r.body,
            "reply": r.reply,
            "visible": r.visible,
            "version": r.version,
            "created_at": views.iso(r.created_at),
            "updated_at": views.iso(r.updated_at),
            "financial_status": order.financial_status,
        }

    def favorite_view(self, row):
        p = self.get(Product, row.product_id)
        available = self.eligible(p)
        return {
            "id": str(row.id),
            "product_id": str(row.product_id),
            "active": row.active,
            "version": row.version,
            "purchasable": available,
            "product": self.card(p) if available else None,
        }

    def set_favorite(self, body):
        inp.fields(body, ["product_id", "active"])
        pid, active = inp.identifier(body["product_id"]), inp.boolean(body["active"])
        row = self.db.scalar(select(Favorite).filter_by(customer_id=self.actor.id, product_id=pid))
        if active:
            self.public_product(pid)
        elif row is None:
            fail("NOT_FOUND", 404)
        if row is None:
            row = self.new(Favorite, customer_id=self.actor.id, product_id=pid, active=active)
        elif row.active != active:
            row.active = active
            self.bump(row)
        self.audit("catalog.favorite.set", row.id)
        return self.favorite_view(row), 200

    def set_experience(self, p, body):
        inp.fields(body, ["expected_version", "category_id"])
        self.version(p, body)
        cid = inp.identifier(body["category_id"]) if body["category_id"] is not None else None
        if cid is not None and not self.get(Category, cid).active:
            fail("INVALID_REQUEST", 400)
        exp = self.experience(p)
        if exp is None:
            self.new(ProductExperience, product_id=p.id, category_id=cid, moderation_hidden=False)
        else:
            exp.category_id = cid
            self.bump(exp)
        self.bump(p)
        self.audit("catalog.experience.set", p.id)
        self.db.flush()
        return self.card(p, True), 200

    def upload(self, p, body):
        inp.fields(body, ["expected_version", "data_base64", "alt"])
        self.version(p, body)
        alt = inp.string(body["alt"], 0, 200)
        value = body["data_base64"]
        if not isinstance(value, str) or len(value) > ((MAX_RAW + 2) // 3) * 4:
            fail("INVALID_IMAGE", 400)
        try:
            raw = base64.b64decode(value, validate=True)
            if not 0 < len(raw) <= MAX_RAW:
                fail("INVALID_IMAGE", 400)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as probe:
                    fmt = probe.format
                    if (
                        fmt not in {"PNG", "JPEG", "WEBP"}
                        or probe.width * probe.height > MAX_PIXELS
                        or getattr(probe, "n_frames", 1) != 1
                    ):
                        fail("INVALID_IMAGE", 400)
                    probe.verify()
                with Image.open(io.BytesIO(raw)) as source:
                    source.load()
                    canonical = Image.new(
                        "RGBA"
                        if source.mode in {"RGBA", "LA"} or "transparency" in source.info
                        else "RGB",
                        source.size,
                    )
                    canonical.paste(source.convert(canonical.mode))
                    output = io.BytesIO()
                    canonical.save(output, format="PNG")
                    content = output.getvalue()
                    width, height = canonical.size
            if len(content) > 8 * 1024 * 1024:
                fail("INVALID_IMAGE", 400)
        except (
            ValueError,
            binascii.Error,
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            EOFError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            fail("INVALID_IMAGE", 400)
        settings = self.request.app.state.settings
        if settings.commerce_public_demo:
            stored = self.db.scalar(
                select(func.coalesce(func.sum(func.octet_length(ProductImage.content)), 0))
            )
            if stored + len(content) > settings.commerce_image_quota_bytes:
                fail("IMAGE_STORAGE_LIMIT", 409)
        used = set(
            self.db.scalars(select(ProductImage.position).where(ProductImage.product_id == p.id))
        )
        position = next((n for n in range(8) if n not in used), None)
        if position is None:
            fail("IMAGE_LIMIT", 409)
        image = self.new(
            ProductImage,
            product_id=p.id,
            position=position,
            alt=alt,
            mime="image/png",
            width=width,
            height=height,
            digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.bump(p)
        self.audit("catalog.image.upload", image.id)
        return self.card(p, True), 201

    def delete_image(self, p, image, body):
        inp.fields(body, ["expected_version"])
        self.version(p, body)
        self.db.delete(image)
        self.bump(p)
        self.audit("catalog.image.delete", image.id)
        self.db.flush()
        return self.card(p, True), 200

    def create_review(self, order, line, body):
        inp.fields(body, ["rating", "body"])
        rating, text = inp.integer(body["rating"], 1, 5), inp.string(body["body"], 1, 2000)
        shipments = list(
            self.db.scalars(
                select(Shipment)
                .join(ShipmentLine, ShipmentLine.shipment_id == Shipment.id)
                .where(ShipmentLine.order_line_id == line.id)
            )
        )
        if (
            order.status != "COMPLETED"
            or line.shipped_qty <= 0
            or not shipments
            or any(s.status != "DELIVERED" or s.delivered_at is None for s in shipments)
        ):
            fail("INVALID_STATE", 409)
        if self.db.scalar(select(ProductReview).filter_by(order_line_id=line.id)):
            fail("REVIEW_EXISTS", 409)
        sku = self.get(SKU, line.sku_id)
        review = self.new(
            ProductReview,
            customer_id=self.actor.id,
            order_id=order.id,
            order_line_id=line.id,
            product_id=sku.product_id,
            shop_id=order.shop_id,
            rating=rating,
            body=text,
            reply=None,
            visible=True,
        )
        self.audit("catalog.review.create", review.id)
        return self.review_view(review), 201

    def edit_review(self, row, body, reply=False):
        inp.fields(
            body, ["expected_version", "body"] if reply else ["expected_version", "rating", "body"]
        )
        self.version(row, body)
        text = inp.string(body["body"], 1, 2000)
        if reply:
            row.reply = text
        else:
            row.rating = inp.integer(body["rating"], 1, 5)
            row.body = text
        self.bump(row)
        self.audit("catalog.review.reply" if reply else "catalog.review.edit", row.id)
        return self.review_view(row), 200

    def shopping_products(self, values):
        minimum = maximum = None
        for key in ("min_price_minor", "max_price_minor"):
            if key in values and (
                not values[key].isascii()
                or not values[key].isdecimal()
                or int(values[key]) > 100000000
            ):
                fail("INVALID_REQUEST", 400)
        minimum = int(values["min_price_minor"]) if "min_price_minor" in values else None
        maximum = int(values["max_price_minor"]) if "max_price_minor" in values else None
        if minimum is not None and maximum is not None and minimum > maximum:
            fail("INVALID_REQUEST", 400)
        if values.get("in_stock", "false") not in {"true", "false"} or values.get(
            "sort", "newest"
        ) not in {"newest", "price_asc", "price_desc", "rating"}:
            fail("INVALID_REQUEST", 400)
        shop = inp.identifier(values["shop_id"]) if "shop_id" in values else None
        category = inp.identifier(values["category_id"]) if "category_id" in values else None
        q = inp.string(values.get("q", ""), 0, 200).casefold()
        eligible = (
            select(
                SKU.product_id.label("product_id"), func.min(SKU.unit_price_minor).label("price")
            )
            .join(Inventory, Inventory.sku_id == SKU.id)
            .where(SKU.active.is_(True))
        )
        if minimum is not None:
            eligible = eligible.where(SKU.unit_price_minor >= minimum)
        if maximum is not None:
            eligible = eligible.where(SKU.unit_price_minor <= maximum)
        if values.get("in_stock") == "true":
            eligible = eligible.where(Inventory.on_hand > Inventory.reserved)
        eligible = eligible.group_by(SKU.product_id).subquery()
        ratings = (
            select(
                ProductReview.product_id.label("product_id"),
                func.avg(ProductReview.rating).label("rating"),
            )
            .where(ProductReview.visible.is_(True))
            .group_by(ProductReview.product_id)
            .subquery()
        )
        statement = (
            select(Product)
            .join(Shop, Shop.id == Product.shop_id)
            .join(eligible, eligible.c.product_id == Product.id)
            .outerjoin(ProductExperience, ProductExperience.product_id == Product.id)
            .outerjoin(ratings, ratings.c.product_id == Product.id)
            .where(
                Product.status == "PUBLISHED",
                Shop.status == "ACTIVE",
                func.coalesce(ProductExperience.moderation_hidden, False).is_(False),
            )
        )
        if shop:
            statement = statement.where(Product.shop_id == shop)
        if category:
            statement = statement.where(ProductExperience.category_id == category)
        if q:
            statement = statement.where(
                func.lower(Product.title + " " + Product.description).contains(q, autoescape=True)
            )
        sort = values.get("sort", "newest")
        order = (
            eligible.c.price.asc()
            if sort == "price_asc"
            else eligible.c.price.desc()
            if sort == "price_desc"
            else func.coalesce(ratings.c.rating, 0).desc()
            if sort == "rating"
            else Product.created_at.desc()
        )
        limit, offset = int(values.get("limit", 20)), int(values.get("offset", 0))
        return [
            self.card(p)
            for p in self.db.scalars(
                statement.order_by(order, Product.id).limit(limit + 1).offset(offset)
            )
        ]
