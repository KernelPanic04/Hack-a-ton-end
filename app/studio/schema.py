"""UI contract for prompt-driven Studio generation.

Reuses the safe, run-agnostic node primitives from ``app.schemas.contracts``
(``metric``, ``alert``, ``timeline``, ``keyValue``, ``compare``, ``map``,
``step``) and adds two new ones (``button``, ``text``) plus a layout-capable
``section``. ``decisionPanel`` is deliberately excluded: it is the one
primitive tied to a policy-authorized ``actionId``, which does not exist
here — there is no run.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from app.schemas.contracts import (
    AlertNode,
    CompareNode,
    ContractModel,
    Emphasis,
    KeyValueNode,
    MapNode,
    MetricNode,
    PageProps,
    SCHEMA_VERSION,
    SectionProps,
    StepNode,
    TimelineNode,
    UINodeId,
)


class ButtonProps(ContractModel):
    label: str = Field(min_length=1, max_length=80)
    variant: Literal["primary", "secondary", "ghost", "danger"] = "primary"
    size: Literal["sm", "md", "lg"] = "md"


class ButtonNode(ContractModel):
    id: UINodeId
    type: Literal["button"]
    props: ButtonProps


class TextProps(ContractModel):
    content: str = Field(min_length=1, max_length=2000)
    variant: Literal["heading", "body", "caption"] = "body"
    emphasis: Emphasis = "normal"


class TextNode(ContractModel):
    id: UINodeId
    type: Literal["text"]
    props: TextProps


class StudioSectionProps(SectionProps):
    """``SectionProps`` plus the layout controls prompts actually ask for."""

    direction: Literal["row", "column"] = "column"
    gap: Literal["sm", "md", "lg"] = "md"
    align: Literal["start", "center", "end", "stretch"] = "stretch"
    justify: Literal["start", "center", "end", "between"] = "start"


class StudioSectionNode(ContractModel):
    id: UINodeId
    type: Literal["section"]
    props: StudioSectionProps
    children: list[StudioUINode] = Field(default_factory=list)


class StudioPageNode(ContractModel):
    id: UINodeId
    type: Literal["page"]
    props: PageProps
    children: list[StudioUINode] = Field(min_length=1)


StudioUINode: TypeAlias = Annotated[
    StudioPageNode
    | StudioSectionNode
    | MetricNode
    | AlertNode
    | TimelineNode
    | KeyValueNode
    | CompareNode
    | StepNode
    | MapNode
    | ButtonNode
    | TextNode,
    Field(discriminator="type"),
]

StudioPageNode.model_rebuild(_types_namespace={"StudioUINode": StudioUINode})
StudioSectionNode.model_rebuild(_types_namespace={"StudioUINode": StudioUINode})


class StudioLLMOutput(ContractModel):
    """The only shape the model provider may generate.

    ``schemaVersion`` and ``generatedBy`` are backend-owned and attached only
    after this validates, matching the boundary already used for the run
    composer's LLM upgrade (see ``app/synthesis/llm_upgrade.py``).
    """

    reason: str = Field(min_length=1, max_length=500)
    suggestion: str | None = Field(default=None, max_length=300)
    layout: StudioPageNode


class StudioUISpec(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    generated_by: Literal["llm", "fallback"]
    reason: str = Field(min_length=1, max_length=500)
    suggestion: str | None = Field(default=None, max_length=300)
    layout: StudioPageNode

    @model_validator(mode="after")
    def validate_unique_node_ids(self) -> StudioUISpec:
        node_ids: set[str] = set()

        def visit(node: StudioUINode, *, root: bool = False) -> None:
            if node.id in node_ids:
                raise ValueError("layout must contain unique node ids")
            node_ids.add(node.id)
            if not root and isinstance(node, StudioPageNode):
                raise ValueError("page nodes cannot be nested")
            if isinstance(node, (StudioPageNode, StudioSectionNode)):
                for child in node.children:
                    visit(child)

        visit(self.layout, root=True)
        return self
