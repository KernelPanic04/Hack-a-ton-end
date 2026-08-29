from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID

from app.runtime.run import RunEngine
from app.runtime.status import StoredRunStatus


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
RUN_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
WORKFLOW_UUID = UUID("550e8400-e29b-41d4-a716-446655440001")
VERSION_UUID = UUID("550e8400-e29b-41d4-a716-446655440002")
EVENT_UUID = UUID("550e8400-e29b-41d4-a716-446655440003")


class RuntimeProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_runtime_is_adapted_to_the_frozen_wire_contract(self) -> None:
        engine = RunEngine(session=None)  # type: ignore[arg-type]
        run = SimpleNamespace(
            id=RUN_UUID,
            workflow_id=WORKFLOW_UUID,
            workflow_version_id=VERSION_UUID,
            status=StoredRunStatus.DECISION_REQUIRED.value,
            current_step_id="transshipment_anomaly",
            state={
                "booking_received": {"verdict": "ok"},
                "_pending_decision": {
                    "decision_id": "dec_route_choice",
                    "step_id": "step_transshipment_anomaly",
                    "title": "Human decision required",
                    "prompt": "Find an alternative route?",
                    "context": {"delayDays": 9},
                    "requested_at": NOW.isoformat(),
                    "available_actions": ["act_find_alternative"],
                },
            },
            state_version=3,
            updated_at=NOW,
        )
        version = SimpleNamespace(
            id=VERSION_UUID,
            workflow_id=WORKFLOW_UUID,
            version=1,
            steps=[
                {
                    "id": "transshipment_anomaly",
                    "type": "transshipment_anomaly",
                    "title": "Unexpected transshipment",
                    "objective": "Choose how to recover the route.",
                    "inputs": ["delay_days"],
                    "requires_human_review": True,
                }
            ],
        )
        event = SimpleNamespace(
            id=EVENT_UUID,
            run_id=RUN_UUID,
            type="DECISION_REQUIRED",
            payload={"step_id": "transshipment_anomaly"},
            state_version=3,
            created_at=NOW,
        )

        engine._get_run_or_raise = AsyncMock(return_value=run)  # type: ignore[method-assign]
        engine.flow_engine.get_version_by_id = AsyncMock(return_value=version)
        engine.export_events = AsyncMock(return_value=[event])  # type: ignore[method-assign]

        projection = await engine.get_projection(RUN_UUID)
        wire = projection.model_dump(mode="json")

        self.assertEqual(wire["runId"], f"run_{RUN_UUID}")
        self.assertEqual(wire["workflowId"], f"wf_{WORKFLOW_UUID}")
        self.assertEqual(wire["status"], "paused")
        self.assertEqual(wire["lastSequence"], 1)
        self.assertEqual(wire["currentStep"]["id"], "step_transshipment_anomaly")
        self.assertEqual(
            wire["pendingDecision"]["decisionId"], "dec_route_choice"
        )
        self.assertEqual(
            wire["availableActions"][0]["actionId"], "act_find_alternative"
        )
        self.assertEqual(wire["recentEvents"][0]["eventId"], f"evt_{EVENT_UUID}")
        self.assertNotIn("_pending_decision", wire["operation"])


if __name__ == "__main__":
    unittest.main()
