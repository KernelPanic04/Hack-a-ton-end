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

    async def _effort_for_scores(self, scores: list[int]) -> str:
        """Reasoning effort the orchestrator would request for these ratings."""

        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        feedback = [
            StoredFeedback(
                id=uuid.uuid4(), score=score, comment=None, created_at=datetime.now(timezone.utc)
            )
            for score in scores
        ]
        await generator.generate("crea dos botones", feedback=feedback)
        return captured["payload"]["reasoning"]["effort"]

    async def test_reasoning_effort_graduates_with_recent_average(self) -> None:
        # avg < 2 -> high, < 3 -> medium, < 4 -> low, >= 4 -> none.
        self.assertEqual(await self._effort_for_scores([1, 2]), "high")   # avg 1.5
        self.assertEqual(await self._effort_for_scores([2, 3]), "medium")  # avg 2.5
        self.assertEqual(await self._effort_for_scores([3, 4]), "low")     # avg 3.5
        self.assertEqual(await self._effort_for_scores([4, 5]), "none")    # avg 4.5

    async def test_reasoning_effort_boundaries_are_inclusive_at_the_lower_bucket(self) -> None:
        # An average exactly on a bound belongs to the calmer bucket above it.
        self.assertEqual(await self._effort_for_scores([1, 3]), "medium")  # avg 2.0, not high
        self.assertEqual(await self._effort_for_scores([2, 4]), "low")     # avg 3.0, not medium
        self.assertEqual(await self._effort_for_scores([3, 5]), "none")    # avg 4.0, not low

    async def test_worst_ratings_request_the_deepest_reasoning(self) -> None:
        self.assertEqual(await self._effort_for_scores([1, 1, 1]), "high")

    async def test_high_average_feedback_score_keeps_reasoning_effort_at_none(self) -> None:
        self.assertEqual(await self._effort_for_scores([4, 5]), "none")

    async def test_low_scored_comments_are_quoted_back_to_the_model(self) -> None:
        captured: dict = {}

        def request_response(payload, api_key, timeout):
            captured["payload"] = payload
            return response(VALID_LAYOUT)

        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, request_response=request_response
        )
        feedback = [
            StoredFeedback(
                id=uuid.uuid4(), score=1, comment="El botón de cancelar sobra.",
                created_at=datetime.now(timezone.utc),
            ),
            StoredFeedback(
                id=uuid.uuid4(), score=5, comment="Perfecto.",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        await generator.generate("crea dos botones", feedback=feedback)

        instructions = captured["payload"]["instructions"]
        self.assertIn("El botón de cancelar sobra.", instructions)
        # A high-scored comment is not quoted as a defect to fix.
        self.assertNotIn('"Perfecto."', instructions)

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

    async def test_orchestration_metadata_describes_the_decision(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )
        previous_layout = StudioPageNode.model_validate(VALID_LAYOUT["layout"])
        history = [AssistMessage(role="user", content="crea dos botones")]
        feedback = [
            StoredFeedback(id=uuid.uuid4(), score=1, comment=None, created_at=datetime.now(timezone.utc)),
            StoredFeedback(id=uuid.uuid4(), score=2, comment=None, created_at=datetime.now(timezone.utc)),
        ]

        spec = await generator.generate(
            "otra vez", history=history, previous_layout=previous_layout, feedback=feedback
        )

        assert spec.orchestration is not None
        self.assertEqual(spec.orchestration.reasoning_effort, "high")
        self.assertEqual(spec.orchestration.feedback_average, 1.5)
        self.assertEqual(spec.orchestration.feedback_count, 2)
        self.assertEqual(spec.orchestration.history_turns, 1)
        self.assertTrue(spec.orchestration.used_previous_layout)
        # And it reaches the wire under camelCase aliases.
        dumped = spec.model_dump(mode="json", by_alias=True)
        self.assertEqual(dumped["orchestration"]["reasoningEffort"], "high")
        self.assertEqual(dumped["orchestration"]["usedPreviousLayout"], True)

    async def test_fallback_spec_still_carries_orchestration(self) -> None:
        request_response = Mock(return_value={"output": []})  # always invalid
        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, retries=0, request_response=request_response
        )

        spec = await generator.generate("crea dos botones")

        self.assertEqual(spec.generated_by, "fallback")
        assert spec.orchestration is not None
        self.assertEqual(spec.orchestration.reasoning_effort, "none")
        self.assertEqual(spec.orchestration.feedback_count, 0)
        self.assertEqual(spec.orchestration.history_turns, 0)
        self.assertFalse(spec.orchestration.used_previous_layout)

    async def test_disabled_generator_still_reports_orchestration(self) -> None:
        generator = StudioUIGenerator(api_key="")
        spec = await generator.generate("crea dos botones")
        assert spec.orchestration is not None
        self.assertEqual(spec.orchestration.reasoning_effort, "none")


if __name__ == "__main__":
    unittest.main()
