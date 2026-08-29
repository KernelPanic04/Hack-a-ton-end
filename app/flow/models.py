"""Definiciones estáticas de workflow (Pydantic, no DB). Una WorkflowVersionModel
persiste la salida de `FlowDefinition.model_dump()` en su columna `steps`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class StepDefinition(BaseModel):
    """A runtime-editable workflow step.

    This model is deliberately domain-neutral: an editor may define a step
    that the backend has never seen as long as it declares its objective and
    input paths.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
    type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=500)
    inputs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class FlowDefinition(BaseModel):
    workflow_id: str
    version: int
    steps: list[StepDefinition]

    @model_validator(mode="after")
    def validate_step_ids(self) -> "FlowDefinition":
        if not self.steps:
            raise ValueError("A workflow version requires at least one step")
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step IDs must be unique")
        return self

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
