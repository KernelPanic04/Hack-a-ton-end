from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID

from app.policy.engine import ActionPolicyEngine, PolicyViolation
from app.schemas.contracts import (
    ActionDefinition,
    ActionEvent,
    DecisionRequest,
    RunProjection,
    RunStepProjection,
)


RUN_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def projection() -> RunProjection:
    return RunProjection(
        run_id=f"run_{RUN_UUID}",
        workflow_id="wf_1",
        workflow_version=1,
        state_version=3,
        last_sequence=4,
        status="paused",
        current_step=RunStepProjection(
            id="step_1", type="generic.step", title="Review", status="attention"
        ),
        pending_decision=DecisionRequest(
            decision_id="dec_1", step_id="step_1", title="Review", prompt="Choose.", requested_at=NOW
        ),
        available_actions=[
            ActionDefinition(
                action_id="act_find_alternative", label="Find", risk="medium", requires_human=True
            )
        ],
    )


def action(*, state_version: int = 3, payload=None) -> ActionEvent:
    return ActionEvent(
        idempotency_key="idem_1",
        run_id=f"run_{RUN_UUID}",
        workflow_version=1,
        state_version=state_version,
        decision_id="dec_1",
        action_id="act_find_alternative",
        payload={} if payload is None else payload,
        timestamp=NOW,
    )


class PolicyEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.result = SimpleNamespace(scalars=lambda: [])
        self.session = SimpleNamespace(execute=AsyncMock(return_value=self.result))
        self.runtime = SimpleNamespace(get_projection=AsyncMock(return_value=projection()))

    async def test_allows_an_available_current_action(self) -> None:
        result = await ActionPolicyEngine(self.session, self.runtime).validate(action(), RUN_UUID)

        self.assertEqual(result.state_version, 3)

    async def test_rejects_stale_state_before_runtime_mutates(self) -> None:
        with self.assertRaises(PolicyViolation) as raised:
            await ActionPolicyEngine(self.session, self.runtime).validate(
                action(state_version=2), RUN_UUID
            )

        self.assertEqual(raised.exception.code, "STALE_STATE_VERSION")

    async def test_rejects_used_idempotency_key(self) -> None:
        self.result.scalars = lambda: [{"_idempotency_key": "idem_1"}]

        with self.assertRaises(PolicyViolation) as raised:
            await ActionPolicyEngine(self.session, self.runtime).validate(action(), RUN_UUID)

        self.assertEqual(raised.exception.code, "IDEMPOTENCY_REPLAY")

    async def test_rejects_payload_outside_the_declared_schema(self) -> None:
        with self.assertRaises(PolicyViolation) as raised:
            await ActionPolicyEngine(self.session, self.runtime).validate(
                action(payload={"unexpected": True}), RUN_UUID
            )

        self.assertEqual(raised.exception.code, "PAYLOAD_INVALID")


if __name__ == "__main__":
    unittest.main()
