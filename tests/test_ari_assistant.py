import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.schemas.contracts import AssistRequest, DecisionRequest, RunProjection, RunStepProjection
from app.synthesis.assistant import AriAssistant


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def projection() -> RunProjection:
    return RunProjection(
        run_id="run_assist_test", workflow_id="wf_assist_test", workflow_version=1,
        state_version=2, last_sequence=2, status="paused", recent_events=[],
        current_step=RunStepProjection(id="step_review", type="generic.review", title="Review", status="active"),
        pending_decision=DecisionRequest(decision_id="dec_assist_test", step_id="step_review", title="Review", prompt="Choose.", requested_at=NOW),
        available_actions=[{"actionId": "act_find_alternative", "label": "Find alternative", "risk": "medium", "requiresHuman": True}],
    )


class AriAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def _respond(self, assistant: AriAssistant, message: str):
        async def immediate(function, *args):
            return function(*args)

        with patch("app.synthesis.assistant.asyncio.to_thread", new=immediate):
            return await assistant.respond(projection(), [], AssistRequest(message=message))

    async def test_accepts_only_available_recommendations(self) -> None:
        def provider(payload, key, timeout):
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            context = json.loads(payload["input"])
            self.assertEqual(context["availableActionIds"], ["act_find_alternative"])
            self.assertEqual(context["projection"]["status"], "paused")
            result = {"reply": "I recommend finding an alternative.", "recommendedActions": [{"actionId": "act_find_alternative", "rationale": "It may reduce the delay."}], "proposedStep": None}
            return {"output": [{"content": [{"type": "output_text", "text": json.dumps(result)}]}]}

        result = await self._respond(
            AriAssistant(api_key="test-key", enabled=True, request_response=provider),
            "What should we do?",
        )
        self.assertEqual(result.recommended_actions[0].action_id, "act_find_alternative")

    async def test_invalid_recommendation_falls_back_without_actions(self) -> None:
        def provider(*_):
            result = {"reply": "Do it.", "recommendedActions": [{"actionId": "act_not_allowed", "rationale": "No."}], "proposedStep": None}
            return {"output": [{"content": [{"type": "output_text", "text": json.dumps(result)}]}]}

        result = await self._respond(
            AriAssistant(api_key="test-key", enabled=True, retries=0, request_response=provider),
            "What should we do?",
        )
        self.assertEqual(result.recommended_actions, [])

    async def test_disabled_assistant_returns_deterministic_reply(self) -> None:
        assistant = AriAssistant(api_key="test-key", enabled=False)
        result = await self._respond(assistant, "Status?")
        self.assertEqual(result.recommended_actions, [])
        self.assertIn("waiting", result.reply)
