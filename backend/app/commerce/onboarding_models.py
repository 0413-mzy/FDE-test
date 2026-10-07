"""Additive onboarding records; identity and support contracts remain separate."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.commerce.models import Base, Record


class AccountProfile(Record, Base):
    __tablename__ = "commerce_account_profiles"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"), unique=True)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    review_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailChallenge(Record, Base):
    __tablename__ = "commerce_email_challenges"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    email: Mapped[str] = mapped_column(String(254))
    purpose: Mapped[str] = mapped_column(String(20))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("purpose IN ('REGISTER','BIND','RESET')"),)


class AnonymousRequest(Record, Base):
    __tablename__ = "commerce_anonymous_requests"
    operation: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[dict] = mapped_column(JSONB)
    response_status: Mapped[int]
    __table_args__ = (UniqueConstraint("operation", "key"),)


class AuthRateEvent(Record, Base):
    __tablename__ = "commerce_auth_rate_events"
    purpose: Mapped[str] = mapped_column(String(100))
    ip_digest: Mapped[str] = mapped_column(String(64))
    email_digest: Mapped[str | None] = mapped_column(String(64))


class AddressBook(Record, Base):
    __tablename__ = "commerce_address_book"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    address: Mapped[dict] = mapped_column(JSONB)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        Index(
            "commerce_one_default_address",
            "customer_id",
            unique=True,
            postgresql_where=text("active AND is_default"),
        ),
    )


class MerchantApplication(Record, Base):
    __tablename__ = "commerce_merchant_applications"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    shop_name: Mapped[str] = mapped_column(String(200))
    business_scope: Mapped[str] = mapped_column(String(500))
    contact_name: Mapped[str] = mapped_column(String(100))
    contact_phone: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    shop_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_shops.id"))
    __table_args__ = (
        CheckConstraint("state IN ('PENDING','APPROVED','REJECTED','WITHDRAWN')"),
        Index(
            "commerce_one_pending_application",
            "customer_id",
            unique=True,
            postgresql_where=text("state='PENDING'"),
        ),
    )
