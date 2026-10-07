"""Safe append-only record history and transaction-local attribution."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.commerce.models import Base

# Explicit business snapshot policy; new columns require deliberate review.
FIELD_POLICY = {
    "commerce_account_profiles": (
        "account_id",
        "display_name",
        "phone",
        "email",
        "email_verified",
        "review_enabled",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_accounts": (
        "username",
        "active",
        "customer_enabled",
        "demo_enabled",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_address_book": (
        "customer_id",
        "address",
        "is_default",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_address_revisions": (
        "order_id",
        "revision",
        "address_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_after_sale_cases": (
        "order_id",
        "type",
        "state",
        "reason",
        "requested_amount_minor",
        "currency",
        "decision_reason",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_after_sale_lines": (
        "case_id",
        "order_id",
        "order_line_id",
        "quantity",
        "unit_price_minor_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_cart_lines": (
        "cart_id",
        "sku_id",
        "quantity",
        "seen_price_version",
        "seen_price_minor",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_carts": ("customer_id", "id", "version", "created_at", "updated_at"),
    "commerce_checkouts": (
        "customer_id",
        "cart_id",
        "source_cart_version",
        "result_cart_version",
        "address_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_conversations": (
        "customer_id",
        "shop_id",
        "order_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_email_challenges": (
        "account_id",
        "email",
        "purpose",
        "expires_at",
        "consumed_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_inventory": (
        "sku_id",
        "on_hand",
        "reserved",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_merchant_applications": (
        "customer_id",
        "state",
        "shop_name",
        "business_scope",
        "contact_name",
        "contact_phone",
        "description",
        "decision_reason",
        "shop_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_messages": (
        "conversation_id",
        "sender_account_id",
        "sender_side",
        "body",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_order_lines": (
        "shop_id",
        "order_id",
        "sku_id",
        "product_title_snapshot",
        "options_snapshot",
        "unit_price_minor",
        "quantity",
        "shipped_qty",
        "refunded_unshipped_qty",
        "refunded_shipped_qty",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_orders": (
        "checkout_id",
        "customer_id",
        "shop_id",
        "status",
        "financial_status",
        "total_minor",
        "currency",
        "payment_deadline",
        "address_snapshot",
        "address_revision",
        "completed_at",
        "cancelled_at",
        "cancel_reason_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_payment_attempts": (
        "order_id",
        "amount_minor",
        "currency",
        "state",
        "simulation",
        "provider_reference",
        "finished_at",
        "failure_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_products": (
        "shop_id",
        "title",
        "description",
        "status",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_refund_attempts": (
        "after_sale_id",
        "amount_minor",
        "currency",
        "state",
        "simulation",
        "provider_reference",
        "finished_at",
        "failure_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_return_shipments": (
        "case_id",
        "tracking_number",
        "state",
        "restock",
        "registered_at",
        "received_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_sessions": (
        "account_id",
        "expires_at",
        "revoked_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shipment_lines": (
        "order_id",
        "shipment_id",
        "order_line_id",
        "quantity",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shipments": (
        "order_id",
        "tracking_number",
        "status",
        "simulation",
        "shipped_at",
        "delivered_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shop_memberships": (
        "account_id",
        "shop_id",
        "role",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shops": ("name", "status", "id", "version", "created_at", "updated_at"),
    "commerce_skus": (
        "product_id",
        "shop_id",
        "sku_code",
        "options",
        "unit_price_minor",
        "currency",
        "price_version",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_stock_movements": (
        "sku_id",
        "actor_id",
        "on_hand_delta",
        "reserved_delta",
        "reason",
        "related_record_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_stock_reservations": (
        "order_line_id",
        "quantity",
        "state",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_tracking_events": (
        "shipment_id",
        "event_id",
        "kind",
        "description",
        "occurred_at",
        "sequence",
        "source",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
}


class RecordHistory(Base):
    __tablename__ = "commerce_record_history"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    entity_table: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID]
    operation: Mapped[str] = mapped_column(String(8))
    before_data: Mapped[dict | None] = mapped_column(JSONB)
    after_data: Mapped[dict | None] = mapped_column(JSONB)
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(Text))
    actor_id: Mapped[UUID | None]
    actor_username: Mapped[str | None] = mapped_column(String(80))
    db_role: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(String(500))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    __table_args__ = (
        CheckConstraint("operation IN ('BASELINE','INSERT','UPDATE','DELETE')"),
        CheckConstraint(
            "(operation IN ('BASELINE','INSERT') "
            "AND before_data IS NULL AND after_data IS NOT NULL) "
            "OR (operation='UPDATE' AND before_data IS NOT NULL AND after_data IS NOT NULL) "
            "OR (operation='DELETE' AND before_data IS NOT NULL AND after_data IS NULL)"
        ),
        Index("commerce_history_entity", "entity_table", "entity_id", "id"),
        Index("commerce_history_time", "recorded_at", "id"),
    )


def set_context(db, actor=None, request=None, reason=None, *, action=None):
    """Bind only safe scalars; LOCAL settings disappear at commit/rollback."""
    route = request.scope.get("route") if request is not None else None
    action = action or (getattr(route, "name", None) if route else None) or "DIRECT_SQL"
    values = {
        "actor_id": str(actor.id) if actor is not None else "",
        "actor_username": actor.username if actor is not None else "",
        "request_id": str(getattr(request.state, "request_id", ""))[:100] if request else "",
        "action": action[:120],
        "reason": reason[:500] if isinstance(reason, str) else "",
    }
    for name, value in values.items():
        db.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": "commerce_history." + name, "value": value},
        )
