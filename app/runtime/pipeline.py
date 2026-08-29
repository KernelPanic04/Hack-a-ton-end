"""Coordinates a committed runtime transition with deterministic UI delivery."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.run import RunEngine
from app.schemas.contracts import UIUpdatedEnvelope, UIUpdatedPayload
from app.synthesis import DeterministicComposer
from app.ws import RunWebSocketHub


class RuntimePipeline:
    def __init__(
        self,
        session: AsyncSession,
        hub: RunWebSocketHub,
        composer: DeterministicComposer | None = None,
    ) -> None:
        self.engine = RunEngine(session)
        self.hub = hub
        self.composer = composer or DeterministicComposer()

    async def publish_current(self, run_id: uuid.UUID) -> UIUpdatedEnvelope:
        projection = await self.engine.get_projection(run_id)
        ui_spec = self.composer.compose(projection)
        event = await self.engine.save_ui_spec(run_id, ui_spec)
        projection = await self.engine.get_projection(run_id)
        envelope = UIUpdatedEnvelope(
            type="UI_UPDATED",
            run_id=projection.run_id,
            sequence=event.sequence,
            timestamp=datetime.now(timezone.utc),
            payload=UIUpdatedPayload(event=event, projection=projection, ui_spec=ui_spec),
        )
        await self.hub.publish(envelope)
        return envelope

    async def latest_envelope(self, run_id: uuid.UUID) -> UIUpdatedEnvelope | None:
        """Rebuild the latest UI envelope for a newly connected subscriber."""
        ui_spec = await self.engine.get_last_ui_spec(run_id)
        if ui_spec is None:
            return None
        projection = await self.engine.get_projection(run_id)
        events = await self.engine.get_event_log(run_id)
        event = next((item for item in reversed(events) if item.type == "UI_UPDATED"), None)
        if event is None:
            return None
        return UIUpdatedEnvelope(
            type="UI_UPDATED",
            run_id=projection.run_id,
            sequence=event.sequence,
            timestamp=datetime.now(timezone.utc),
            payload=UIUpdatedPayload(event=event, projection=projection, ui_spec=ui_spec),
        )
