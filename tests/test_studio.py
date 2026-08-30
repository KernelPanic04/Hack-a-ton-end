import json
import unittest
from unittest.mock import Mock

from datetime import datetime, timezone
import uuid

from app.schemas.contracts import AssistMessage
from app.studio.llm import StudioUIGenerator
from app.studio.schema import StudioPageNode, StudioUISpec
from app.studio.store import StoredFeedback


def response(payload: dict) -> dict:
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


VALID_LAYOUT = {
    "reason": "Dos botones lado a lado.",
    "layout": {
        "id": "ui_page",
        "type": "page",
        "props": {"title": "Botones"},
        "children": [
            {
                "id": "ui_row",
                "type": "section",
                "props": {
                    "direction": "row",
                    "gap": "md",
                    "align": "center",
                    "justify": "start",
                    "columns": 1,
                    "emphasis": "normal",
                },
                "children": [
                    {
                        "id": "ui_btn_1",
                        "type": "button",
                        "props": {"label": "Guardar", "variant": "primary", "size": "md"},
                    },
                    {
                        "id": "ui_btn_2",
                        "type": "button",
                        "props": {"label": "Cancelar", "variant": "secondary", "size": "md"},
                    },
                ],
            }
        ],
    },
}


class StudioUIGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_a_row_layout_with_two_buttons(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )

        spec = await generator.generate("crea dos botones, uno al lado del otro")

        self.assertEqual(spec.generated_by, "llm")
        section = spec.layout.children[0]
        self.assertEqual(section.type, "section")
        self.assertEqual(section.props.direction, "row")
        self.assertEqual([child.type for child in section.children], ["button", "button"])
        StudioUISpec.model_validate(spec.model_dump(mode="json"))

    async def test_suggestion_from_the_model_reaches_the_spec(self) -> None:
        payload = {**VALID_LAYOUT, "suggestion": "Suele leerse mejor si van en horizontal."}
        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=lambda *_args: response(payload)
        )

        spec = await generator.generate("crea dos botones")

        self.assertEqual(spec.suggestion, "Suele leerse mejor si van en horizontal.")

    async def test_missing_suggestion_from_the_model_is_none(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )

        spec = await generator.generate("crea dos botones")

        self.assertIsNone(spec.suggestion)

    async def test_disabled_returns_blank_fallback(self) -> None:
        generator = StudioUIGenerator(api_key="")

        self.assertFalse(generator.enabled)
        spec = await generator.generate("crea dos botones")

        self.assertEqual(spec.generated_by, "fallback")
        self.assertIn("deshabilitada", spec.reason)

    async def test_exhausted_retries_return_blank_fallback_with_real_error(self) -> None:
        request_response = Mock(return_value={"output": []})  # always invalid
        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, retries=2, request_response=request_response
        )

        spec = await generator.generate("crea dos botones")

        self.assertEqual(request_response.call_count, 3)
        self.assertEqual(spec.generated_by, "fallback")
        self.assertIn("3 intentos", spec.reason)
        self.assertIn("no output_text content", spec.reason)

    async def test_history_and_previous_layout_reach_the_provider_payload(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        previous_layout = StudioPageNode.model_validate(VALID_LAYOUT["layout"])
        history = [
            AssistMessage(role="user", content="crea dos botones"),
            AssistMessage(role="assistant", content="Listo, dos botones lado a lado."),
        ]

        await generator.generate(
            "ahora ponlos verticales",
            history=history,
            previous_layout=previous_layout,
        )

        sent_input = json.loads(captured["payload"]["input"])
        self.assertEqual(sent_input["prompt"], "ahora ponlos verticales")
        self.assertEqual(len(sent_input["history"]), 2)
        self.assertEqual(sent_input["history"][0]["content"], "crea dos botones")
        self.assertEqual(sent_input["previousLayout"]["id"], "ui_page")

    async def test_no_history_or_previous_layout_is_optional(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )

        await generator.generate("crea dos botones")

        sent_input = json.loads(captured["payload"]["input"])
        self.assertEqual(sent_input["history"], [])
        self.assertNotIn("previousLayout", sent_input)

    async def test_feedback_history_reaches_the_provider_payload(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        feedback = [
            StoredFeedback(
                id=uuid.uuid4(), score=2, comment="Muy cargado.", created_at=datetime.now(timezone.utc)
            ),
            StoredFeedback(id=uuid.uuid4(), score=5, comment=None, created_at=datetime.now(timezone.utc)),
        ]

        await generator.generate("ahora ponlos verticales", feedback=feedback)

        sent_input = json.loads(captured["payload"]["input"])
        self.assertEqual(sent_input["feedbackHistory"], [
            {"score": 2, "comment": "Muy cargado."},
            {"score": 5, "comment": None},
        ])

    async def test_no_feedback_omits_feedback_history_from_the_payload(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )

        await generator.generate("crea dos botones")

        sent_input = json.loads(captured["payload"]["input"])
        self.assertNotIn("feedbackHistory", sent_input)

    async def test_low_average_feedback_score_escalates_reasoning_effort(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        low_feedback = [
            StoredFeedback(id=uuid.uuid4(), score=1, comment=None, created_at=datetime.now(timezone.utc)),
            StoredFeedback(id=uuid.uuid4(), score=2, comment=None, created_at=datetime.now(timezone.utc)),
        ]

        await generator.generate("crea dos botones", feedback=low_feedback)

        self.assertEqual(captured["payload"]["reasoning"]["effort"], "low")

    async def test_high_average_feedback_score_keeps_reasoning_effort_at_none(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        high_feedback = [
            StoredFeedback(id=uuid.uuid4(), score=4, comment=None, created_at=datetime.now(timezone.utc)),
            StoredFeedback(id=uuid.uuid4(), score=5, comment=None, created_at=datetime.now(timezone.utc)),
        ]

        await generator.generate("crea dos botones", feedback=high_feedback)

        self.assertEqual(captured["payload"]["reasoning"]["effort"], "none")

    async def test_no_run_or_workflow_metadata_is_required(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )

        spec = await generator.generate("crea dos botones")

        dumped = spec.model_dump(mode="json", by_alias=True)
        for field in ("runId", "workflowId", "workflowVersion", "stateVersion", "allowedActions"):
            self.assertNotIn(field, dumped)


if __name__ == "__main__":
    unittest.main()
