"""In-memory Studio conversation memory.

Deliberately volatile, mirroring how ``RunWebSocketHub`` already keeps run
state in memory in this backend: a process restart clears every
conversation. While the process stays up, each conversation keeps its own
history and last generated layout for up to ``RETENTION`` (two months)
before those turns age out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.contracts import AssistMessage
from app.studio.schema import StudioPageNode


RETENTION = timedelta(days=60)

# Independent of retention: how many recent turns are actually sent to the
# LLM as context. Two months of a busy conversation could still be far more
# tokens than any prompt should carry.
MAX_HISTORY_TURNS = 40


@dataclass(frozen=True)
class StoredMessage:
    role: str
    content: str
    layout: dict[str, Any] | None
    created_at: datetime


class StudioConversationStore:
    def __init__(
        self, *, retention: timedelta = RETENTION, max_history: int = MAX_HISTORY_TURNS
    ) -> None:
        self._conversations: dict[uuid.UUID, list[StoredMessage]] = {}
        self._retention = retention
        self._max_history = max_history

    def create_conversation(self) -> uuid.UUID:
        conversation_id = uuid.uuid4()
        self._conversations[conversation_id] = []
        return conversation_id

    def conversation_exists(self, conversation_id: uuid.UUID) -> bool:
        return conversation_id in self._conversations

    def append_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        *,
        layout: StudioPageNode | None = None,
        now: datetime | None = None,
    ) -> None:
        messages = self._conversations.setdefault(conversation_id, [])
        messages.append(
            StoredMessage(
                role=role,
                content=content,
                layout=layout.model_dump(mode="json", by_alias=True) if layout is not None else None,
                created_at=now or datetime.now(timezone.utc),
            )
        )

    def get_history(self, conversation_id: uuid.UUID, *, now: datetime | None = None) -> list[AssistMessage]:
        messages = self._sweep(conversation_id, now=now)[-self._max_history :]
        return [AssistMessage(role=message.role, content=message.content) for message in messages]

    def get_last_layout(
        self, conversation_id: uuid.UUID, *, now: datetime | None = None
    ) -> StudioPageNode | None:
        for message in reversed(self._sweep(conversation_id, now=now)):
            if message.role == "assistant" and message.layout is not None:
                return StudioPageNode.model_validate(message.layout)
        return None

    def _sweep(self, conversation_id: uuid.UUID, *, now: datetime | None = None) -> list[StoredMessage]:
        """Drop turns older than the retention window; return what remains."""

        current_time = now or datetime.now(timezone.utc)
        messages = self._conversations.get(conversation_id, [])
        fresh = [message for message in messages if current_time - message.created_at <= self._retention]
        if conversation_id in self._conversations:
            self._conversations[conversation_id] = fresh
        return fresh
