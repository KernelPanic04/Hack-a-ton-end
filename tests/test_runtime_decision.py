from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from app.flow.models import FlowDefinition, StepDefinition
from app.runtime.run import RunEngine
from app.runtime.status import StoredRunStatus
from app.schemas.contracts import RunEventType


RUN_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


class RuntimeDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviewed_generic_step_is_recorded_as_completed(self) -> None:
        session = SimpleNamespace(add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
        engine = RunEngine(session)  # type: ignore[arg-type]
        run = SimpleNamespace(
            id=RUN_ID,
            status=StoredRunStatus.DECISION_REQUIRED.value,
            current_step_id="unseen_runtime_audit",
            state={
                "unseen_runtime_audit": {
                    "data": {"summary": "Checked the declared runtime value."},
                    "verdict": "attention",
                },
                "_pending_decision": {
                    "available_actions": ["act_acknowledge"],
                },
            },
            state_version=2,
        )
        flow = FlowDefinition(
            workflow_id="workflow",
            version=2,
            steps=[
                StepDefinition(
                    id="unseen_runtime_audit",
                    type="generic.runtime",
                    title="Unseen runtime audit",
                    objective="Inspect a prior value.",
                    inputs=["previous.data.value"],
                    requiresHumanReview=True,
                )
            ],
        )
        engine._get_run_or_raise = AsyncMock(return_value=run)  # type: ignore[method-assign]
        engine._flow_for_run = AsyncMock(return_value=flow)  # type: ignore[method-assign]
        engine._append_event = AsyncMock()  # type: ignore[method-assign]

        await engine.resolve_decision(
            RUN_ID,
            "act_acknowledge",
            {},
            state_version=2,
            idempotency_key="idem_phase4_review",
        )

        event_types = [call.args[1] for call in engine._append_event.await_args_list]
        self.assertEqual(
            event_types,
            [
                RunEventType.ACTION_ACCEPTED,
                RunEventType.RUN_RESUMED,
                RunEventType.STEP_COMPLETED,
                RunEventType.RUN_COMPLETED,
            ],
        )
        completed_payload = engine._append_event.await_args_list[2].args[2]
        self.assertEqual(completed_payload["step_id"], "unseen_runtime_audit")
        self.assertEqual(
            completed_payload["data"]["summary"],
            "Checked the declared runtime value.",
        )
        self.assertEqual(run.status, StoredRunStatus.COMPLETED.value)
        self.assertIsNone(run.current_step_id)


if __name__ == "__main__":
    unittest.main()
