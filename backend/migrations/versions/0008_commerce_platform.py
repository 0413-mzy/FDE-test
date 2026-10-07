"""Frozen additive platform operations schema and explicit safe history policy."""

from alembic import op

revision = "0008_commerce_platform"
down_revision = "0007_commerce_catalog"
branch_labels = None
depends_on = None
COMMON = (
    "id uuid PRIMARY KEY, version integer NOT NULL DEFAULT 1 CHECK(version > 0), "
    "created_at timestamptz NOT NULL DEFAULT now(), updated_at "
    "timestamptz NOT NULL DEFAULT now()"
)
TABLES = {
    "commerce_platform_roles": (
        "account_id uuid NOT NULL UNIQUE REFERENCES "
        "commerce_accounts(id), active boolean NOT NULL DEFAULT true"
    ),
    "commerce_moderation_reports": (
        "reporter_id uuid NOT NULL REFERENCES commerce_accounts(id), "
        "target_type varchar(20) NOT NULL CHECK(target_type IN "
        "('PRODUCT','SHOP','REVIEW')), target_id uuid NOT NULL, reason "
        "text NOT NULL, state varchar(20) NOT NULL DEFAULT 'OPEN' "
        "CHECK(state IN ('OPEN','RESOLVED','DISMISSED')), decision_reason "
        "text"
    ),
    "commerce_moderation_actions": (
        "actor_id uuid NOT NULL REFERENCES commerce_accounts(id), "
        "target_type varchar(20) NOT NULL, target_id uuid NOT NULL, "
        "action varchar(30) NOT NULL, reason text NOT NULL, report_id "
        "uuid REFERENCES commerce_moderation_reports(id)"
    ),
    "commerce_disputes": (
        "customer_id uuid NOT NULL REFERENCES commerce_accounts(id), "
        "order_id uuid NOT NULL REFERENCES commerce_orders(id), case_id "
        "uuid NOT NULL REFERENCES commerce_after_sale_cases(id), shop_id "
        "uuid NOT NULL REFERENCES commerce_shops(id), reason text NOT "
        "NULL, state varchar(20) NOT NULL DEFAULT 'OPEN' CHECK(state IN "
        "('OPEN','UPHELD','OVERTURNED','WITHDRAWN')), customer_evidence "
        "text NOT NULL DEFAULT '', merchant_evidence text NOT NULL "
        "DEFAULT '', decision_reason text, decided_by uuid REFERENCES "
        "commerce_accounts(id), "
        "FOREIGN KEY(case_id,order_id) REFERENCES commerce_after_sale_cases(id,order_id), "
        "FOREIGN KEY(order_id,customer_id,shop_id) "
        "REFERENCES commerce_orders(id,customer_id,shop_id)"
    ),
}
FIELD_POLICY = {
    "commerce_platform_roles": ("account_id", "active"),
    "commerce_moderation_reports": (
        "reporter_id",
        "target_type",
        "target_id",
        "reason",
        "state",
        "decision_reason",
    ),
    "commerce_moderation_actions": (
        "actor_id",
        "target_type",
        "target_id",
        "action",
        "reason",
        "report_id",
    ),
    "commerce_disputes": (
        "customer_id",
        "order_id",
        "case_id",
        "shop_id",
        "reason",
        "state",
        "customer_evidence",
        "merchant_evidence",
        "decision_reason",
        "decided_by",
    ),
}


def upgrade():
    for table, columns in TABLES.items():
        op.execute(f"CREATE TABLE {table} ({COMMON}, {columns})")
    op.execute(
        "CREATE UNIQUE INDEX commerce_one_open_report ON "
        "commerce_moderation_reports(reporter_id,target_type,target_id) "
        "WHERE state='OPEN'"
    )
    op.execute(
        "CREATE UNIQUE INDEX commerce_one_open_dispute ON "
        "commerce_disputes(case_id) WHERE state='OPEN'"
    )
    for table, fields in FIELD_POLICY.items():
        safe = ",".join(("id", "version", "created_at", "updated_at", *fields))
        op.execute(
            f"CREATE TRIGGER commerce_history_record AFTER INSERT OR UPDATE OR DELETE "
            f"ON {table} FOR EACH ROW EXECUTE FUNCTION commerce_history_record('{safe}','')"
        )


def downgrade():
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
