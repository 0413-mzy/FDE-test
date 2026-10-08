"""Independent platform-owned commerce records; legacy support tables stay untouched."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CommerceAccount(Record, Base):
    __tablename__ = "commerce_accounts"
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    customer_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class CommerceSession(Record, Base):
    __tablename__ = "commerce_sessions"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Shop(Record, Base):
    __tablename__ = "commerce_shops"
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','SUSPENDED')"),)


class ShopMembership(Record, Base):
    __tablename__ = "commerce_shop_memberships"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    role: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("account_id", "shop_id"),
        CheckConstraint("role IN ('OWNER','STAFF')"),
    )


class Product(Record, Base):
    __tablename__ = "commerce_products"
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')"),
        UniqueConstraint("id", "shop_id"),
    )


class SKU(Record, Base):
    __tablename__ = "commerce_skus"
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_products.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    sku_code: Mapped[str] = mapped_column(String(80))
    options: Mapped[dict] = mapped_column(JSONB)
    unit_price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    price_version: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "shop_id"], ["commerce_products.id", "commerce_products.shop_id"]
        ),
        UniqueConstraint("id", "shop_id"),
        UniqueConstraint("shop_id", "sku_code"),
        UniqueConstraint("product_id", "options"),
        CheckConstraint("unit_price_minor BETWEEN 1 AND 100000000"),
        CheckConstraint("price_version > 0"),
        CheckConstraint("currency='CNY'"),
    )


class Inventory(Record, Base):
    __tablename__ = "commerce_inventory"
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_skus.id"), unique=True)
    on_hand: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand"),)


class StockMovement(Record, Base):
    __tablename__ = "commerce_stock_movements"
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_skus.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    on_hand_delta: Mapped[int] = mapped_column(Integer)
    reserved_delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    related_record_id: Mapped[UUID]


class Cart(Record, Base):
    __tablename__ = "commerce_carts"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"), unique=True)


class CartLine(Record, Base):
    __tablename__ = "commerce_cart_lines"
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_carts.id"))
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_skus.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    seen_price_version: Mapped[int] = mapped_column(Integer)
    seen_price_minor: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("cart_id", "sku_id"),
        CheckConstraint("quantity BETWEEN 1 AND 99"),
    )


class Checkout(Record, Base):
    __tablename__ = "commerce_checkouts"
    __table_args__ = (UniqueConstraint("id", "customer_id"),)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_carts.id"))
    source_cart_version: Mapped[int]
    result_cart_version: Mapped[int]
    address_snapshot: Mapped[dict] = mapped_column(JSONB)


class Order(Record, Base):
    __tablename__ = "commerce_orders"
    checkout_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_checkouts.id"))
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    status: Mapped[str] = mapped_column(String(30), default="PENDING_PAYMENT")
    financial_status: Mapped[str] = mapped_column(String(30), default="UNPAID")
    total_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    payment_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    address_snapshot: Mapped[dict] = mapped_column(JSONB)
    address_revision: Mapped[int] = mapped_column(default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason_code: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_PAYMENT','READY_TO_SHIP','PARTIALLY_SHIPPED',"
            "'SHIPPED','COMPLETED','CANCELLED')"
        ),
        CheckConstraint("financial_status IN ('UNPAID','PAID','PARTIALLY_REFUNDED','REFUNDED')"),
        ForeignKeyConstraint(
            ["checkout_id", "customer_id"],
            ["commerce_checkouts.id", "commerce_checkouts.customer_id"],
        ),
        UniqueConstraint("id", "shop_id"),
        UniqueConstraint("id", "customer_id", "shop_id"),
        CheckConstraint("total_minor > 0"),
        CheckConstraint("currency='CNY'"),
    )


class AddressRevision(Record, Base):
    __tablename__ = "commerce_address_revisions"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    revision: Mapped[int]
    address_snapshot: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("order_id", "revision"),)


class OrderLine(Record, Base):
    __tablename__ = "commerce_order_lines"
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_skus.id"))
    product_title_snapshot: Mapped[str] = mapped_column(Text)
    options_snapshot: Mapped[dict] = mapped_column(JSONB)
    unit_price_minor: Mapped[int]
    quantity: Mapped[int]
    shipped_qty: Mapped[int] = mapped_column(default=0)
    refunded_unshipped_qty: Mapped[int] = mapped_column(default=0)
    refunded_shipped_qty: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "shop_id"], ["commerce_orders.id", "commerce_orders.shop_id"]
        ),
        ForeignKeyConstraint(["sku_id", "shop_id"], ["commerce_skus.id", "commerce_skus.shop_id"]),
        UniqueConstraint("id", "order_id"),
        UniqueConstraint("order_id", "sku_id"),
        CheckConstraint(
            "quantity BETWEEN 1 AND 99 AND shipped_qty >= 0 AND shipped_qty <= quantity "
            "AND refunded_unshipped_qty >= 0 AND refunded_shipped_qty >= 0 "
            "AND shipped_qty + refunded_unshipped_qty <= quantity "
            "AND refunded_shipped_qty <= shipped_qty"
        ),
    )


class StockReservation(Record, Base):
    __tablename__ = "commerce_stock_reservations"
    order_line_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_order_lines.id"), unique=True)
    quantity: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default="HELD")
    __table_args__ = (
        CheckConstraint("state IN ('HELD','CONSUMED','RELEASED')"),
        CheckConstraint("quantity BETWEEN 1 AND 99"),
    )


class PaymentAttempt(Record, Base):
    __tablename__ = "commerce_payment_attempts"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    simulation: Mapped[bool] = mapped_column(default=True)
    provider_reference: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint("state IN ('PENDING','SUCCEEDED','FAILED')"),
        CheckConstraint("amount_minor > 0 AND simulation"),
        Index(
            "commerce_one_pending_payment",
            "order_id",
            unique=True,
            postgresql_where=text("state='PENDING'"),
        ),
        Index(
            "commerce_one_success_payment",
            "order_id",
            unique=True,
            postgresql_where=text("state='SUCCEEDED'"),
        ),
    )


class Shipment(Record, Base):
    __tablename__ = "commerce_shipments"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    tracking_number: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="SHIPPED")
    simulation: Mapped[bool] = mapped_column(default=True)
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exception_reason: Mapped[str | None] = mapped_column(String(30))
    exception_from_status: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (
        CheckConstraint(
            "status IN ('SHIPPED','COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY',"
            "'EXCEPTION','DELIVERED')"
        ),
        UniqueConstraint("id", "order_id"),
        CheckConstraint("simulation"),
    )


class ShipmentLine(Record, Base):
    __tablename__ = "commerce_shipment_lines"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shipments.id"))
    order_line_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_order_lines.id"))
    quantity: Mapped[int]
    __table_args__ = (
        ForeignKeyConstraint(
            ["shipment_id", "order_id"], ["commerce_shipments.id", "commerce_shipments.order_id"]
        ),
        ForeignKeyConstraint(
            ["order_line_id", "order_id"],
            ["commerce_order_lines.id", "commerce_order_lines.order_id"],
        ),
        UniqueConstraint("shipment_id", "order_line_id"),
        CheckConstraint("quantity BETWEEN 1 AND 99"),
    )


class TrackingEvent(Record, Base):
    __tablename__ = "commerce_tracking_events"
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shipments.id"))
    event_id: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int]
    source: Mapped[str] = mapped_column(String(30), default="SIMULATED_CARRIER")
    location: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(String(30))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_accounts.id"))
    status_applied: Mapped[bool | None]
    request_version: Mapped[int | None]
    __table_args__ = (
        UniqueConstraint("shipment_id", "sequence"),
        CheckConstraint("sequence > 0"),
        CheckConstraint("source='SIMULATED_CARRIER'"),
        CheckConstraint(
            "kind IN ('SHIPPED','COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY',"
            "'EXCEPTION','DELIVERED')"
        ),
    )


class SimulationEvent(Record, Base):
    __tablename__ = "commerce_simulation_events"
    source: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[dict] = mapped_column(JSONB)
    response_status: Mapped[int]
    target_id: Mapped[UUID]
    __table_args__ = (UniqueConstraint("source", "event_id"),)


class IdempotencyRecord(Record, Base):
    __tablename__ = "commerce_idempotency_records"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    operation: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_ids: Mapped[list] = mapped_column(JSONB)
    response_status: Mapped[int]
    response_payload: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    __table_args__ = (UniqueConstraint("actor_id", "operation", "key"),)


class BusinessAudit(Record, Base):
    __tablename__ = "commerce_business_audits"
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_accounts.id"))
    action: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID | None]
    request_id: Mapped[str] = mapped_column(String(100))
    safe_metadata: Mapped[dict] = mapped_column(JSONB)


class Conversation(Record, Base):
    __tablename__ = "commerce_conversations"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    order_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_orders.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "customer_id", "shop_id"],
            ["commerce_orders.id", "commerce_orders.customer_id", "commerce_orders.shop_id"],
        ),
        Index(
            "commerce_conversation_unique",
            "customer_id",
            "shop_id",
            "order_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )


class Message(Record, Base):
    __tablename__ = "commerce_messages"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_conversations.id"))
    sender_account_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    sender_side: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("sender_side IN ('CUSTOMER','MERCHANT')"),
        CheckConstraint("length(btrim(body)) BETWEEN 1 AND 2000"),
    )


class AfterSaleCase(Record, Base):
    __tablename__ = "commerce_after_sale_cases"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    type: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    requested_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("id", "order_id"),
        CheckConstraint("type IN ('UNSHIPPED_REFUND','RETURN_REFUND')"),
        CheckConstraint(
            "state IN ('REQUESTED','REJECTED','CANCELLED','AWAITING_RETURN',"
            "'RETURN_IN_TRANSIT','REFUND_PENDING','COMPLETED')"
        ),
        CheckConstraint("requested_amount_minor > 0 AND currency='CNY'"),
        Index(
            "commerce_one_active_case",
            "order_id",
            unique=True,
            postgresql_where=text("state NOT IN ('REJECTED','CANCELLED','COMPLETED')"),
        ),
    )


class AfterSaleLine(Record, Base):
    __tablename__ = "commerce_after_sale_lines"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_after_sale_cases.id"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    order_line_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_order_lines.id"))
    quantity: Mapped[int]
    unit_price_minor_snapshot: Mapped[int]
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "order_id"],
            ["commerce_after_sale_cases.id", "commerce_after_sale_cases.order_id"],
        ),
        ForeignKeyConstraint(
            ["order_line_id", "order_id"],
            ["commerce_order_lines.id", "commerce_order_lines.order_id"],
        ),
        UniqueConstraint("case_id", "order_line_id"),
        CheckConstraint("quantity BETWEEN 1 AND 99 AND unit_price_minor_snapshot > 0"),
    )


class ReturnShipment(Record, Base):
    __tablename__ = "commerce_return_shipments"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_after_sale_cases.id"), unique=True)
    tracking_number: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20))
    restock: Mapped[bool | None] = mapped_column(Boolean)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("state IN ('IN_TRANSIT','RECEIVED')"),
        CheckConstraint(
            "(state='IN_TRANSIT' AND restock IS NULL AND received_at IS NULL) OR "
            "(state='RECEIVED' AND restock IS NOT NULL AND received_at IS NOT NULL)"
        ),
    )


class RefundAttempt(Record, Base):
    __tablename__ = "commerce_refund_attempts"
    after_sale_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_after_sale_cases.id"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    simulation: Mapped[bool] = mapped_column(default=True)
    provider_reference: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint("state IN ('PENDING','SUCCEEDED','FAILED')"),
        CheckConstraint("amount_minor > 0 AND simulation AND currency='CNY'"),
        Index(
            "commerce_one_pending_refund",
            "after_sale_id",
            unique=True,
            postgresql_where=text("state='PENDING'"),
        ),
        Index(
            "commerce_one_success_refund",
            "after_sale_id",
            unique=True,
            postgresql_where=text("state='SUCCEEDED'"),
        ),
    )


for _table in Base.metadata.tables.values():
    _table.append_constraint(CheckConstraint("version > 0", name=_table.name + "_positive_version"))
