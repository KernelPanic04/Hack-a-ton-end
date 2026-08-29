"""Coordinates policy, runtime transitions, and typed WebSocket responses."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.engine import ActionPolicyEngine, PolicyViolation
from app.runtime.run import RunEngine, RunEngineError
from app.schemas.contracts import (
    ActionAcceptedEnvelope,
    ActionAcceptedPayload,
    ActionEvent,
    ActionRejectedEnvelope,
    ActionRejectedPayload,
    RunEventType,
    ServerEnvelope,
)


class ActionCoordinator:
    def __init__(
        self,
        session: AsyncSession,
        engine: RunEngine | None = None,
        policy: ActionPolicyEngine | None = None,
    ) -> None:
        self.engine = engine or RunEngine(session)
        self.policy = policy or ActionPolicyEngine(session, self.engine)

    async def handle(self, event: ActionEvent, run_id: uuid.UUID) -> ServerEnvelope:
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
            return await self._reject(event, run_id, exc.code, exc.message)
        except RunEngineError as exc:
            return await self._reject(
                event, run_id, "RUNTIME_REJECTED", str(exc), record=False
            )

        projection = await self.engine.get_projection(run_id)
        accepted_event = await self.engine.latest_event(
            run_id, RunEventType.ACTION_ACCEPTED
        )
        if accepted_event is None:
            raise RuntimeError("resolve_decision did not append ACTION_ACCEPTED")
        accepted = ActionAcceptedEnvelope(
            type="ACTION_ACCEPTED",
            run_id=projection.run_id,
            sequence=accepted_event.sequence,
            timestamp=accepted_event.timestamp,
            payload=ActionAcceptedPayload(
                event=accepted_event,
                projection=projection,
                idempotency_key=event.idempotency_key,
                decision_id=event.decision_id,
                action_id=event.action_id,
            ),
        )
        return accepted

    async def _reject(
        self,
        action: ActionEvent,
        run_id: uuid.UUID,
        code: str,
        message: str,
        *,
        record: bool = True,
    ) -> ActionRejectedEnvelope:
        event = (
            await self.engine.record_action_rejection(run_id, action.action_id, code)
            if record
            else await self.engine.latest_event(run_id, RunEventType.ACTION_REJECTED)
        )
        if event is None:
            event = await self.engine.record_action_rejection(run_id, action.action_id, code)
        projection = await self.engine.get_projection(run_id)
        return ActionRejectedEnvelope(
            type="ACTION_REJECTED",
            run_id=projection.run_id,
            sequence=event.sequence,
            timestamp=event.timestamp,
            payload=ActionRejectedPayload(
                event=event,
                code=code,
                message=message,
                idempotency_key=action.idempotency_key,
                current_state_version=projection.state_version,
            ),
        )
