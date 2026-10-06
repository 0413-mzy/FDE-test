"""Frozen additive purchase and fulfillment schema; no legacy table changes."""

# ruff: noqa: E501
from alembic import op

revision = "0003_commerce"
down_revision = "0002_nonblank_constraints"
branch_labels = None
depends_on = None

DDL = (
    """
    CREATE TABLE commerce_accounts ( username VARCHAR(80) NOT NULL, password_hash TEXT NOT
    NULL, active BOOLEAN NOT NULL, customer_enabled BOOLEAN NOT NULL, demo_enabled BOOLEAN
    NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME
    ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE
    (username), CONSTRAINT commerce_accounts_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_shops ( name VARCHAR(200) NOT NULL, status VARCHAR(20) NOT NULL,
    id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT
    NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CHECK (status IN
    ('ACTIVE','SUSPENDED')), CONSTRAINT commerce_shops_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE commerce_simulation_events ( source VARCHAR(30) NOT NULL, event_id
    VARCHAR(100) NOT NULL, request_hash VARCHAR(64) NOT NULL, response_payload JSONB NOT
    NULL, response_status INTEGER NOT NULL, target_id UUID NOT NULL, id UUID NOT NULL,
    version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at
    TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE (source, event_id),
    CONSTRAINT commerce_simulation_events_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_business_audits ( actor_id UUID, action TEXT NOT NULL, target_id
    UUID, request_id VARCHAR(100) NOT NULL, safe_metadata JSONB NOT NULL, id UUID NOT NULL,
    version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at
    TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), FOREIGN KEY(actor_id) REFERENCES
    commerce_accounts (id), CONSTRAINT commerce_business_audits_positive_version CHECK
    (version > 0) )
    """,
    """
    CREATE TABLE commerce_carts ( customer_id UUID NOT NULL, id UUID NOT NULL, version
    INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP
    WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE (customer_id), FOREIGN
    KEY(customer_id) REFERENCES commerce_accounts (id), CONSTRAINT
    commerce_carts_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_idempotency_records ( actor_id UUID NOT NULL, operation TEXT NOT
    NULL, key VARCHAR(200) NOT NULL, request_hash VARCHAR(64) NOT NULL, resource_ids JSONB
    NOT NULL, response_status INTEGER NOT NULL, response_payload JSONB, id UUID NOT NULL,
    version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at
    TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE (actor_id, operation, key),
    FOREIGN KEY(actor_id) REFERENCES commerce_accounts (id), CONSTRAINT
    commerce_idempotency_records_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_products ( shop_id UUID NOT NULL, title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL, status VARCHAR(20) NOT NULL, id UUID NOT NULL, version
    INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP
    WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CHECK (status IN
    ('DRAFT','PUBLISHED','ARCHIVED')), UNIQUE (id, shop_id), FOREIGN KEY(shop_id) REFERENCES
    commerce_shops (id), CONSTRAINT commerce_products_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_sessions ( account_id UUID NOT NULL, token_digest VARCHAR(64) NOT
    NULL, expires_at TIMESTAMP WITH TIME ZONE NOT NULL, revoked_at TIMESTAMP WITH TIME ZONE,
    id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT
    NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), FOREIGN
    KEY(account_id) REFERENCES commerce_accounts (id), UNIQUE (token_digest), CONSTRAINT
    commerce_sessions_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_shop_memberships ( account_id UUID NOT NULL, shop_id UUID NOT
    NULL, role VARCHAR(10) NOT NULL, active BOOLEAN NOT NULL, id UUID NOT NULL, version
    INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP
    WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE (account_id, shop_id), CHECK (role IN
    ('OWNER','STAFF')), FOREIGN KEY(account_id) REFERENCES commerce_accounts (id), FOREIGN
    KEY(shop_id) REFERENCES commerce_shops (id), CONSTRAINT
    commerce_shop_memberships_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_checkouts ( customer_id UUID NOT NULL, cart_id UUID NOT NULL,
    source_cart_version INTEGER NOT NULL, result_cart_version INTEGER NOT NULL,
    address_snapshot JSONB NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at
    TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY
    KEY (id), UNIQUE (id, customer_id), FOREIGN KEY(customer_id) REFERENCES
    commerce_accounts (id), FOREIGN KEY(cart_id) REFERENCES commerce_carts (id), CONSTRAINT
    commerce_checkouts_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_skus ( product_id UUID NOT NULL, shop_id UUID NOT NULL, sku_code
    VARCHAR(80) NOT NULL, options JSONB NOT NULL, unit_price_minor INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL, price_version INTEGER NOT NULL, active BOOLEAN NOT NULL,
    id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT
    NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), FOREIGN
    KEY(product_id, shop_id) REFERENCES commerce_products (id, shop_id), UNIQUE (id,
    shop_id), UNIQUE (shop_id, sku_code), UNIQUE (product_id, options), CHECK
    (unit_price_minor BETWEEN 1 AND 100000000), CHECK (price_version > 0), CHECK
    (currency='CNY'), FOREIGN KEY(product_id) REFERENCES commerce_products (id), FOREIGN
    KEY(shop_id) REFERENCES commerce_shops (id), CONSTRAINT commerce_skus_positive_version
    CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_cart_lines ( cart_id UUID NOT NULL, sku_id UUID NOT NULL, quantity
    INTEGER NOT NULL, seen_price_version INTEGER NOT NULL, seen_price_minor INTEGER NOT
    NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE
    NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE
    (cart_id, sku_id), CHECK (quantity BETWEEN 1 AND 99), FOREIGN KEY(cart_id) REFERENCES
    commerce_carts (id), FOREIGN KEY(sku_id) REFERENCES commerce_skus (id), CONSTRAINT
    commerce_cart_lines_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_inventory ( sku_id UUID NOT NULL, on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at
    TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY
    KEY (id), CHECK (on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand), UNIQUE
    (sku_id), FOREIGN KEY(sku_id) REFERENCES commerce_skus (id), CONSTRAINT
    commerce_inventory_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_orders ( checkout_id UUID NOT NULL, customer_id UUID NOT NULL,
    shop_id UUID NOT NULL, status VARCHAR(30) NOT NULL, financial_status VARCHAR(30) NOT
    NULL, total_minor BIGINT NOT NULL, currency VARCHAR(3) NOT NULL, payment_deadline
    TIMESTAMP WITH TIME ZONE NOT NULL, address_snapshot JSONB NOT NULL, address_revision
    INTEGER NOT NULL, completed_at TIMESTAMP WITH TIME ZONE, cancelled_at TIMESTAMP WITH
    TIME ZONE, cancel_reason_code VARCHAR(40), id UUID NOT NULL, version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT
    NULL, PRIMARY KEY (id), CHECK (status IN
    ('PENDING_PAYMENT','READY_TO_SHIP','PARTIALLY_SHIPPED','SHIPPED','COMPLETED','CANCELLED')),
    CHECK (financial_status IN ('UNPAID','PAID','PARTIALLY_REFUNDED','REFUNDED')), FOREIGN
    KEY(checkout_id, customer_id) REFERENCES commerce_checkouts (id, customer_id), UNIQUE
    (id, shop_id), CHECK (total_minor > 0), CHECK (currency='CNY'), FOREIGN KEY(checkout_id)
    REFERENCES commerce_checkouts (id), FOREIGN KEY(customer_id) REFERENCES
    commerce_accounts (id), FOREIGN KEY(shop_id) REFERENCES commerce_shops (id), CONSTRAINT
    commerce_orders_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_stock_movements ( sku_id UUID NOT NULL, actor_id UUID NOT NULL,
    on_hand_delta INTEGER NOT NULL, reserved_delta INTEGER NOT NULL, reason TEXT NOT NULL,
    related_record_id UUID NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at
    TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY
    KEY (id), FOREIGN KEY(sku_id) REFERENCES commerce_skus (id), FOREIGN KEY(actor_id)
    REFERENCES commerce_accounts (id), CONSTRAINT commerce_stock_movements_positive_version
    CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_address_revisions ( order_id UUID NOT NULL, revision INTEGER NOT
    NULL, address_snapshot JSONB NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT
    NULL, PRIMARY KEY (id), UNIQUE (order_id, revision), FOREIGN KEY(order_id) REFERENCES
    commerce_orders (id), CONSTRAINT commerce_address_revisions_positive_version CHECK
    (version > 0) )
    """,
    """
    CREATE TABLE commerce_order_lines ( shop_id UUID NOT NULL, order_id UUID NOT NULL,
    sku_id UUID NOT NULL, product_title_snapshot TEXT NOT NULL, options_snapshot JSONB NOT
    NULL, unit_price_minor INTEGER NOT NULL, quantity INTEGER NOT NULL, shipped_qty INTEGER
    NOT NULL, refunded_unshipped_qty INTEGER NOT NULL, refunded_shipped_qty INTEGER NOT
    NULL, id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE
    NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), FOREIGN
    KEY(order_id, shop_id) REFERENCES commerce_orders (id, shop_id), FOREIGN KEY(sku_id,
    shop_id) REFERENCES commerce_skus (id, shop_id), UNIQUE (id, order_id), UNIQUE
    (order_id, sku_id), CHECK (quantity BETWEEN 1 AND 99 AND shipped_qty >= 0 AND
    shipped_qty <= quantity AND refunded_unshipped_qty >= 0 AND refunded_shipped_qty >= 0
    AND shipped_qty + refunded_unshipped_qty <= quantity AND refunded_shipped_qty <=
    shipped_qty), FOREIGN KEY(shop_id) REFERENCES commerce_shops (id), FOREIGN KEY(order_id)
    REFERENCES commerce_orders (id), FOREIGN KEY(sku_id) REFERENCES commerce_skus (id),
    CONSTRAINT commerce_order_lines_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_payment_attempts ( order_id UUID NOT NULL, amount_minor BIGINT NOT
    NULL, currency VARCHAR(3) NOT NULL, state VARCHAR(20) NOT NULL, simulation BOOLEAN NOT
    NULL, provider_reference TEXT, finished_at TIMESTAMP WITH TIME ZONE, failure_code
    VARCHAR(40), id UUID NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME
    ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CHECK
    (state IN ('PENDING','SUCCEEDED','FAILED')), CHECK (amount_minor > 0 AND simulation),
    FOREIGN KEY(order_id) REFERENCES commerce_orders (id), CONSTRAINT
    commerce_payment_attempts_positive_version CHECK (version > 0) )
    """,
    """
    CREATE UNIQUE INDEX commerce_one_success_payment ON commerce_payment_attempts (order_id)
    WHERE state='SUCCEEDED'
    """,
    """
    CREATE UNIQUE INDEX commerce_one_pending_payment ON commerce_payment_attempts (order_id)
    WHERE state='PENDING'
    """,
    """
    CREATE TABLE commerce_shipments ( order_id UUID NOT NULL, tracking_number VARCHAR(100)
    NOT NULL, status VARCHAR(20) NOT NULL, simulation BOOLEAN NOT NULL, shipped_at TIMESTAMP
    WITH TIME ZONE NOT NULL, delivered_at TIMESTAMP WITH TIME ZONE, id UUID NOT NULL,
    version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at
    TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), CHECK (status IN
    ('SHIPPED','IN_TRANSIT','EXCEPTION','DELIVERED')), UNIQUE (id, order_id), CHECK
    (simulation), FOREIGN KEY(order_id) REFERENCES commerce_orders (id), UNIQUE
    (tracking_number), CONSTRAINT commerce_shipments_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_shipment_lines ( order_id UUID NOT NULL, shipment_id UUID NOT
    NULL, order_line_id UUID NOT NULL, quantity INTEGER NOT NULL, id UUID NOT NULL, version
    INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP
    WITH TIME ZONE NOT NULL, PRIMARY KEY (id), FOREIGN KEY(shipment_id, order_id) REFERENCES
    commerce_shipments (id, order_id), FOREIGN KEY(order_line_id, order_id) REFERENCES
    commerce_order_lines (id, order_id), UNIQUE (shipment_id, order_line_id), CHECK
    (quantity BETWEEN 1 AND 99), FOREIGN KEY(order_id) REFERENCES commerce_orders (id),
    FOREIGN KEY(shipment_id) REFERENCES commerce_shipments (id), FOREIGN KEY(order_line_id)
    REFERENCES commerce_order_lines (id), CONSTRAINT
    commerce_shipment_lines_positive_version CHECK (version > 0) )
    """,
    """
    CREATE TABLE commerce_stock_reservations ( order_line_id UUID NOT NULL, quantity INTEGER
    NOT NULL, state VARCHAR(20) NOT NULL, id UUID NOT NULL, version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT
    NULL, PRIMARY KEY (id), CHECK (state IN ('HELD','CONSUMED','RELEASED')), CHECK (quantity
    BETWEEN 1 AND 99), UNIQUE (order_line_id), FOREIGN KEY(order_line_id) REFERENCES
    commerce_order_lines (id), CONSTRAINT commerce_stock_reservations_positive_version CHECK
    (version > 0) )
    """,
    """
    CREATE TABLE commerce_tracking_events ( shipment_id UUID NOT NULL, event_id VARCHAR(100)
    NOT NULL, kind VARCHAR(20) NOT NULL, description TEXT NOT NULL, occurred_at TIMESTAMP
    WITH TIME ZONE NOT NULL, sequence INTEGER NOT NULL, source VARCHAR(30) NOT NULL, id UUID
    NOT NULL, version INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, PRIMARY KEY (id), UNIQUE (shipment_id,
    sequence), CHECK (sequence > 0), CHECK (source='SIMULATED_CARRIER'), CHECK (kind IN
    ('SHIPPED','IN_TRANSIT','EXCEPTION','DELIVERED')), FOREIGN KEY(shipment_id) REFERENCES
    commerce_shipments (id), UNIQUE (event_id), CONSTRAINT
    commerce_tracking_events_positive_version CHECK (version > 0) )
    """,
    """
    CREATE FUNCTION commerce_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION 'immutable commerce record'; END; $$
    """,
    """
    CREATE TRIGGER commerce_stock_movements_immutable BEFORE UPDATE OR DELETE ON
    commerce_stock_movements FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_tracking_events_immutable BEFORE UPDATE OR DELETE ON
    commerce_tracking_events FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_business_audits_immutable BEFORE UPDATE OR DELETE ON
    commerce_business_audits FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_idempotency_records_immutable BEFORE UPDATE OR DELETE ON
    commerce_idempotency_records FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_simulation_events_immutable BEFORE UPDATE OR DELETE ON
    commerce_simulation_events FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_address_revisions_immutable BEFORE UPDATE OR DELETE ON
    commerce_address_revisions FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_checkouts_immutable BEFORE UPDATE OR DELETE ON
    commerce_checkouts FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_shipment_lines_immutable BEFORE UPDATE OR DELETE ON
    commerce_shipment_lines FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE FUNCTION commerce_payment_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF
    TG_OP='DELETE' OR OLD.state <> 'PENDING' OR NEW.order_id <> OLD.order_id OR
    NEW.amount_minor <> OLD.amount_minor OR NEW.currency <> OLD.currency OR NEW.state NOT IN
    ('SUCCEEDED','FAILED') THEN RAISE EXCEPTION 'immutable payment record'; END IF; RETURN
    NEW; END; $$
    """,
    """
    CREATE TRIGGER commerce_payment_guard BEFORE UPDATE OR DELETE ON
    commerce_payment_attempts FOR EACH ROW EXECUTE FUNCTION commerce_payment_guard()
    """,
)


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    op.execute("DROP TABLE commerce_tracking_events")
    op.execute("DROP TABLE commerce_stock_reservations")
    op.execute("DROP TABLE commerce_shipment_lines")
    op.execute("DROP TABLE commerce_shipments")
    op.execute("DROP TABLE commerce_payment_attempts")
    op.execute("DROP TABLE commerce_order_lines")
    op.execute("DROP TABLE commerce_address_revisions")
    op.execute("DROP TABLE commerce_stock_movements")
    op.execute("DROP TABLE commerce_orders")
    op.execute("DROP TABLE commerce_inventory")
    op.execute("DROP TABLE commerce_cart_lines")
    op.execute("DROP TABLE commerce_skus")
    op.execute("DROP TABLE commerce_checkouts")
    op.execute("DROP TABLE commerce_shop_memberships")
    op.execute("DROP TABLE commerce_sessions")
    op.execute("DROP TABLE commerce_products")
    op.execute("DROP TABLE commerce_idempotency_records")
    op.execute("DROP TABLE commerce_carts")
    op.execute("DROP TABLE commerce_business_audits")
    op.execute("DROP TABLE commerce_simulation_events")
    op.execute("DROP TABLE commerce_shops")
    op.execute("DROP TABLE commerce_accounts")
    op.execute("DROP FUNCTION commerce_append_only()")
    op.execute("DROP FUNCTION commerce_payment_guard()")
