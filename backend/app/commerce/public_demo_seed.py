"""Production-only fictional bootstrap; existing records are validated, never repaired."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commerce.models import CommerceAccount, ShopMembership
from app.commerce.onboarding_models import AccountProfile
from app.commerce.onboarding_seed import seed_reviewer
from app.commerce.platform_models import PlatformRole
from app.commerce.platform_seed import seed_platform
from app.commerce.public_demo import VISITOR_ACCOUNTS
from app.commerce.seed import seed_commerce, seed_id
from app.core.config import Settings
from app.core.security import password_matches
from app.db.connection import product_engine


def bootstrap_public_demo(settings):
    if settings.app_env != "production" or not settings.commerce_public_demo:
        raise ValueError("Explicit production public demo mode is required")
    if not settings.commerce_public_demo_bootstrap:
        raise ValueError("Explicit public demo bootstrap acknowledgement is required")
    if settings.database_url is None:
        raise ValueError("Public demo database is required")
    public = settings.commerce_demo_password.get_secret_value()
    private = settings.commerce_operator_password.get_secret_value()
    engine = product_engine(settings.database_url.get_secret_value())
    try:
        # Session seeds own transactions. A session-level lock serializes the complete
        # bootstrap, including all three seeds and restart verification.
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_advisory_lock(hashtextextended("
                    "current_schema() || '-public-demo-bootstrap',0))"
                )
            )
            connection.commit()
            try:
                with Session(bind=connection) as db:
                    rows = list(db.scalars(select(CommerceAccount)))
                    db.rollback()
                    if not rows:
                        # Any commerce business rows without accounts are not an empty demo.
                        tables = db.scalars(
                            text(
                                "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
                                "AND tablename LIKE 'commerce_%'"
                            )
                        ).all()
                        for table in tables:
                            if db.scalar(
                                text('SELECT count(*) FROM "' + table.replace('"', '""') + '"')
                            ):
                                raise ValueError("Unknown nonempty commerce database refused")
                        db.rollback()
                        seed_commerce(db, public)
                        seed_reviewer(db, private)
                        seed_platform(db, private)
                    verify_public_demo(db, public, private)
            finally:
                connection.rollback()
                connection.execute(
                    text(
                        "SELECT pg_advisory_unlock(hashtextextended("
                        "current_schema() || '-public-demo-bootstrap',0))"
                    )
                )
                connection.commit()
    finally:
        engine.dispose()


def verify_public_demo(db, public, private):
    accounts = list(db.scalars(select(CommerceAccount)))
    expected = {*VISITOR_ACCOUNTS, "reviewer", "platform"}
    if {row.username for row in accounts} != expected:
        raise ValueError("Unknown or incomplete public demo accounts refused")
    for row in accounts:
        if (
            row.id != seed_id("account/" + row.username)
            or row.username not in VISITOR_ACCOUNTS
            and not row.active
            or not password_matches(
                row.password_hash, public if row.username in VISITOR_ACCOUNTS else private
            )
        ):
            raise ValueError("Public demo account configuration mismatch")
        if row.customer_enabled != (
            row.username.startswith("customer") or row.username == "dual.a"
        ) or row.demo_enabled != (row.username == "demo"):
            raise ValueError("Public demo account permissions mismatch")
    expected_members = {
        (seed_id("account/" + user), seed_id("shop/" + shop), role, True)
        for user, shop, role in [
            ("owner.a", "shopA", "OWNER"),
            ("owner.b", "shopB", "OWNER"),
            ("staff.a", "shopA", "STAFF"),
            ("dual.a", "shopA", "OWNER"),
        ]
    }
    memberships = {
        (m.account_id, m.shop_id, m.role, m.active) for m in db.scalars(select(ShopMembership))
    }
    if memberships != expected_members:
        raise ValueError("Public demo shop memberships mismatch")
    roles = list(db.scalars(select(PlatformRole)))
    reviewers = list(
        db.scalars(select(AccountProfile).where(AccountProfile.review_enabled.is_(True)))
    )
    if (
        len(roles) != 1
        or roles[0].account_id != seed_id("account/platform")
        or not roles[0].active
        or len(reviewers) != 1
        or reviewers[0].account_id != seed_id("account/reviewer")
    ):
        raise ValueError("Public demo private roles mismatch")


def main():
    bootstrap_public_demo(Settings())
    print("Public fictional demo initialized or verified; existing business records preserved.")


if __name__ == "__main__":
    main()
