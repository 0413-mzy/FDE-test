"""Real PostgreSQL shopping ownership, images, privacy and atomic regressions."""

import base64
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commerce.catalog_models import Category, ProductExperience, ProductImage, ProductReview
from app.commerce.models import SKU, Order, OrderLine, Product, Shipment, ShipmentLine
from app.commerce.seed import seed_commerce, seed_id
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.database
PASSWORD = "catalog-test-secret-123"
PREFIX = "/api/commerce/v1"


@pytest.fixture
def catalog(database):
    engine, _, _ = database
    with Session(engine) as db:
        seed_commerce(db, PASSWORD)
    app = create_app(Settings(app_env="test"), session_factory=lambda: Session(engine))
    from app.commerce.catalog_router import router

    if not any(getattr(r, "name", "") == "catalog.products" for r in app.routes):
        app.include_router(router)
    with TestClient(app) as client:
        yield client, engine


def login(client, name):
    r = client.post(PREFIX + "/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def post(client, path, headers, body, key=None):
    return client.post(
        PREFIX + path, headers={**headers, "Idempotency-Key": key or str(uuid4())}, json=body
    )


def picture():
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


def product_path():
    return (
        "/merchant/shops/"
        + str(seed_id("shop/shopA"))
        + "/products/"
        + str(seed_id("product/A"))
        + "/experience"
    )


def test_images_owner_canonical_privacy_history_rollback(catalog):
    client, engine = catalog
    owner = login(client, "owner.a")
    staff = login(client, "staff.a")
    other = login(client, "owner.b")
    path = product_path()
    body = {"expected_version": 1, "data_base64": picture(), "alt": "Red"}
    for headers, code in [(staff, 403), (other, 404), ({}, 401)]:
        denied = post(client, path + "/images", headers, body)
        assert denied.status_code == code, denied.text
    invalid = post(
        client,
        path + "/images",
        owner,
        {**body, "data_base64": base64.b64encode(b"<svg/>").decode()},
    )
    assert invalid.status_code == 400, invalid.text
    uploaded = post(client, path + "/images", owner, body, "picture-one")
    assert uploaded.status_code == 201, uploaded.text
    replay = post(client, path + "/images", owner, body, "picture-one")
    assert replay.status_code == 200 and replay.json() == uploaded.json()
    image = uploaded.json()["images"][0]
    response = client.get(image["url"])
    assert response.status_code == 200 and response.headers["x-content-type-options"] == "nosniff"
    with Session(engine) as db:
        assert len(list(db.scalars(select(ProductImage)))) == 1
        p = db.get(Product, seed_id("product/A"))
        assert p.version == 2
        row = db.execute(
            text(
                "SELECT after_data FROM commerce_record_history WHERE "
                "entity_table='commerce_product_images'"
            )
        ).scalar_one()
        assert "content" not in row and row["digest"]
        exp = ProductExperience(product_id=p.id, moderation_hidden=True)
        db.add(exp)
        db.commit()
    assert client.get(image["url"]).status_code == 401
    assert client.get(image["url"], headers=owner).status_code == 200
    assert client.get(PREFIX + "/shopping/products/" + str(seed_id("product/A"))).status_code == 404
    # A forced downstream failure must roll back the already-created image and product bump.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_image_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.action='catalog.image.upload' THEN "
                "RAISE EXCEPTION 'forced'; END IF; RETURN NEW; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_image_audit BEFORE INSERT ON commerce_business_audits "
                "FOR EACH ROW EXECUTE FUNCTION reject_image_audit()"
            )
        )
    failed = post(client, path + "/images", owner, {**body, "expected_version": 2})
    assert failed.status_code == 500, failed.text
    with Session(engine) as db:
        assert len(list(db.scalars(select(ProductImage)))) == 1
        assert db.get(Product, seed_id("product/A")).version == 2


def test_search_same_sku_category_stock_and_private_favorites(catalog):
    client, engine = catalog
    with Session(engine) as db:
        p = db.get(Product, seed_id("product/A"))
        db.get(SKU, seed_id("sku/A")).unit_price_minor = 100
        sku = SKU(
            product_id=p.id,
            shop_id=p.shop_id,
            sku_code="HIGH",
            options={"variant": "high"},
            unit_price_minor=10000,
            currency="CNY",
            active=True,
        )
        db.add(sku)
        db.flush()
        from app.commerce.models import Inventory

        db.add(Inventory(sku_id=sku.id, on_hand=2, reserved=0))
        cat = Category(name="Test category", active=True)
        db.add(cat)
        db.flush()
        cid = str(cat.id)
        db.commit()
    products = client.get(
        PREFIX + "/shopping/products",
        params={
            "shop_id": str(seed_id("shop/shopA")),
            "q": "Product A",
            "min_price_minor": "500",
            "max_price_minor": "5000",
        },
    ).json()
    assert products["items"] == []
    first = client.get(PREFIX + "/shopping/products?limit=1&offset=0").json()
    second = client.get(PREFIX + "/shopping/products?limit=1&offset=1").json()
    assert len(first["items"]) == len(second["items"]) == 1 and first["has_more"]
    assert first["items"][0]["id"] != second["items"][0]["id"]
    owner = login(client, "owner.a")
    assigned = post(client, product_path(), owner, {"expected_version": 1, "category_id": cid})
    assert assigned.status_code == 200, assigned.text
    filtered = client.get(
        PREFIX + "/shopping/products", params={"category_id": cid, "in_stock": "true"}
    ).json()["items"]
    assert len(filtered) == 1 and filtered[0]["category_name"] == "Test category"
    assert (
        client.get(PREFIX + "/shopping/products?min_price_minor=20&max_price_minor=10").status_code
        == 400
    )
    assert client.get(PREFIX + "/shopping/products?sort=bad").status_code == 400
    a, b = login(client, "customer.a"), login(client, "customer.b")
    body = {"product_id": str(seed_id("product/A")), "active": True}
    favorite = post(client, "/customer/favorites", a, body, "favorite")
    assert favorite.status_code == 200, favorite.text
    assert post(client, "/customer/favorites", a, body, "favorite").json() == favorite.json()
    assert client.get(PREFIX + "/customer/favorites", headers=b).json()["items"] == []
    with Session(engine) as db:
        db.get(Product, seed_id("product/A")).status = "ARCHIVED"
        db.commit()
    hidden = client.get(PREFIX + "/customer/favorites", headers=a).json()["items"][0]
    assert hidden["product"] is None and not hidden["purchasable"]
    assert post(client, "/customer/favorites", b, body).status_code == 404


def test_review_purchase_ownership_duplicate_edit_reply(catalog):
    client, engine = catalog
    customer = login(client, "customer.a")
    other = login(client, "customer.b")
    owner = login(client, "owner.a")
    order_id, line_id = uuid4(), uuid4()
    with Session(engine) as db:
        order = Order(
            id=order_id,
            customer_id=seed_id("account/customer.a"),
            shop_id=seed_id("shop/shopA"),
            checkout_id=None,
            status="READY_TO_SHIP",
            financial_status="PAID",
            total_minor=1000,
            currency="CNY",
            address_revision=1,
            address_snapshot={},
            payment_deadline=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
        # A genuine checkout is required by commerce FK; create minimal persisted business snapshot.
        from app.commerce.models import Checkout

        checkout = Checkout(
            customer_id=order.customer_id,
            cart_id=seed_id("cart/customer.a"),
            source_cart_version=1,
            result_cart_version=2,
            address_snapshot={},
        )
        db.add(checkout)
        db.flush()
        order.checkout_id = checkout.id
        db.add(order)
        db.flush()
        line = OrderLine(
            id=line_id,
            order_id=order_id,
            shop_id=order.shop_id,
            sku_id=seed_id("sku/A"),
            product_title_snapshot="A",
            options_snapshot={},
            unit_price_minor=1000,
            quantity=1,
        )
        db.add(line)
        db.commit()
    path = f"/customer/orders/{order_id}/lines/{line_id}/review"
    body = {"rating": 5, "body": "Purchased product"}
    assert post(client, path, other, body).status_code == 404
    assert post(client, path, customer, body).status_code == 409
    with Session(engine) as db:
        db.get(Order, order_id).status = "COMPLETED"
        db.commit()
    # Whole-order completion can include a refunded, never-shipped line.
    assert post(client, path, customer, body).status_code == 409
    from datetime import UTC, datetime

    with Session(engine) as db:
        db.get(OrderLine, line_id).shipped_qty = 1
        shipment = Shipment(
            order_id=order_id,
            tracking_number="REVIEW-" + str(uuid4()),
            status="DELIVERED",
            shipped_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
        )
        db.add(shipment)
        db.flush()
        db.add(
            ShipmentLine(
                order_id=order_id, shipment_id=shipment.id, order_line_id=line_id, quantity=1
            )
        )
        db.commit()
    assert post(client, path, customer, {**body, "rating": 6}).status_code == 400
    review = post(client, path, customer, body, "review")
    assert review.status_code == 201, review.text
    assert post(client, path, customer, body, "review").json() == review.json()
    assert post(client, path, customer, body).status_code == 409
    current = client.get(PREFIX + path, headers=customer)
    assert current.status_code == 200 and current.json() == review.json()
    assert client.get(PREFIX + path, headers=other).status_code == 404
    rid = review.json()["id"]
    edit = f"/customer/reviews/{rid}/edit"
    assert (
        post(client, edit, other, {"expected_version": 1, "rating": 4, "body": "edit"}).status_code
        == 404
    )
    edited = post(client, edit, customer, {"expected_version": 1, "rating": 4, "body": "edit"})
    assert edited.status_code == 200, edited.text
    reply = post(
        client,
        f"/merchant/shops/{seed_id('shop/shopA')}/reviews/{rid}/reply",
        owner,
        {"expected_version": 2, "body": "Thanks"},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["reply"] == "Thanks"
    public = client.get(PREFIX + f"/shopping/products/{seed_id('product/A')}/reviews").json()[
        "items"
    ][0]
    assert public["order_id"] == "" and public["rating"] == 4
    with Session(engine) as db:
        row = db.get(ProductReview, __import__("uuid").UUID(rid))
        row.visible = False
        db.commit()
    assert (
        client.get(PREFIX + f"/shopping/products/{seed_id('product/A')}/reviews").json()["items"]
        == []
    )


def test_image_bounds_limit_delete_and_competing_versions(catalog):
    import struct
    import zlib
    from concurrent.futures import ThreadPoolExecutor

    client, engine = catalog
    owner = login(client, "owner.a")
    path = product_path()
    raw = bytearray(base64.b64decode(picture()))
    raw[16:20] = struct.pack(">I", 16000001)
    raw[20:24] = struct.pack(">I", 1)
    raw[29:33] = struct.pack(">I", zlib.crc32(raw[12:29]))
    for value in [base64.b64encode(raw).decode(), "a" * (4 * 1024 * 1024 + 4), "???"]:
        response = post(
            client,
            path + "/images",
            owner,
            {"expected_version": 1, "data_base64": value, "alt": ""},
        )
        assert response.status_code == 400, response.text
    body = {"expected_version": 1, "data_base64": picture(), "alt": ""}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(client, path + "/images", owner, body), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    version = 2
    for _ in range(7):
        response = post(client, path + "/images", owner, {**body, "expected_version": version})
        assert response.status_code == 201, response.text
        version = response.json()["version"]
    full = post(client, path + "/images", owner, {**body, "expected_version": version})
    assert full.status_code == 409 and full.json()["error"]["code"] == "IMAGE_LIMIT"
    image = response.json()["images"][0]
    deleted = post(
        client, path + "/images/" + image["id"] + "/delete", owner, {"expected_version": version}
    )
    assert deleted.status_code == 200 and len(deleted.json()["images"]) == 7
    assert client.get(image["url"]).status_code == 404
    refill = post(
        client, path + "/images", owner, {**body, "expected_version": deleted.json()["version"]}
    )
    assert refill.status_code == 201 and len(refill.json()["images"]) == 8
    with Session(engine) as db:
        count = db.scalar(text("SELECT count(*) FROM commerce_product_images"))
        assert count == 8
