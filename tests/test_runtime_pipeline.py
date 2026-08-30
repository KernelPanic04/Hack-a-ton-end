import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock
import unittest
from uuid import UUID

from app.runtime.pipeline import RuntimePipeline
from app.schemas.contracts import RunEvent, RunProjection, UISpec
from app.synthesis import LLMComposer


RUN_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "demo"
    / "fixtures"
    / "run_projection_pending_decision.json"
)


def fixture_projection() -> RunProjection:
    return RunProjection.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))


class RuntimePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_transition_projection_composition_and_websocket_delivery(self) -> None:
        before_transition = fixture_projection()
        after_transition = before_transition.model_copy(update={"last_sequence": 3})
        ui_event = RunEvent(
            event_id="evt_ui_updated",
            run_id=before_transition.run_id,
            workflow_id=before_transition.workflow_id,
            workflow_version=before_transition.workflow_version,
            sequence=3,
            state_version=before_transition.state_version,
            type="UI_UPDATED",
            timestamp=datetime(2026, 8, 29, 12, 2, tzinfo=timezone.utc),
        )
        hub = type("Hub", (), {"publish": AsyncMock()})()
        pipeline = RuntimePipeline(session=None, hub=hub)  # type: ignore[arg-type]
        pipeline.engine.get_projection = AsyncMock(
            side_effect=[before_transition, after_transition]
        )
        pipeline.engine.save_ui_spec = AsyncMock(return_value=ui_event)

        envelope = await pipeline.publish_current(RUN_UUID)

        self.assertEqual(envelope.type, "UI_UPDATED")
        self.assertEqual(envelope.run_id, before_transition.run_id)
        self.assertEqual(envelope.sequence, 3)
        self.assertEqual(envelope.payload.projection.last_sequence, 3)
        self.assertEqual(envelope.payload.ui_spec.generated_by, "deterministic")
        self.assertEqual(envelope.payload.ui_spec.state_version, before_transition.state_version)
        UISpec.model_validate(envelope.payload.ui_spec.model_dump(mode="json"))
        pipeline.engine.save_ui_spec.assert_awaited_once_with(
            RUN_UUID, envelope.payload.ui_spec
        )
        hub.publish.assert_awaited_once_with(envelope)

    async def test_llm_enabled_publishes_blank_placeholder_not_a_deterministic_guess(
        self,
    ) -> None:
        before_transition = fixture_projection()
        after_transition = before_transition.model_copy(update={"last_sequence": 3})
        ui_event = RunEvent(
            event_id="evt_ui_updated",
            run_id=before_transition.run_id,
            workflow_id=before_transition.workflow_id,
            workflow_version=before_transition.workflow_version,
            sequence=3,
            state_version=before_transition.state_version,
            type="UI_UPDATED",
            timestamp=datetime(2026, 8, 29, 12, 2, tzinfo=timezone.utc),
        )
        hub = type("Hub", (), {"publish": AsyncMock()})()
        llm_composer = LLMComposer(api_key="test-key", enabled=True)
        llm_composer.compose_upgrade = AsyncMock(return_value=None)
        pipeline = RuntimePipeline(session=None, hub=hub, llm_composer=llm_composer)  # type: ignore[arg-type]
        pipeline.engine.get_projection = AsyncMock(
            side_effect=[before_transition, after_transition]
        )
        pipeline.engine.save_ui_spec = AsyncMock(return_value=ui_event)

        envelope = await pipeline.publish_current(RUN_UUID)
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done()
        ]
        await asyncio.gather(*pending)

        self.assertEqual(envelope.payload.ui_spec.generated_by, "fallback")
        llm_composer.compose_upgrade.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
