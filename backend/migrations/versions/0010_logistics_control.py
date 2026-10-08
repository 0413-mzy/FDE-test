"""Add manual simulated carrier stages and attribution; preserve all existing rows."""

import sqlalchemy as sa
from alembic import op

revision = "0010_logistics_control"
down_revision = "0009_conversation_ai"
branch_labels = None
depends_on = None

# Frozen safe projections: deployed migration cannot import changing runtime policy.
FIELDS = {
    "commerce_shipments": (
        "order_id,tracking_number,status,simulation,shipped_at,delivered_at,"
        "exception_reason,exception_from_status,id,version,created_at,updated_at"
    ),
    "commerce_tracking_events": (
        "shipment_id,event_id,kind,description,occurred_at,sequence,source,location,"
        "reason,actor_id,status_applied,request_version,id,version,created_at,updated_at"
    ),
}


def upgrade():
    op.execute(
        "ALTER TABLE commerce_shipments ADD COLUMN exception_reason "
        "varchar(30), ADD COLUMN exception_from_status varchar(20)"
    )
    op.execute(
        "ALTER TABLE commerce_tracking_events ADD COLUMN location "
        "varchar(200), ADD COLUMN reason varchar(30), ADD COLUMN actor_id "
        "uuid REFERENCES commerce_accounts(id), ADD COLUMN status_applied "
        "boolean, ADD COLUMN request_version integer"
    )
    # Existing anonymous PostgreSQL CHECK names are deterministic for these tables.
    op.execute(
        "ALTER TABLE commerce_shipments DROP CONSTRAINT "
        "commerce_shipments_status_check, ADD CONSTRAINT "
        "commerce_shipments_status_check CHECK(status IN ('SHIPPED',"
        "'COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY','EXCEPTION',"
        "'DELIVERED'))"
    )
    op.execute(
        "ALTER TABLE commerce_tracking_events DROP CONSTRAINT "
        "commerce_tracking_events_kind_check, ADD CONSTRAINT "
        "commerce_tracking_events_kind_check CHECK(kind IN ('SHIPPED',"
        "'COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY','EXCEPTION',"
        "'DELIVERED'))"
    )
    op.execute(
        "ALTER TABLE commerce_shipments ADD CONSTRAINT "
        "commerce_shipments_exception_reason_check CHECK(exception_reason "
        "IS NULL OR exception_reason IN ('TRANSPORT_DELAY',"
        "'DELIVERY_FAILED')), ADD CONSTRAINT "
        "commerce_shipments_exception_from_check "
        "CHECK(exception_from_status IS NULL OR exception_from_status IN "
        "('COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY'))"
    )
    op.execute(
        "ALTER TABLE commerce_tracking_events ADD CONSTRAINT "
        "commerce_tracking_events_reason_check CHECK(reason IS NULL OR "
        "reason IN ('TRANSPORT_DELAY','DELIVERY_FAILED')), ADD CONSTRAINT "
        "commerce_tracking_events_request_version_check "
        "CHECK(request_version IS NULL OR request_version > 0)"
    )
    for table, fields in FIELDS.items():
        op.execute(f"DROP TRIGGER commerce_history_record ON {table}")
        op.execute(
            "CREATE TRIGGER commerce_history_record AFTER INSERT OR UPDATE OR "
            f"DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION "
            f"commerce_history_record('{fields}','')"
        )


def downgrade():
    # Empty/legacy-only test schemas can roundtrip; never lose new business facts.
    occupied = op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM commerce_shipments
            WHERE status IN ('COLLECTED','OUT_FOR_DELIVERY')
               OR exception_reason IS NOT NULL OR exception_from_status IS NOT NULL)
        OR EXISTS(SELECT 1 FROM commerce_tracking_events
            WHERE kind IN ('COLLECTED','OUT_FOR_DELIVERY') OR location IS NOT NULL
               OR reason IS NOT NULL OR actor_id IS NOT NULL
               OR status_applied IS NOT NULL OR request_version IS NOT NULL)
    """)
    )
    if occupied:
        raise RuntimeError("Logistics downgrade would lose business facts")
    for table, fields in FIELDS.items():
        original = ",".join(
            f
            for f in fields.split(",")
            if f
            not in {
                "exception_reason",
                "exception_from_status",
                "location",
                "reason",
                "actor_id",
                "status_applied",
                "request_version",
            }
        )
        op.execute(f"DROP TRIGGER commerce_history_record ON {table}")
        op.execute(
            "CREATE TRIGGER commerce_history_record AFTER INSERT OR UPDATE OR DELETE "
            f"ON {table} FOR EACH ROW EXECUTE FUNCTION "
            f"commerce_history_record('{original}','')"
        )
    op.execute(
        "ALTER TABLE commerce_shipments DROP CONSTRAINT commerce_shipments_status_check, "
        "DROP CONSTRAINT commerce_shipments_exception_reason_check, "
        "DROP CONSTRAINT commerce_shipments_exception_from_check, "
        "DROP COLUMN exception_reason, DROP COLUMN exception_from_status, "
        "ADD CONSTRAINT commerce_shipments_status_check "
        "CHECK(status IN ('SHIPPED','IN_TRANSIT','EXCEPTION','DELIVERED'))"
    )
    op.execute(
        "ALTER TABLE commerce_tracking_events DROP CONSTRAINT commerce_tracking_events_kind_check, "
        "DROP CONSTRAINT commerce_tracking_events_reason_check, "
        "DROP CONSTRAINT commerce_tracking_events_request_version_check, "
        "DROP COLUMN location, DROP COLUMN reason, DROP COLUMN actor_id, "
        "DROP COLUMN status_applied, DROP COLUMN request_version, "
        "ADD CONSTRAINT commerce_tracking_events_kind_check "
        "CHECK(kind IN ('SHIPPED','IN_TRANSIT','EXCEPTION','DELIVERED'))"
    )
