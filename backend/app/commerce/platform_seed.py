"""Explicit platform bootstrap; never promote or modify an existing account."""

import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commerce.history import set_context
from app.commerce.models import CommerceAccount
from app.commerce.platform_models import PlatformRole
from app.commerce.seed import seed_id
from app.core.security import PASSWORD_HASHER
from app.db.connection import product_engine


def seed_platform(db, password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("DEMO_SEED_PASSWORD must contain 12..128 characters")
    with db.begin():
        set_context(db, action="PLATFORM_SEED")
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(current_schema() || '-commerce-v1',0))"
            )
        )
        existing = db.scalar(select(CommerceAccount).where(CommerceAccount.username == "platform"))
        if existing is not None:
            return
        account = CommerceAccount(
            id=seed_id("account/platform"),
            username="platform",
            password_hash=PASSWORD_HASHER.hash(password),
            active=True,
            customer_enabled=False,
            demo_enabled=False,
        )
        db.add(account)
        db.flush()
        db.add(PlatformRole(account_id=account.id, active=True))


def main():
    if os.environ.get("APP_ENV") not in {"development", "test"}:
        raise SystemExit("Explicit APP_ENV development/test is required")
    engine = product_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as db:
            seed_platform(db, os.environ.get("DEMO_SEED_PASSWORD", ""))
        print("Independent platform seed ensured; existing accounts preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
