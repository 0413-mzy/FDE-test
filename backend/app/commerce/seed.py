"""Explicit fictional seed. Re-running never changes existing business records."""

import os
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commerce.history import set_context
from app.commerce.models import SKU, Cart, CommerceAccount, Inventory, Product, Shop, ShopMembership
from app.core.security import PASSWORD_HASHER
from app.db.connection import product_engine


def seed_id(name):
    return uuid5(NAMESPACE_URL, "fde-commerce-v1/" + name)


def seed_commerce(db: Session, password: str, now=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("DEMO_SEED_PASSWORD must contain 12..128 characters")
    now = now or datetime.now(UTC)
    with db.begin():
        set_context(db, action="DEMO_SEED")
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(current_schema() || '-commerce-v1',0))"
            )
        )

        def add(cls, seed_name, **values):
            identifier = seed_id(seed_name)
            row = db.get(cls, identifier)
            if row is None:
                row = cls(id=identifier, created_at=now, updated_at=now, **values)
                db.add(row)
                db.flush()
            return row

        for name in ["customer.a", "customer.b", "owner.a", "owner.b", "staff.a", "demo", "dual.a"]:
            account = add(
                CommerceAccount,
                "account/" + name,
                username=name,
                password_hash=PASSWORD_HASHER.hash(password),
                active=True,
                customer_enabled=name.startswith("customer") or name == "dual.a",
                demo_enabled=name == "demo",
            )
            if account.customer_enabled:
                add(Cart, "cart/" + name, customer_id=account.id)
        for name in ["shopA", "shopB"]:
            add(Shop, "shop/" + name, name=name, status="ACTIVE")
        for username, shop, role in [
            ("owner.a", "shopA", "OWNER"),
            ("owner.b", "shopB", "OWNER"),
            ("staff.a", "shopA", "STAFF"),
            ("dual.a", "shopA", "OWNER"),
        ]:
            add(
                ShopMembership,
                "membership/" + username + "/" + shop,
                account_id=seed_id("account/" + username),
                shop_id=seed_id("shop/" + shop),
                role=role,
                active=True,
            )
        for code, shop, price, stock in [
            ("A", "shopA", 1000, 5),
            ("B", "shopB", 2000, 3),
            ("L", "shopA", 500, 1),
            ("Z", "shopA", 1000, 0),
        ]:
            product = add(
                Product,
                "product/" + code,
                shop_id=seed_id("shop/" + shop),
                title="Fictional Product " + code,
                description="Fictional commerce simulation product",
                status="PUBLISHED",
            )
            sku = add(
                SKU,
                "sku/" + code,
                product_id=product.id,
                shop_id=product.shop_id,
                sku_code=code,
                options={},
                unit_price_minor=price,
                active=True,
            )
            add(Inventory, "inventory/" + code, sku_id=sku.id, on_hand=stock, reserved=0)


def main():
    if os.environ.get("APP_ENV") not in {"development", "test"}:
        raise SystemExit("Explicit APP_ENV development/test is required")
    password = os.environ.get("DEMO_SEED_PASSWORD", "")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    engine = product_engine(url)
    try:
        with Session(engine) as db:
            seed_commerce(db, password)
        print("Fictional commerce seed ensured; existing records preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
