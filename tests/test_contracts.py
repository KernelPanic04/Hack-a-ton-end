from datetime import datetime, timezone
import unittest

from pydantic import TypeAdapter, ValidationError

from app.schemas.contracts import (
    ActionDefinition,
    ActionEvent,
    COMPONENT_TYPES,
    DecisionAction,
    DecisionPanelNode,
    DecisionPanelProps,
    DecisionRequest,
    PageNode,
    PageProps,
    RunProjection,
    SectionNode,
    SectionProps,
    SERVER_MESSAGE_TYPES,
    UISpec,
    UIUpdatedEnvelope,
    UIUpdatedPayload,
    WebSocketEnvelope,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def action() -> ActionDefinition:
    return ActionDefinition(
        actionId="act_find_alternative",
        label="Find alternative",
        risk="medium",
        requiresHuman=True,
    )


def projection() -> RunProjection:
    return RunProjection(
        runId="run_550e8400-e29b-41d4-a716-446655440000",
        workflowId="wf_logistics_main",
        workflowVersion=1,
        stateVersion=3,
        lastSequence=4,
        status="paused",
        operation={"etaDelayDays": 9},
        pendingDecision=DecisionRequest(
            decisionId="dec_550e8400-e29b-41d4-a716-446655440000",
            stepId="step_track_vessel",
            title="Unexpected transshipment",
            prompt="Find an alternative route?",
            requestedAt=NOW,
        ),
        availableActions=[action()],
    )


def ui_spec() -> UISpec:
    return UISpec(
        runId="run_550e8400-e29b-41d4-a716-446655440000",
        workflowId="wf_logistics_main",
        workflowVersion=1,
        stateVersion=3,
        generatedBy="deterministic",
        reason="A pending decision makes the human action primary.",
        layout=PageNode(
            id="ui_run",
            type="page",
            props=PageProps(title="Run"),
            children=[
                SectionNode(
                    id="ui_decision_section",
                    type="section",
                    props=SectionProps(title="Decision", emphasis="warning"),
                    children=[
                        DecisionPanelNode(
                            id="ui_decision",
                            type="decisionPanel",
                            props=DecisionPanelProps(
                                decisionId="dec_550e8400-e29b-41d4-a716-446655440000",
                                title="Choose the next action",
                                actions=[
                                    DecisionAction(
                                        actionId="act_find_alternative",
                                        label="Find alternative",
                                        style="primary",
                                    )
                                ],
                            ),
                        )
                    ],
                )
            ],
        ),
        allowedActions=[action()],
    )


class ContractTests(unittest.TestCase):
    def test_registry_and_server_message_counts_are_frozen(self) -> None:
        self.assertEqual(len(COMPONENT_TYPES), 10)
        self.assertEqual(len(SERVER_MESSAGE_TYPES), 12)

    def test_wire_dump_uses_camel_case(self) -> None:
        dumped = projection().model_dump(mode="json")
        self.assertEqual(dumped["schemaVersion"], "1")
        self.assertEqual(dumped["stateVersion"], 3)
        self.assertNotIn("state_version", dumped)

    def test_action_event_rejects_client_event_id(self) -> None:
        with self.assertRaises(ValidationError):
            ActionEvent.model_validate(
                {
                    "schemaVersion": "1",
                    "eventId": "evt_550e8400-e29b-41d4-a716-446655440000",
                    "idempotencyKey": "idem_550e8400-e29b-41d4-a716-446655440000",
                    "runId": "run_550e8400-e29b-41d4-a716-446655440000",
                    "workflowVersion": 1,
                    "stateVersion": 3,
                    "decisionId": "dec_550e8400-e29b-41d4-a716-446655440000",
                    "actionId": "act_find_alternative",
                    "payload": {},
                    "timestamp": NOW.isoformat(),
                }
            )

    def test_pending_decision_requires_available_action(self) -> None:
        data = projection().model_dump(mode="json")
        data["availableActions"] = []
        with self.assertRaises(ValidationError):
            RunProjection.model_validate(data)

    def test_decision_panel_must_reference_allowed_action(self) -> None:
        spec = ui_spec().model_dump(mode="json")
        spec["allowedActions"] = []
        with self.assertRaises(ValidationError):
            UISpec.model_validate(spec)

    def test_layout_rejects_duplicate_node_ids(self) -> None:
        spec = ui_spec().model_dump(mode="json")
        spec["layout"]["children"][0]["id"] = "ui_run"
        with self.assertRaises(ValidationError):
            UISpec.model_validate(spec)

    def test_ui_updated_envelope_matches_projection_and_spec(self) -> None:
        run_projection = projection()
        spec = ui_spec()
        event = {
            "schemaVersion": "1",
            "eventId": "evt_550e8400-e29b-41d4-a716-446655440000",
            "runId": run_projection.run_id,
            "workflowId": run_projection.workflow_id,
            "workflowVersion": 1,
            "sequence": 5,
            "stateVersion": 3,
            "type": "UI_UPDATED",
            "payload": {},
            "timestamp": NOW,
        }
        envelope = UIUpdatedEnvelope(
            type="UI_UPDATED",
            runId=run_projection.run_id,
            sequence=5,
            timestamp=NOW,
            payload=UIUpdatedPayload(
                event=event, projection=run_projection, uiSpec=spec
            ),
        )
        parsed = TypeAdapter(WebSocketEnvelope).validate_python(
            envelope.model_dump(mode="json")
        )
        self.assertIsInstance(parsed, UIUpdatedEnvelope)


if __name__ == "__main__":
    unittest.main()
