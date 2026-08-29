import json
import unittest

from app.schemas.contracts import CompareProps, RunProjection
from app.synthesis import DeterministicComposer
from app.synthesis.generic_step import (
    GenericStepLLMExecutor,
    GenericStepLLMResult,
    result_nodes,
)


def response(payload: dict) -> dict:
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


class GenericStepLLMExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_and_returns_validated_result(self) -> None:
        calls = 0

        def request_response(payload, api_key, timeout):
            nonlocal calls
            calls += 1
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            self.assertEqual(timeout, 5.0)
            if calls == 1:
                return {"output": []}
            return response(
                {
                    "findings": ["The resolved value is within the supplied range."],
                    "comparison": None,
                    "verdict": "pass",
                    "summary": "Input check completed.",
                }
            )

        executor = GenericStepLLMExecutor(
            api_key="test-key", enabled=True, request_response=request_response
        )
        result = await executor.analyze(
            objective="Check supplied values.",
            resolved_inputs={"input_1": {"source": "prior.score", "value": 7}},
            missing_inputs=[],
        )

        self.assertEqual(calls, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, "pass")

    async def test_returns_none_when_unconfigured(self) -> None:
        executor = GenericStepLLMExecutor(api_key="")

        self.assertFalse(executor.enabled)
        self.assertIsNone(
            await executor.analyze(
                objective="Check supplied values.", resolved_inputs={}, missing_inputs=[]
            )
        )

    def test_comparison_becomes_compare_node_not_key_value(self) -> None:
        result = GenericStepLLMResult(
            findings=["The second value improved."],
            comparison=CompareProps(
                title="Resolved values",
                left_label="Before",
                right_label="After",
                rows=[
                    {
                        "key": "score",
                        "label": "Score",
                        "before": 4,
                        "after": 7,
                        "outcome": "improved",
                    }
                ],
            ),
            verdict="pass",
            summary="Comparison completed.",
        )

        nodes = result_nodes("step_check", "Check", "Check values.", result)

        self.assertEqual([node.type for node in nodes], ["step", "compare"])
        self.assertEqual(nodes[1].props.rows[0].outcome, "improved")

    def test_no_comparison_does_not_add_compare_node(self) -> None:
        result = GenericStepLLMResult(
            findings=["One value was resolved."],
            verdict="unknown",
            summary="Partial input result.",
        )

        self.assertEqual(
            [node.type for node in result_nodes("step_check", "Check", "Check values.", result)],
            ["step"],
        )

    def test_composer_renders_persisted_comparison_as_compare(self) -> None:
        spec = DeterministicComposer().compose(
            RunProjection(
                run_id="run_generic_llm",
                workflow_id="wf_generic_llm",
                workflow_version=1,
                state_version=1,
                last_sequence=1,
                status="running",
                operation={
                    "step_check": {
                        "data": {
                            "comparison": {
                                "title": "Resolved values",
                                "leftLabel": "Before",
                                "rightLabel": "After",
                                "rows": [
                                    {
                                        "key": "score",
                                        "label": "Score",
                                        "before": 4,
                                        "after": 7,
                                        "outcome": "improved",
                                    }
                                ],
                            }
                        },
                        "verdict": "ok",
                    }
                },
            )
        )

        execution = next(node for node in spec.layout.children if node.id == "ui_execution")
        self.assertEqual([node.type for node in execution.children], ["timeline", "compare"])


if __name__ == "__main__":
    unittest.main()
