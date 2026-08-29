"""Definiciones estáticas de workflow (Pydantic, no DB). Una WorkflowVersionModel
persiste la salida de `FlowDefinition.model_dump()` en su columna `steps`."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StepDefinition(BaseModel):
    id: str
    type: str
    title: str
    objective: str
    inputs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class FlowDefinition(BaseModel):
    workflow_id: str
    version: int
    steps: list[StepDefinition]

    def step_by_id(self, step_id: str) -> StepDefinition | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def first_step(self) -> StepDefinition:
        return self.steps[0]

    def next_step(self, current_step_id: str) -> StepDefinition | None:
        ids = [s.id for s in self.steps]
        idx = ids.index(current_step_id)
        return self.steps[idx + 1] if idx + 1 < len(ids) else None

    def is_last_step(self, step_id: str) -> bool:
        return self.steps[-1].id == step_id
