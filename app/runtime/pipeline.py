"""Coordinates a committed transition with progressive UI delivery."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.runtime.run import RunEngine, RunEngineError
from app.schemas.contracts import RunProjection, UISpec, UIUpdatedEnvelope, UIUpdatedPayload
from app.synthesis import DeterministicComposer, LLMComposer
from app.ws import RunWebSocketHub


class RuntimePipeline:
    def __init__(
        self,
        session: AsyncSession,
        hub: RunWebSocketHub,
        composer: DeterministicComposer | None = None,
        llm_composer: LLMComposer | None = None,
    ) -> None:
        self.engine = RunEngine(session)
        self.hub = hub
        self.composer = composer or DeterministicComposer()
        self.llm_composer = llm_composer or LLMComposer()

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
        if self.llm_composer.enabled:
            asyncio.create_task(
                self._publish_llm_upgrade(run_id, projection, ui_spec),
                name=f"llm-ui-upgrade:{projection.run_id}:{projection.state_version}",
            )
        return envelope

    async def _publish_llm_upgrade(
        self,
        run_id: uuid.UUID,
        projection: RunProjection,
        baseline: UISpec,
    ) -> None:
        """Publish an upgrade only while its deterministic baseline is current."""

        upgraded = await self.llm_composer.compose_upgrade(projection, baseline)
        if upgraded is None:
            return

        async with AsyncSessionLocal() as session:
            engine = RunEngine(session)
            try:
                current = await engine.get_projection(run_id)
                if current.state_version != baseline.state_version:
                    return
                event = await engine.save_ui_spec(run_id, upgraded)
                current = await engine.get_projection(run_id)
            except RunEngineError:
                return

        envelope = UIUpdatedEnvelope(
            type="UI_UPDATED",
            run_id=current.run_id,
            sequence=event.sequence,
            timestamp=datetime.now(timezone.utc),
            payload=UIUpdatedPayload(
                event=event, projection=current, ui_spec=upgraded
            ),
        )
        await self.hub.publish(envelope)

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
