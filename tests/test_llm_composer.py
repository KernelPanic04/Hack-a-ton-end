from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from app.schemas.contracts import RunProjection
from app.synthesis import DeterministicComposer, LLMComposer


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def projection() -> RunProjection:
    return RunProjection(
        run_id="run_llm_test",
        workflow_id="wf_llm_test",
        workflow_version=1,
        state_version=2,
        last_sequence=2,
        status="running",
        operation={"input": {"value": 4, "verdict": "ok"}},
        recent_events=[],
        available_actions=[],
    )


class LLMComposerTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_then_returns_validated_upgrade(self) -> None:
        current = projection()
        baseline = DeterministicComposer().compose(current)
        calls = 0

        def request_response(payload, api_key, timeout):
            nonlocal calls
            calls += 1
            self.assertEqual(api_key, "test-key")
            self.assertEqual(timeout, 5.0)
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            if calls == 1:
                return {"output": []}
            text = {
                "reason": "The upgraded hierarchy foregrounds the current status.",
                "layout": baseline.layout.model_dump(mode="json", by_alias=True),
            }
            return {
                "output": [
                    {"content": [{"type": "output_text", "text": __import__("json").dumps(text)}]}
                ]
            }

        composer = LLMComposer(
            api_key="test-key", enabled=True, request_response=request_response
        )
        upgraded = await composer.compose_upgrade(current, baseline)

        self.assertEqual(calls, 2)
        self.assertIsNotNone(upgraded)
        self.assertEqual(upgraded.generated_by, "llm")
        self.assertEqual(upgraded.state_version, baseline.state_version)
        self.assertEqual(upgraded.allowed_actions, baseline.allowed_actions)

    async def test_missing_api_key_keeps_deterministic_baseline(self) -> None:
        current = projection()
        baseline = DeterministicComposer().compose(current)
        composer = LLMComposer(api_key="")

        self.assertFalse(composer.enabled)
        self.assertIsNone(await composer.compose_upgrade(current, baseline))

    async def test_kill_switch_keeps_deterministic_baseline_with_api_key(self) -> None:
        current = projection()
        baseline = DeterministicComposer().compose(current)
        request_response = Mock()
        composer = LLMComposer(
            api_key="configured-key",
            enabled=False,
            request_response=request_response,
        )

        self.assertFalse(composer.enabled)
        self.assertIsNone(await composer.compose_upgrade(current, baseline))
        request_response.assert_not_called()

    async def test_llm_cannot_remove_or_change_a_trusted_map(self) -> None:
        current = projection()
        current.operation["route"] = {
            "waypoints": [
                {"id": "a", "label": "A", "lat": 1, "lon": 2, "kind": "origin"},
                {"id": "b", "label": "B", "lat": 3, "lon": 4, "kind": "destination"},
            ],
            "segments": [{"from": "a", "to": "b", "status": "planned"}],
        }
        baseline = DeterministicComposer().compose(current)
        layout = baseline.layout.model_dump(mode="json", by_alias=True)

        def remove_maps(node):
            children = node.get("children", [])
            node["children"] = [child for child in children if child["type"] != "map"]
            for child in node["children"]:
                remove_maps(child)

        remove_maps(layout)

        def request_response(*_args):
            return {"output": [{"content": [{"type": "output_text", "text": __import__("json").dumps({
                "reason": "Attempted simplification.", "layout": layout
            })}]}]}

        composer = LLMComposer(api_key="test-key", enabled=True, request_response=request_response)
        self.assertIsNone(await composer.compose_upgrade(current, baseline))


if __name__ == "__main__":
    unittest.main()
