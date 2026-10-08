"""Safe logistics input snapshots; old attempts remain unknown."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_ai_logistics_context"
down_revision = "0010_logistics_control"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("commerce_ai_attempts", sa.Column("logistics_context", JSONB(), nullable=True))


def downgrade():
    op.drop_column("commerce_ai_attempts", "logistics_context")
