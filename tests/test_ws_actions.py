from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID

from app.policy.engine import PolicyViolation
from app.policy.service import ActionCoordinator
from app.schemas.contracts import (
    ActionDefinition,
    ActionSubmittedEnvelope,
    DecisionRequest,
    RunEvent,
    RunProjection,
    RunStepProjection,
)


NOW = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)
RUN_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
RUN_ID = f"run_{RUN_UUID}"


def projection(*, state_version: int = 3, pending: bool = True) -> RunProjection:
    return RunProjection(
        run_id=RUN_ID,
        workflow_id="wf_logistics_main",
        workflow_version=1,
        state_version=state_version,
        last_sequence=4,
        status="paused" if pending else "running",
        current_step=RunStepProjection(
            id="step_transshipment_anomaly",
            type="generic.step",
            title="Review anomaly",
            status="attention" if pending else "active",
        ),
        operation={},
        pending_decision=(
            DecisionRequest(
                decision_id="dec_route_review",
                step_id="step_transshipment_anomaly",
                title="Review route",
                prompt="Continue?",
                requested_at=NOW,
            )
            if pending
            else None
        ),
        available_actions=(
            [
                ActionDefinition(
                    action_id="act_find_alternative",
                    label="Find alternative",
                    risk="medium",
                    requires_human=True,
                )
            ]
            if pending
            else []
        ),
    )


def submitted(*, state_version: int = 3) -> ActionSubmittedEnvelope:
    return ActionSubmittedEnvelope.model_validate(
        {
            "schemaVersion": "1",
            "type": "ACTION_SUBMITTED",
            "runId": RUN_ID,
            "sequence": 4,
            "timestamp": NOW,
            "payload": {
                "schemaVersion": "1",
                "idempotencyKey": "idem_action_1",
                "runId": RUN_ID,
                "workflowVersion": 1,
                "stateVersion": state_version,
                "decisionId": "dec_route_review",
                "actionId": "act_find_alternative",
                "payload": {},
                "timestamp": NOW,
            },
        }
    )


def event(event_type: str, sequence: int, state_version: int) -> RunEvent:
    return RunEvent(
        event_id=f"evt_{event_type.lower()}_{sequence}",
        run_id=RUN_ID,
        workflow_id="wf_logistics_main",
        workflow_version=1,
        sequence=sequence,
        state_version=state_version,
        type=event_type,
        timestamp=NOW,
    )


class ActionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_action_returns_action_accepted_envelope(self) -> None:
        engine = SimpleNamespace(
            get_projection=AsyncMock(
                side_effect=[projection(), projection(state_version=4, pending=False)]
            ),
            resolve_decision=AsyncMock(),
            latest_event=AsyncMock(return_value=event("ACTION_ACCEPTED", 5, 4)),
        )
        policy = SimpleNamespace(validate=AsyncMock(return_value=projection()))
        handler = ActionCoordinator(  # type: ignore[arg-type]
            session=None, engine=engine, policy=policy
        )

        result = await handler.handle(submitted().payload, RUN_UUID)

        self.assertEqual(result.type, "ACTION_ACCEPTED")
        self.assertEqual(result.payload.idempotency_key, "idem_action_1")
        engine.resolve_decision.assert_awaited_once_with(
            RUN_UUID,
            "act_find_alternative",
            {},
            3,
            idempotency_key="idem_action_1",
        )

    async def test_stale_action_is_logged_and_returned_as_rejected(self) -> None:
        engine = SimpleNamespace(
            get_projection=AsyncMock(return_value=projection(state_version=3)),
            record_action_rejection=AsyncMock(
                return_value=event("ACTION_REJECTED", 5, 3)
            ),
            resolve_decision=AsyncMock(),
        )
        policy = SimpleNamespace(
            validate=AsyncMock(
                side_effect=PolicyViolation(
                    "STALE_STATE_VERSION", "El estado cambió; actualiza la interfaz."
                )
            )
        )
        handler = ActionCoordinator(  # type: ignore[arg-type]
            session=None, engine=engine, policy=policy
        )

        result = await handler.handle(submitted(state_version=2).payload, RUN_UUID)

        self.assertEqual(result.type, "ACTION_REJECTED")
        self.assertEqual(result.payload.code, "STALE_STATE_VERSION")
        self.assertEqual(result.payload.current_state_version, 3)
        engine.record_action_rejection.assert_awaited_once_with(
            RUN_UUID,
            "act_find_alternative",
            "STALE_STATE_VERSION",
        )
        engine.resolve_decision.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
