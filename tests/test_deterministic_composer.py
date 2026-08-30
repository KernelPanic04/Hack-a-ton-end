from datetime import datetime, timezone
import unittest

from app.schemas.contracts import (
    ActionDefinition,
    DecisionRequest,
    RunEvent,
    RunProjection,
    RunStepProjection,
)
from app.synthesis import DeterministicComposer


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def make_projection(*, pending: bool = False, anomaly: bool = False) -> RunProjection:
    event = RunEvent(
        event_id="evt_1",
        run_id="run_1",
        workflow_id="wf_1",
        workflow_version=1,
        sequence=1,
        state_version=1,
        type="STEP_STARTED",
        step_id="step_1",
        timestamp=NOW,
    )
    actions = [
        ActionDefinition(
            action_id="act_continue",
            label="Continue",
            risk="low",
            requires_human=True,
        )
    ] if pending else []
    return RunProjection(
        run_id="run_1",
        workflow_id="wf_1",
        workflow_version=1,
        state_version=1,
        last_sequence=1,
        status="paused" if pending else "running",
        current_step=RunStepProjection(
            id="step_1",
            type="generic.step",
            title="Check input",
            status="attention" if pending or anomaly else "active",
        ),
        operation={"step_0": {"data": {"count": 3}, "verdict": "attention" if anomaly else "ok"}},
        recent_events=[event],
        pending_decision=(
            DecisionRequest(
                decision_id="dec_1", step_id="step_1", title="Review", prompt="Continue?", requested_at=NOW
            ) if pending else None
        ),
        available_actions=actions,
    )


class DeterministicComposerTests(unittest.TestCase):
    @staticmethod
    def _node_by_type(node, node_type: str):
        if node.type == node_type:
            return node
        for child in getattr(node, "children", []):
            found = DeterministicComposerTests._node_by_type(child, node_type)
            if found is not None:
                return found
        return None

    def test_standard_projection_produces_valid_generic_ui_spec(self) -> None:
        spec = DeterministicComposer().compose(make_projection(pending=False))

        self.assertEqual(spec.generated_by, "deterministic")
        self.assertFalse(any(node.type == "decisionPanel" for node in spec.layout.children))
        execution = next(node for node in spec.layout.children if node.id == "ui_execution")
        self.assertTrue(any(node.type == "timeline" for node in execution.children))

    def test_pending_decision_adds_attention_layout_and_allowed_action(self) -> None:
        spec = DeterministicComposer().compose(make_projection(pending=True))

        panel = self._node_by_type(spec.layout, "decisionPanel")
        self.assertIsNotNone(panel)
        self.assertEqual(panel.props.actions[0].action_id, "act_continue")
        self.assertIn("pending", spec.reason.lower())

    def test_anomaly_and_decision_have_structurally_distinct_layouts(self) -> None:
        normal = DeterministicComposer().compose(make_projection())
        anomaly = DeterministicComposer().compose(make_projection(anomaly=True))
        decision = DeterministicComposer().compose(make_projection(pending=True))

        def tree_types(spec):
            types = []

            def visit(node):
                types.append(node.type)
                for child in getattr(node, "children", []):
                    visit(child)

            visit(spec.layout)
            return types

        self.assertNotEqual(tree_types(normal), tree_types(anomaly))
        self.assertNotEqual(tree_types(normal), tree_types(decision))
        self.assertNotEqual(tree_types(anomaly), tree_types(decision))
        self.assertIn("anomaly", anomaly.reason.lower())

    def test_route_shaped_operation_data_adds_a_map_node(self) -> None:
        current = make_projection()
        current.operation["event"] = {"data": {"route": {
            "waypoints": [
                {"id": "origin", "label": "Origin", "lat": 10, "lon": 20, "kind": "origin"},
                {"id": "destination", "label": "Destination", "lat": 11, "lon": 21, "kind": "destination"},
            ],
            "segments": [{"fromId": "origin", "toId": "destination", "status": "active"}],
        }}}

        spec = DeterministicComposer().compose(current)
        route_map = self._node_by_type(spec.layout, "map")
        self.assertIsNotNone(route_map)
        self.assertEqual(route_map.props.segments[0].status, "active")

if __name__ == "__main__":
    unittest.main()
