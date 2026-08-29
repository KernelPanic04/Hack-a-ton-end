from datetime import datetime, timezone
from time import perf_counter
import unittest

from app.schemas.contracts import (
    ActionDefinition,
    DecisionRequest,
    RunProjection,
    RunStepProjection,
)
from app.synthesis import DeterministicComposer
from app.synthesis.composer import compose


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def projection(*, attention: bool = False, decision: bool = False) -> RunProjection:
    available_actions = []
    pending_decision = None
    if decision:
        available_actions = [
            ActionDefinition(
                action_id="act_review",
                label="Review",
                risk="medium",
                requires_human=True,
            )
        ]
        pending_decision = DecisionRequest(
            decision_id="dec_review",
            step_id="step_validate_data",
            title="Review required",
            prompt="Choose a permitted next action.",
            requested_at=NOW,
        )

    return RunProjection(
        run_id="run_example",
        workflow_id="wf_example",
        workflow_version=1,
        state_version=3,
        last_sequence=0,
        status="paused" if decision else "running",
        current_step=RunStepProjection(
            id="step_validate_data",
            type="validate_data",
            title="Validate data",
            objective="Assess the available values.",
            status="attention" if attention or decision else "active",
        ),
        operation={"result": {"value": 3, "verdict": "attention" if attention else "ok"}},
        pending_decision=pending_decision,
        available_actions=available_actions,
    )


class DeterministicComposerTests(unittest.TestCase):
    def test_object_api_is_exported_for_runtime_pipeline(self) -> None:
        spec = DeterministicComposer().compose(projection())
        self.assertEqual(spec.generated_by, "deterministic")

    def test_normal_projection_produces_a_valid_summary_layout(self) -> None:
        spec = compose(projection())
        self.assertEqual(spec.generated_by, "deterministic")
        self.assertEqual(spec.layout.children[0].id, "ui_summary_section")

    def test_attention_projection_uses_an_alert_first_layout(self) -> None:
        spec = compose(projection(attention=True))
        self.assertEqual(spec.layout.children[0].type, "alert")
        self.assertNotEqual(spec.layout.children[0].id, "ui_summary_section")

    def test_pending_decision_uses_a_decision_first_layout(self) -> None:
        spec = compose(projection(decision=True))
        self.assertEqual(spec.layout.children[0].id, "ui_decision_section")
        self.assertEqual(spec.allowed_actions[0].action_id, "act_review")

    def test_composition_is_under_fifty_milliseconds_per_run(self) -> None:
        sample = projection(decision=True)
        started = perf_counter()
        for _ in range(100):
            compose(sample)
        average_seconds = (perf_counter() - started) / 100
        self.assertLess(average_seconds, 0.05)


if __name__ == "__main__":
    unittest.main()
