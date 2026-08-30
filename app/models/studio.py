import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudioConversationModel(Base):
    """A Studio prompt-to-UI conversation, i.e. a "project": one named,
    persistent thread. The turns live in ``StudioMessageModel``; this row
    only holds identity, a display name, and timestamps for listing."""

    __tablename__ = "studio_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StudioConversationFeedbackModel(Base):
    """A user rating of how well recent Studio generations served them.

    Scoped to the project (``conversation_id``), not a single message: the
    LLM composer folds recent ratings back into its own prompt as
    conversation-level guidance (see ``app.studio.llm``), so per-turn
    attribution isn't needed."""

    __tablename__ = "studio_conversation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studio_conversations.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class StudioMessageModel(Base):
    """One turn of a Studio conversation.

    ``layout`` is only set on assistant turns that actually produced a
    layout (``generatedBy == "llm"``); a blank-fallback turn keeps it null
    so the next request doesn't treat a "not available" screen as the thing
    to edit. ``suggestion`` is the model's optional, forward-looking UX tip
    about the prompt — distinct from ``content`` (the ``reason`` explaining
    what was actually built) — and is likewise only set on ``llm`` turns.
    Rows beyond the retention cap are deleted by ``app.studio.store``, not by
    a database-side policy."""

    __tablename__ = "studio_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studio_conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    layout: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
