"""Independent platform authority, moderation and arbitration records."""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.commerce.models import Base, Record


class PlatformRole(Record, Base):
    __tablename__ = "commerce_platform_roles"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("version > 0"),)


class ModerationReport(Record, Base):
    __tablename__ = "commerce_moderation_reports"
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[UUID]
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("version > 0"),
        CheckConstraint("target_type IN ('PRODUCT','SHOP','REVIEW')"),
        CheckConstraint("state IN ('OPEN','RESOLVED','DISMISSED')"),
        Index(
            "commerce_one_open_report",
            "reporter_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("state='OPEN'"),
        ),
    )


class ModerationAction(Record, Base):
    __tablename__ = "commerce_moderation_actions"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    report_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_moderation_reports.id"))
    __table_args__ = (CheckConstraint("version > 0"),)


class Dispute(Record, Base):
    __tablename__ = "commerce_disputes"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    case_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_after_sale_cases.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    customer_evidence: Mapped[str] = mapped_column(Text, default="")
    merchant_evidence: Mapped[str] = mapped_column(Text, default="")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_accounts.id"))
    __table_args__ = (
        CheckConstraint("version > 0"),
        CheckConstraint("state IN ('OPEN','UPHELD','OVERTURNED','WITHDRAWN')"),
        ForeignKeyConstraint(
            ["case_id", "order_id"],
            ["commerce_after_sale_cases.id", "commerce_after_sale_cases.order_id"],
        ),
        ForeignKeyConstraint(
            ["order_id", "customer_id", "shop_id"],
            ["commerce_orders.id", "commerce_orders.customer_id", "commerce_orders.shop_id"],
        ),
        Index(
            "commerce_one_open_dispute",
            "case_id",
            unique=True,
            postgresql_where=text("state='OPEN'"),
        ),
    )
