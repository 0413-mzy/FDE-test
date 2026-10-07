"""Frozen append-only commerce history; never rewrites business rows."""

from alembic import op

revision = "0006_commerce_history"
down_revision = "0005_commerce_onboarding"
branch_labels = None
depends_on = None

# Frozen independently of runtime models, including explicit safe column names.
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
SENSITIVE_CHANGED_FIELDS = {
    "commerce_accounts": ("password_hash",),
    "commerce_sessions": ("token_digest",),
    "commerce_email_challenges": ("token_digest",),
}

DDL = """
CREATE TABLE commerce_record_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_table TEXT NOT NULL,
    entity_id UUID NOT NULL,
    operation VARCHAR(8) NOT NULL CHECK(operation IN ('BASELINE','INSERT','UPDATE','DELETE')),
    before_data JSONB,
    after_data JSONB,
    changed_fields TEXT[] NOT NULL,
    actor_id UUID,
    actor_username VARCHAR(80),
    db_role TEXT NOT NULL,
    request_id VARCHAR(100),
    action VARCHAR(120) NOT NULL,
    reason VARCHAR(500),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK ((operation IN ('BASELINE','INSERT') AND before_data IS NULL AND after_data IS NOT NULL)
        OR (operation='UPDATE' AND before_data IS NOT NULL AND after_data IS NOT NULL)
        OR (operation='DELETE' AND before_data IS NOT NULL AND after_data IS NULL))
);
CREATE INDEX commerce_history_entity ON commerce_record_history(entity_table, entity_id, id);
CREATE INDEX commerce_history_time ON commerce_record_history(recorded_at, id);
CREATE FUNCTION commerce_history_record() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
    old_row JSONB;
    new_row JSONB;
    before_safe JSONB;
    after_safe JSONB;
    fields TEXT[] := string_to_array(TG_ARGV[0], ',');
    monitored TEXT[] := fields || string_to_array(TG_ARGV[1], ',');
    changed TEXT[];
BEGIN
    IF TG_OP <> 'INSERT' THEN old_row := to_jsonb(OLD); END IF;
    IF TG_OP <> 'DELETE' THEN new_row := to_jsonb(NEW); END IF;
    IF TG_OP='UPDATE' AND old_row IS NOT DISTINCT FROM new_row THEN RETURN NEW; END IF;
    IF old_row IS NOT NULL THEN
        SELECT jsonb_object_agg(key,value) INTO before_safe
        FROM jsonb_each(old_row) WHERE key=ANY(fields);
    END IF;
    IF new_row IS NOT NULL THEN
        SELECT jsonb_object_agg(key,value) INTO after_safe
        FROM jsonb_each(new_row) WHERE key=ANY(fields);
    END IF;
    SELECT COALESCE(array_agg(key ORDER BY key), ARRAY[]::text[]) INTO changed
    FROM unnest(monitored) AS key
    WHERE TG_OP <> 'UPDATE' OR old_row->key IS DISTINCT FROM new_row->key;
    EXECUTE format('INSERT INTO %I.commerce_record_history
        (entity_table,entity_id,operation,before_data,after_data,changed_fields,
         actor_id,actor_username,db_role,request_id,action,reason)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)', TG_TABLE_SCHEMA)
    USING TG_TABLE_NAME, COALESCE(new_row->>'id',old_row->>'id')::uuid, TG_OP,
        before_safe, after_safe, changed,
        NULLIF(current_setting('commerce_history.actor_id',true),'')::uuid,
        NULLIF(current_setting('commerce_history.actor_username',true),''), current_user::text,
        NULLIF(current_setting('commerce_history.request_id',true),''),
        COALESCE(NULLIF(current_setting('commerce_history.action',true),''),'DIRECT_SQL'),
        NULLIF(current_setting('commerce_history.reason',true),'');
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END
$fn$;
CREATE FUNCTION commerce_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    RAISE EXCEPTION 'commerce record history is append-only';
END
$fn$;
CREATE TRIGGER commerce_history_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON commerce_record_history FOR EACH STATEMENT EXECUTE FUNCTION commerce_history_immutable();
"""


def upgrade():
    op.execute(DDL)
    for table, fields in FIELD_POLICY.items():
        safe = ",".join(fields)
        sensitive = ",".join(SENSITIVE_CHANGED_FIELDS.get(table, ()))
        op.execute(
            f"CREATE TRIGGER commerce_history_record AFTER INSERT OR UPDATE OR DELETE "
            f"ON {table} FOR EACH ROW EXECUTE FUNCTION "
            f"commerce_history_record('{safe}','{sensitive}')"
        )
        keys = ",".join("'" + field + "'" for field in fields)
        op.execute(
            f"INSERT INTO commerce_record_history "
            f"(entity_table,entity_id,operation,after_data,changed_fields,db_role,action) "
            f"SELECT '{table}', id, 'BASELINE', "
            f"(SELECT jsonb_object_agg(key,value) FROM jsonb_each(to_jsonb(t)) "
            f"WHERE key IN ({keys})), ARRAY[]::text[], current_user, 'MIGRATION_BASELINE' "
            f"FROM {table} t"
        )


def downgrade():
    for table in reversed(FIELD_POLICY):
        op.execute(f"DROP TRIGGER commerce_history_record ON {table}")
    op.execute("DROP FUNCTION commerce_history_record()")
    op.execute("DROP TABLE commerce_record_history")
    op.execute("DROP FUNCTION commerce_history_immutable()")
