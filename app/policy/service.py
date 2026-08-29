"""Coordinates policy, runtime transitions, and typed WebSocket responses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.engine import ActionPolicyEngine, PolicyViolation
from app.runtime.pipeline import RuntimePipeline
from app.runtime.run import RunEngine, RunEngineError
from app.schemas.contracts import (
    ActionAcceptedEnvelope,
    ActionAcceptedPayload,
    ActionEvent,
    ActionRejectedEnvelope,
    ActionRejectedPayload,
)
from app.ws import RunWebSocketHub


class ActionCoordinator:
    def __init__(self, session: AsyncSession, hub: RunWebSocketHub) -> None:
        self.engine = RunEngine(session)
        self.policy = ActionPolicyEngine(session, self.engine)
        self.hub = hub

    async def handle(self, event: ActionEvent, run_id: uuid.UUID) -> None:
        try:
            await self.policy.validate(event, run_id)
            await self.engine.resolve_decision(
                run_id,
                event.action_id,
                event.payload,
                event.state_version,
                idempotency_key=event.idempotency_key,
            )
        except PolicyViolation as exc:
            await self._reject(event, run_id, exc.code, exc.message)
            return
        except RunEngineError as exc:
            await self._reject(event, run_id, "RUNTIME_REJECTED", str(exc), record=False)
            return

        projection = await self.engine.get_projection(run_id)
        accepted_event = next(
            item for item in reversed(await self.engine.get_event_log(run_id))
            if item.type == "ACTION_ACCEPTED"
        )
        accepted = ActionAcceptedEnvelope(
            type="ACTION_ACCEPTED",
            run_id=projection.run_id,
            sequence=accepted_event.sequence,
            timestamp=datetime.now(timezone.utc),
            payload=ActionAcceptedPayload(
                event=accepted_event,
                projection=projection,
                idempotency_key=event.idempotency_key,
                decision_id=event.decision_id,
                action_id=event.action_id,
            ),
        )
        await self.hub.publish(accepted)
        await RuntimePipeline(self.engine.session, self.hub).publish_current(run_id)

    async def _reject(
        self,
        action: ActionEvent,
        run_id: uuid.UUID,
        code: str,
        message: str,
        *,
        record: bool = True,
    ) -> None:
        event = (
            await self.engine.record_action_rejection(run_id, action.action_id, code)
            if record
            else (await self.engine.get_event_log(run_id))[-1]
        )
        projection = await self.engine.get_projection(run_id)
        rejected = ActionRejectedEnvelope(
            type="ACTION_REJECTED",
            run_id=projection.run_id,
            sequence=event.sequence,
            timestamp=datetime.now(timezone.utc),
            payload=ActionRejectedPayload(
                event=event,
                code=code,
                message=message,
                idempotency_key=action.idempotency_key,
                current_state_version=projection.state_version,
            ),
        )
        await self.hub.publish(rejected)
