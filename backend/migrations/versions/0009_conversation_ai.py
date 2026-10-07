"""Additive durable conversation assistance attempts; preserve business rows."""

from alembic import op

revision = "0009_conversation_ai"
down_revision = "0008_commerce_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE commerce_ai_attempts (
      id uuid PRIMARY KEY, cached_from uuid REFERENCES commerce_ai_attempts(id),
      conversation_id uuid NOT NULL REFERENCES commerce_conversations(id),
      actor_id uuid NOT NULL REFERENCES commerce_accounts(id),
      idempotency_key varchar(100) NOT NULL,
      snapshot_hash varchar(64) NOT NULL, source_ids jsonb NOT NULL, message_count integer NOT NULL,
      model varchar(100) NOT NULL, prompt_version varchar(100) NOT NULL,
      state varchar(20) NOT NULL CHECK(state IN ('RUNNING','SUCCEEDED','FAILED')),
      lease_until timestamptz NOT NULL, created_at timestamptz NOT NULL, finished_at timestamptz,
      result jsonb, error_code varchar(50), usage jsonb NOT NULL DEFAULT '[]',
      UNIQUE(actor_id,conversation_id,idempotency_key))""")
    op.execute(
        "CREATE UNIQUE INDEX commerce_ai_one_running ON commerce_ai_attempts(conversation_id) "
        "WHERE state='RUNNING'"
    )
    op.execute("CREATE INDEX commerce_ai_actor_time ON commerce_ai_attempts(actor_id,created_at)")
    op.execute("CREATE INDEX commerce_ai_time ON commerce_ai_attempts(created_at)")


def downgrade():
    op.execute("DROP TABLE commerce_ai_attempts")
