"""Explicit reviewer bootstrap; never promote or modify an existing account."""

import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commerce.models import CommerceAccount
from app.commerce.onboarding_models import AccountProfile
from app.commerce.seed import seed_id
from app.core.security import PASSWORD_HASHER
from app.db.connection import product_engine


def seed_reviewer(db, password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("DEMO_SEED_PASSWORD must contain 12..128 characters")
    with db.begin():
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(current_schema() || '-commerce-v1',0))"
            )
        )
        existing = db.scalar(select(CommerceAccount).where(CommerceAccount.username == "reviewer"))
        if existing is not None:
            return
        account = CommerceAccount(
            id=seed_id("account/reviewer"),
            username="reviewer",
            password_hash=PASSWORD_HASHER.hash(password),
            active=True,
            customer_enabled=False,
            demo_enabled=False,
        )
        db.add(account)
        db.flush()
        db.add(AccountProfile(account_id=account.id, review_enabled=True))


def main():
    if os.environ.get("APP_ENV") not in {"development", "test"}:
        raise SystemExit("Explicit APP_ENV development/test is required")
    engine = product_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as db:
            seed_reviewer(db, os.environ.get("DEMO_SEED_PASSWORD", ""))
        print("Independent reviewer seed ensured; existing accounts preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
