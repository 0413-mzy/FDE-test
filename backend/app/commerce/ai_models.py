from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.commerce.models import Base
from app.db.models import UtcDateTime


class AIAttempt(Base):
    __tablename__ = "commerce_ai_attempts"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    cached_from: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_ai_attempts.id"))
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_conversations.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    source_ids: Mapped[list] = mapped_column(JSONB)
    message_count: Mapped[int]
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20))
    lease_until: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(50))
    logistics_context: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[list] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("actor_id", "conversation_id", "idempotency_key"),
        CheckConstraint("state IN ('RUNNING','SUCCEEDED','FAILED')"),
        Index(
            "commerce_ai_one_running",
            "conversation_id",
            unique=True,
            postgresql_where=text("state='RUNNING'"),
        ),
        Index("commerce_ai_actor_time", "actor_id", "created_at"),
        Index("commerce_ai_time", "created_at"),
    )
