"""Frozen additive conversations and after-sales schema; preserve existing orders."""

from alembic import op

revision = "0004_commerce_after_sales"
down_revision = "0003_commerce"
branch_labels = None
depends_on = None

DDL = (
    """
    ALTER TABLE commerce_orders ADD CONSTRAINT commerce_order_conversation_scope UNIQUE (id,
    customer_id, shop_id)
    """,
    """
    CREATE TABLE commerce_after_sale_cases (
            order_id UUID NOT NULL,
            type VARCHAR(30) NOT NULL,
            state VARCHAR(30) NOT NULL,
            reason TEXT NOT NULL,
            requested_amount_minor BIGINT NOT NULL,
            currency VARCHAR(3) NOT NULL,
            decision_reason TEXT,
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (id, order_id),
            CHECK (type IN ('UNSHIPPED_REFUND','RETURN_REFUND')),
            CHECK (state IN
    ('REQUESTED','REJECTED','CANCELLED','AWAITING_RETURN','RETURN_IN_TRANSIT','REFUND_PENDING','COMPLETED')),
            CHECK (requested_amount_minor > 0 AND currency='CNY'),
            FOREIGN KEY(order_id) REFERENCES commerce_orders (id),
            CONSTRAINT commerce_after_sale_cases_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE UNIQUE INDEX commerce_one_active_case ON commerce_after_sale_cases (order_id) WHERE
    state NOT IN ('REJECTED','CANCELLED','COMPLETED')
    """,
    """
    CREATE TABLE commerce_conversations (
            customer_id UUID NOT NULL,
            shop_id UUID NOT NULL,
            order_id UUID,
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(order_id, customer_id, shop_id) REFERENCES commerce_orders (id,
    customer_id, shop_id),
            FOREIGN KEY(customer_id) REFERENCES commerce_accounts (id),
            FOREIGN KEY(shop_id) REFERENCES commerce_shops (id),
            FOREIGN KEY(order_id) REFERENCES commerce_orders (id),
            CONSTRAINT commerce_conversations_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE UNIQUE INDEX commerce_conversation_unique ON commerce_conversations (customer_id,
    shop_id, order_id) NULLS NOT DISTINCT
    """,
    """
    CREATE TABLE commerce_after_sale_lines (
            case_id UUID NOT NULL,
            order_id UUID NOT NULL,
            order_line_id UUID NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_minor_snapshot INTEGER NOT NULL,
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(case_id, order_id) REFERENCES commerce_after_sale_cases (id, order_id),
            FOREIGN KEY(order_line_id, order_id) REFERENCES commerce_order_lines (id, order_id),
            UNIQUE (case_id, order_line_id),
            CHECK (quantity BETWEEN 1 AND 99 AND unit_price_minor_snapshot > 0),
            FOREIGN KEY(case_id) REFERENCES commerce_after_sale_cases (id),
            FOREIGN KEY(order_id) REFERENCES commerce_orders (id),
            FOREIGN KEY(order_line_id) REFERENCES commerce_order_lines (id),
            CONSTRAINT commerce_after_sale_lines_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE commerce_messages (
            conversation_id UUID NOT NULL,
            sender_account_id UUID NOT NULL,
            sender_side VARCHAR(10) NOT NULL,
            body TEXT NOT NULL,
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CHECK (sender_side IN ('CUSTOMER','MERCHANT')),
            CHECK (length(btrim(body)) BETWEEN 1 AND 2000),
            FOREIGN KEY(conversation_id) REFERENCES commerce_conversations (id),
            FOREIGN KEY(sender_account_id) REFERENCES commerce_accounts (id),
            CONSTRAINT commerce_messages_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE TABLE commerce_refund_attempts (
            after_sale_id UUID NOT NULL,
            amount_minor BIGINT NOT NULL,
            currency VARCHAR(3) NOT NULL,
            state VARCHAR(20) NOT NULL,
            simulation BOOLEAN NOT NULL,
            provider_reference TEXT,
            finished_at TIMESTAMP WITH TIME ZONE,
            failure_code VARCHAR(40),
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CHECK (state IN ('PENDING','SUCCEEDED','FAILED')),
            CHECK (amount_minor > 0 AND simulation AND currency='CNY'),
            FOREIGN KEY(after_sale_id) REFERENCES commerce_after_sale_cases (id),
            CONSTRAINT commerce_refund_attempts_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE UNIQUE INDEX commerce_one_pending_refund ON commerce_refund_attempts (after_sale_id)
    WHERE state='PENDING'
    """,
    """
    CREATE UNIQUE INDEX commerce_one_success_refund ON commerce_refund_attempts (after_sale_id)
    WHERE state='SUCCEEDED'
    """,
    """
    CREATE TABLE commerce_return_shipments (
            case_id UUID NOT NULL,
            tracking_number VARCHAR(100) NOT NULL,
            state VARCHAR(20) NOT NULL,
            restock BOOLEAN,
            registered_at TIMESTAMP WITH TIME ZONE NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CHECK (state IN ('IN_TRANSIT','RECEIVED')),
            CHECK ((state='IN_TRANSIT' AND restock IS NULL AND received_at IS NULL) OR
    (state='RECEIVED' AND restock IS NOT NULL AND received_at IS NOT NULL)),
            UNIQUE (case_id),
            FOREIGN KEY(case_id) REFERENCES commerce_after_sale_cases (id),
            CONSTRAINT commerce_return_shipments_positive_version CHECK (version > 0)
    )
    """,
    """
    CREATE TRIGGER commerce_messages_immutable BEFORE UPDATE OR DELETE ON commerce_messages FOR
    EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_conversations_immutable BEFORE UPDATE OR DELETE ON
    commerce_conversations FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE TRIGGER commerce_after_sale_lines_immutable BEFORE UPDATE OR DELETE ON
    commerce_after_sale_lines FOR EACH ROW EXECUTE FUNCTION commerce_append_only()
    """,
    """
    CREATE FUNCTION commerce_refund_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR OLD.state <> 'PENDING' OR NEW.after_sale_id <> OLD.after_sale_id OR
    NEW.amount_minor <> OLD.amount_minor OR NEW.currency <> OLD.currency OR NOT NEW.simulation OR
    NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at OR NEW.state NOT IN
    ('SUCCEEDED','FAILED')
    THEN RAISE EXCEPTION 'immutable refund record'; END IF; RETURN NEW; END; $$
    """,
    """
    CREATE TRIGGER commerce_refund_guard BEFORE UPDATE OR DELETE ON commerce_refund_attempts FOR
    EACH ROW EXECUTE FUNCTION commerce_refund_guard()
    """,
)


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    op.drop_table("commerce_return_shipments")
    op.drop_table("commerce_refund_attempts")
    op.drop_table("commerce_messages")
    op.drop_table("commerce_after_sale_lines")
    op.drop_table("commerce_conversations")
    op.drop_table("commerce_after_sale_cases")
    op.execute("DROP FUNCTION commerce_refund_guard()")
    op.drop_constraint("commerce_order_conversation_scope", "commerce_orders", type_="unique")
