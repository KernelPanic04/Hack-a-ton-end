import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudioConversationModel(Base):
    """A Studio prompt-to-UI conversation. Holds no state of its own beyond
    its identity and timestamps; the turns live in ``StudioMessageModel``."""

    __tablename__ = "studio_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class StudioMessageModel(Base):
    """One turn of a Studio conversation.

    ``layout`` is only set on assistant turns that actually produced a
    layout (``generatedBy == "llm"``); a blank-fallback turn keeps it null
    so the next request doesn't treat a "not available" screen as the thing
    to edit. Rows beyond the retention cap are deleted by
    ``app.studio.store``, not by a database-side policy."""

    __tablename__ = "studio_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studio_conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    layout: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
