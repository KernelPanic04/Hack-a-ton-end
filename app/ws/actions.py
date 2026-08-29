"""ActionEvent processing for the Phase 1 WebSocket round trip."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.run import RunEngine
from app.schemas.contracts import (
    ActionAcceptedEnvelope,
    ActionAcceptedPayload,
    ActionRejectedEnvelope,
    ActionRejectedPayload,
    ActionSubmittedEnvelope,
    RunEvent,
    RunEventType,
    ServerEnvelope,
)


class RuntimeActionHandler:
    """Validate a submitted action against the visible run projection.

    Full declarative policy and persisted idempotency belong to Phase 3. This
    handler closes Gate G1 while already enforcing run, workflow/state version,
    pending decision, allowed action and object-payload consistency.
    """

    def __init__(
        self,
        session: AsyncSession,
        engine: RunEngine | None = None,
    ) -> None:
        self.engine = engine or RunEngine(session)

    async def process(
        self,
        run_id: uuid.UUID,
        envelope: ActionSubmittedEnvelope,
    ) -> ServerEnvelope:
        action = envelope.payload
        projection = await self.engine.get_projection(run_id)

        if action.workflow_version != projection.workflow_version:
            return await self._reject(
                run_id,
                envelope,
                "workflow_version_mismatch",
                "workflowVersion no coincide con el run visible.",
            )
        if action.state_version != projection.state_version:
            return await self._reject(
                run_id,
                envelope,
                "stale_state_version",
                "stateVersion desactualizado: la decisión se rechaza.",
            )
        if (
            projection.pending_decision is None
            or action.decision_id != projection.pending_decision.decision_id
        ):
            return await self._reject(
                run_id,
                envelope,
                "decision_not_pending",
                "La decisión indicada ya no está pendiente.",
            )
        allowed_action_ids = {
            definition.action_id for definition in projection.available_actions
        }
        if action.action_id not in allowed_action_ids:
            return await self._reject(
                run_id,
                envelope,
                "action_not_available",
                "La acción no está disponible para esta decisión.",
            )
        if not isinstance(action.payload, dict):
            return await self._reject(
                run_id,
                envelope,
                "invalid_payload",
                "El payload de Phase 1 debe ser un objeto JSON.",
            )

        await self.engine.resolve_decision(
            run_id,
            action.action_id,
            action.payload,
            action.state_version,
        )
        accepted_event = await self.engine.latest_event(run_id, RunEventType.ACTION_ACCEPTED)
        if accepted_event is None:
            raise RuntimeError("resolve_decision did not append ACTION_ACCEPTED")
        projection = await self.engine.get_projection(run_id)
        return ActionAcceptedEnvelope(
            type="ACTION_ACCEPTED",
            run_id=projection.run_id,
            sequence=accepted_event.sequence,
            timestamp=accepted_event.timestamp,
            payload=ActionAcceptedPayload(
                event=accepted_event,
                projection=projection,
                idempotency_key=action.idempotency_key,
                decision_id=action.decision_id,
                action_id=action.action_id,
            ),
        )

    async def _reject(
        self,
        run_id: uuid.UUID,
        envelope: ActionSubmittedEnvelope,
        code: str,
        message: str,
    ) -> ActionRejectedEnvelope:
        action = envelope.payload
        event: RunEvent = await self.engine.record_action_rejection(
            run_id,
            action.action_id,
            code,
        )
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
