"""Reject whitespace-only values without rewriting records or frozen revision 0001."""

from alembic import op

revision = "0002_nonblank_constraints"
down_revision = "0001_core_mvp"
branch_labels = None
depends_on = None

# Frozen SQL pairs, independent of the current ORM. PostgreSQL validates existing
# rows when adding each CHECK; invalid legacy data aborts the migration transaction.
CONSTRAINTS = (
    (
        "inquiries",
        "external_inquiry_id",
        "btrim(external_inquiry_id) <> ''",
        "external_inquiry_id ~ '[^[:space:]]'",
    ),
    (
        "inquiries",
        "external_order_id",
        "external_order_id IS NULL OR btrim(external_order_id) <> ''",
        "external_order_id IS NULL OR external_order_id ~ '[^[:space:]]'",
    ),
    (
        "inquiries",
        "escalation_reason",
        "(state = 'ESCALATED' AND escalation_reason IS NOT NULL "
        "AND btrim(escalation_reason) <> '') OR "
        "(state <> 'ESCALATED' AND escalation_reason IS NULL)",
        "(state = 'ESCALATED' AND escalation_reason IS NOT NULL "
        "AND escalation_reason ~ '[^[:space:]]') OR "
        "(state <> 'ESCALATED' AND escalation_reason IS NULL)",
    ),
    (
        "resolution_runs",
        "idempotency_key",
        "btrim(idempotency_key) <> ''",
        "idempotency_key ~ '[^[:space:]]'",
    ),
    (
        "generation_attempts",
        "idempotency_key",
        "btrim(idempotency_key) <> ''",
        "idempotency_key ~ '[^[:space:]]'",
    ),
    (
        "draft_revisions",
        "reply_text",
        "length(reply_text) BETWEEN 1 AND 10000 AND btrim(reply_text) <> ''",
        "length(reply_text) BETWEEN 1 AND 10000 AND reply_text ~ '[^[:space:]]'",
    ),
    (
        "approvals",
        "idempotency_key",
        "btrim(idempotency_key) <> ''",
        "idempotency_key ~ '[^[:space:]]'",
    ),
)


def upgrade():
    for table, suffix, _, improved in CONSTRAINTS:
        name = op.f(f"ck_{table}_{suffix}")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, improved)


def downgrade():
    for table, suffix, original, _ in reversed(CONSTRAINTS):
        name = op.f(f"ck_{table}_{suffix}")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, original)
