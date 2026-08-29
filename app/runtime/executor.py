"""Domain-neutral executor for workflow steps created at runtime (Phase 4)."""

from __future__ import annotations

import uuid
from typing import Any

from app.flow.models import StepDefinition
from app.runtime.run import RunEngine, RunEngineError
from app.runtime.status import StoredRunStatus


class GenericStepExecutor:
    """Resolve a step's declared inputs from run state and reduce its result.

    No step type is hard-coded here. Values remain visible under the completed
    step's ``data.resolved_inputs`` state, which the deterministic composer
    renders with its generic ``keyValue`` primitive.
    """

    def __init__(self, session: Any, engine: RunEngine | None = None) -> None:
        self.engine = engine or RunEngine(session)

    async def execute_current(self, run_id: uuid.UUID):
        run = await self.engine.get_run(run_id)
        if run.status != StoredRunStatus.RUNNING.value:
            raise RunEngineError(f"Run {run_id} no está corriendo (status={run.status})")
        if run.current_step_id is None:
            raise RunEngineError(f"Run {run_id} no tiene un paso actual")

        version = await self.engine.flow_engine.get_version_by_id(run.workflow_version_id)
        if version is None:
            raise RunEngineError(f"WorkflowVersion {run.workflow_version_id} no existe")
        flow = self.engine.flow_engine.to_flow_definition(version)
        step = flow.step_by_id(run.current_step_id)
        if step is None:
            raise RunEngineError(f"Step {run.current_step_id} no existe en el workflow")

        data, has_missing_inputs = self._result_data(step, run.state)
        needs_review = step.requires_human_review
        pending_decision = None
        if needs_review:
            pending_decision = {
                "title": f"Review: {step.title}",
                "prompt": step.objective,
                "context": data,
                "available_actions": ["acknowledge"],
            }

        verdict = "attention" if needs_review or has_missing_inputs else "ok"
        return await self.engine.advance(
            run_id,
            step.id,
            data,
            verdict,
            pending_decision=pending_decision,
        )

    @staticmethod
    def _result_data(step: StepDefinition, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        resolved: dict[str, Any] = {}
        missing: list[str] = []
        for index, input_path in enumerate(step.inputs, start=1):
            found, value = GenericStepExecutor._resolve_path(state, input_path)
            key = f"input_{index}"
            if found:
                resolved[key] = {"source": input_path, "value": value}
            else:
                missing.append(input_path)

        return (
            {
                "summary": step.objective,
                "resolved_inputs": resolved,
                "missing_inputs": missing,
            },
            bool(missing),
        )

    @staticmethod
    def _resolve_path(state: dict[str, Any], path: str) -> tuple[bool, Any]:
        """Resolve dotted input paths without any domain-specific mappings."""
        current: Any = state
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return False, None
            current = current[segment]
        return True, current
