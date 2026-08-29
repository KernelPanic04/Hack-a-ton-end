from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.runtime.pipeline import RuntimePipeline
from app.schemas.contracts import RunEvent, RunProjection
from app.synthesis import DeterministicComposer


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
RUN_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")


def projection(state_version: int = 2) -> RunProjection:
    return RunProjection(
        run_id=f"run_{RUN_UUID}",
        workflow_id="wf_progressive_ui",
        workflow_version=1,
        state_version=state_version,
        last_sequence=2,
        status="running",
        operation={"input": {"value": 4, "verdict": "ok"}},
        recent_events=[],
        available_actions=[],
    )


def ui_event() -> RunEvent:
    return RunEvent(
        event_id="evt_llm_ui_3",
        run_id=f"run_{RUN_UUID}",
        workflow_id="wf_progressive_ui",
        workflow_version=1,
        sequence=3,
        state_version=2,
        type="UI_UPDATED",
        timestamp=NOW,
    )


class SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class RuntimePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_llm_upgrade_when_baseline_is_still_current(self) -> None:
        current = projection()
        baseline = DeterministicComposer().compose(current)
        upgraded = baseline.model_copy(
            update={"generated_by": "llm", "reason": "Improved hierarchy."}
        )
        llm = SimpleNamespace(
            enabled=True,
            compose_upgrade=AsyncMock(return_value=upgraded),
        )
        hub = SimpleNamespace(publish=AsyncMock())
        pipeline = RuntimePipeline(  # type: ignore[arg-type]
            session=None, hub=hub, llm_composer=llm
        )
        engine = SimpleNamespace(
            get_projection=AsyncMock(side_effect=[current, current]),
            save_ui_spec=AsyncMock(return_value=ui_event()),
        )

        with patch("app.runtime.pipeline.AsyncSessionLocal", return_value=SessionContext()), patch(
            "app.runtime.pipeline.RunEngine", return_value=engine
        ):
            await pipeline._publish_llm_upgrade(RUN_UUID, current, baseline)

        engine.save_ui_spec.assert_awaited_once_with(RUN_UUID, upgraded)
        published = hub.publish.await_args.args[0]
        self.assertEqual(published.payload.ui_spec.generated_by, "llm")
        self.assertEqual(published.sequence, 3)

    async def test_drops_upgrade_when_a_newer_state_already_exists(self) -> None:
        original = projection()
        newer = projection(state_version=3)
        baseline = DeterministicComposer().compose(original)
        upgraded = baseline.model_copy(update={"generated_by": "llm"})
        llm = SimpleNamespace(
            enabled=True,
            compose_upgrade=AsyncMock(return_value=upgraded),
        )
        hub = SimpleNamespace(publish=AsyncMock())
        pipeline = RuntimePipeline(  # type: ignore[arg-type]
            session=None, hub=hub, llm_composer=llm
        )
        engine = SimpleNamespace(
            get_projection=AsyncMock(return_value=newer),
            save_ui_spec=AsyncMock(),
        )

        with patch("app.runtime.pipeline.AsyncSessionLocal", return_value=SessionContext()), patch(
            "app.runtime.pipeline.RunEngine", return_value=engine
        ):
            await pipeline._publish_llm_upgrade(RUN_UUID, original, baseline)

        engine.save_ui_spec.assert_not_awaited()
        hub.publish.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
