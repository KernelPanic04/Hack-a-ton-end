from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID

from app.runtime.executor import GenericStepExecutor
from app.runtime.status import StoredRunStatus
from app.synthesis.generic_step import GenericStepLLMResult


RUN_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
VERSION_ID = UUID("550e8400-e29b-41d4-a716-446655440002")


class GenericStepExecutorTests(unittest.IsolatedAsyncioTestCase):
    def _executor(self, *, review: bool = False):
        run = SimpleNamespace(
            id=RUN_ID,
            workflow_version_id=VERSION_ID,
            status=StoredRunStatus.RUNNING.value,
            current_step_id="verify_inputs",
            state={"source": {"data": {"score": 7, "label": "ready"}}},
        )
        version = SimpleNamespace(
            steps=[
                {
                    "id": "verify_inputs",
                    "type": "generic.check",
                    "title": "Verify inputs",
                    "objective": "Check supplied state values.",
                    "inputs": ["source.data.score", "source.data.missing"],
                    "requires_human_review": review,
                }
            ]
        )
        flow_engine = SimpleNamespace(
            get_version_by_id=AsyncMock(return_value=version),
            to_flow_definition=lambda row: __import__("app.flow.models", fromlist=["FlowDefinition"]).FlowDefinition(
                workflow_id="workflow", version=1, steps=row.steps
            ),
        )
        engine = SimpleNamespace(
            get_run=AsyncMock(return_value=run),
            flow_engine=flow_engine,
            advance=AsyncMock(return_value=run),
        )
        return GenericStepExecutor(session=None, engine=engine), engine

    async def test_executes_unknown_step_from_declared_input_paths(self) -> None:
        executor, engine = self._executor()

        await executor.execute_current(RUN_ID)

        data = engine.advance.await_args.args[2]
        self.assertEqual(data["resolved_inputs"]["input_1"]["value"], 7)
        self.assertEqual(data["missing_inputs"], ["source.data.missing"])
        self.assertEqual(engine.advance.await_args.args[3], "attention")
        self.assertIsNone(engine.advance.await_args.kwargs["pending_decision"])

    async def test_requests_human_review_only_when_step_declares_it(self) -> None:
        executor, engine = self._executor(review=True)

        await executor.execute_current(RUN_ID)

        pending = engine.advance.await_args.kwargs["pending_decision"]
        self.assertEqual(pending["available_actions"], ["acknowledge"])
        self.assertEqual(engine.advance.await_args.args[3], "attention")

    async def test_uses_validated_llm_result_when_available(self) -> None:
        executor, engine = self._executor()

        class LLM:
            async def analyze(self, **kwargs):
                return GenericStepLLMResult(
                    findings=["The resolved input is ready."],
                    verdict="pass",
                    summary="Input analysis completed.",
                )

        executor.llm_executor = LLM()
        await executor.execute_current(RUN_ID)

        data = engine.advance.await_args.args[2]
        self.assertEqual(data["summary"], "Input analysis completed.")
        self.assertEqual(data["findings"], ["The resolved input is ready."])
        self.assertEqual(data["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
