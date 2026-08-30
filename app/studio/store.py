"""Server-persisted memory for Studio conversations ("projects").

Kept deliberately separate from the run engine: a conversation is not a run,
has no policy/actions, and its only job is remembering recent turns so the
LLM can edit instead of rebuild, plus letting the UI list and reopen past
projects. Retention is capped per conversation so the table can't grow
without bound (see ``DEFAULT_HISTORY_LIMIT``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import StudioConversationModel, StudioMessageModel
from app.schemas.contracts import AssistMessage
from app.studio.schema import StudioPageNode


DEFAULT_HISTORY_LIMIT = 20


@dataclass(frozen=True)
class StoredMessage:
    id: uuid.UUID
    role: str
    content: str
    layout: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class StoredConversation:
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


def _to_history(rows: list[StoredMessage]) -> list[AssistMessage]:
    """Oldest-first ``AssistMessage`` list, as the LLM payload expects."""

    return [AssistMessage(role=row.role, content=row.content) for row in rows]


def _latest_layout(rows: list[StoredMessage]) -> StudioPageNode | None:
    """The most recent assistant turn that actually produced a layout.

    A blank-fallback turn (``layout is None``) is skipped so a "not
    available" screen is never mistaken for something to edit.
    """

    for row in reversed(rows):
        if row.role == "assistant" and row.layout is not None:
            return StudioPageNode.model_validate(row.layout)
    return None


def _ids_to_prune(rows: list[StoredMessage], *, keep: int) -> list[uuid.UUID]:
    """Ids of the oldest rows beyond the retention cap, oldest-first input."""

    overflow = len(rows) - keep
    if overflow <= 0:
        return []
    return [row.id for row in rows[:overflow]]


class StudioConversationStore:
    def __init__(self, session: AsyncSession, *, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self.session = session
        self.history_limit = history_limit

    async def create_conversation(self, name: str = "") -> uuid.UUID:
        conversation = StudioConversationModel(name=name)
        self.session.add(conversation)
        await self.session.flush()
        return conversation.id

    async def conversation_exists(self, conversation_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(StudioConversationModel.id).where(StudioConversationModel.id == conversation_id)
        )
        return result.scalar_one_or_none() is not None

    async def get_conversation(self, conversation_id: uuid.UUID) -> StoredConversation | None:
        result = await self.session.execute(
            select(StudioConversationModel).where(StudioConversationModel.id == conversation_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return StoredConversation(id=row.id, name=row.name, created_at=row.created_at, updated_at=row.updated_at)

    async def list_conversations(self) -> list[StoredConversation]:
        """Most recently active project first."""

        result = await self.session.execute(
            select(StudioConversationModel).order_by(StudioConversationModel.updated_at.desc())
        )
        return [
            StoredConversation(id=row.id, name=row.name, created_at=row.created_at, updated_at=row.updated_at)
            for row in result.scalars().all()
        ]

    async def _rows(self, conversation_id: uuid.UUID) -> list[StoredMessage]:
        result = await self.session.execute(
            select(StudioMessageModel)
            .where(StudioMessageModel.conversation_id == conversation_id)
            .order_by(StudioMessageModel.created_at.asc())
        )
        return [
            StoredMessage(
                id=row.id, role=row.role, content=row.content, layout=row.layout, created_at=row.created_at
            )
            for row in result.scalars().all()
        ]

    async def get_messages(self, conversation_id: uuid.UUID) -> list[StoredMessage]:
        """Full turn history for the project detail view, oldest first."""

        return await self._rows(conversation_id)

    async def get_history(self, conversation_id: uuid.UUID) -> list[AssistMessage]:
        return _to_history(await self._rows(conversation_id))

    async def get_last_layout(self, conversation_id: uuid.UUID) -> StudioPageNode | None:
        return _latest_layout(await self._rows(conversation_id))

    async def append_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        *,
        layout: StudioPageNode | None = None,
    ) -> None:
        self.session.add(
            StudioMessageModel(
                conversation_id=conversation_id,
                role=role,
                content=content,
                layout=layout.model_dump(mode="json", by_alias=True) if layout is not None else None,
            )
        )
        result = await self.session.execute(
            select(StudioConversationModel).where(StudioConversationModel.id == conversation_id)
        )
        conversation = result.scalar_one()
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def prune(self, conversation_id: uuid.UUID) -> None:
        stale_ids = _ids_to_prune(await self._rows(conversation_id), keep=self.history_limit)
        if not stale_ids:
            return
        await self.session.execute(delete(StudioMessageModel).where(StudioMessageModel.id.in_(stale_ids)))
