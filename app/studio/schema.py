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
    DisplayValue,
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

# A free-form accent color, opt-in on top of the fixed emphasis/variant
# palette. Hex-only (no CSS keywords, no arbitrary strings) so it drops
# straight into an inline style without any sanitization step.
HexColor: TypeAlias = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class ButtonProps(ContractModel):
    label: str = Field(min_length=1, max_length=80)
    variant: Literal["primary", "secondary", "ghost", "danger"] = "primary"
    size: Literal["sm", "md", "lg"] = "md"
    color: HexColor | None = None


class ButtonNode(ContractModel):
    id: UINodeId
    type: Literal["button"]
    props: ButtonProps


class TextProps(ContractModel):
    content: str = Field(min_length=1, max_length=2000)
    variant: Literal["heading", "body", "caption"] = "body"
    emphasis: Emphasis = "normal"
    color: HexColor | None = None


class TextNode(ContractModel):
    id: UINodeId
    type: Literal["text"]
    props: TextProps


class SearchBarProps(ContractModel):
    label: str | None = Field(default=None, max_length=80)
    placeholder: str = Field(default="Buscar…", max_length=100)
    value: str | None = Field(default=None, max_length=200)


class SearchBarNode(ContractModel):
    id: UINodeId
    type: Literal["searchBar"]
    props: SearchBarProps


class DropdownOption(ContractModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=80)


class DropdownProps(ContractModel):
    label: str | None = Field(default=None, max_length=80)
    placeholder: str | None = Field(default=None, max_length=100)
    options: list[DropdownOption] = Field(min_length=1, max_length=30)
    selected_value: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_selected_value(self) -> DropdownProps:
        if self.selected_value is not None:
            known = {option.value for option in self.options}
            if self.selected_value not in known:
                raise ValueError("dropdown selectedValue must match a declared option value")
        return self


class DropdownNode(ContractModel):
    id: UINodeId
    type: Literal["dropdown"]
    props: DropdownProps


class ChartPoint(ContractModel):
    label: str = Field(min_length=1, max_length=40)
    value: float
    color: HexColor | None = None


class ChartProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    chart_type: Literal["bar", "line", "pie"] = "bar"
    points: list[ChartPoint] = Field(min_length=1, max_length=20)
    emphasis: Emphasis = "normal"


class ChartNode(ContractModel):
    id: UINodeId
    type: Literal["chart"]
    props: ChartProps


class TableProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    columns: list[str] = Field(min_length=1, max_length=8)
    rows: list[list[DisplayValue]] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_row_widths(self) -> TableProps:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("table rows must each match the number of columns")
        return self


class TableNode(ContractModel):
    id: UINodeId
    type: Literal["table"]
    props: TableProps


class ProgressProps(ContractModel):
    label: str = Field(min_length=1, max_length=80)
    value: float = Field(ge=0, le=100)
    supporting_text: str | None = Field(default=None, max_length=160)
    emphasis: Emphasis = "normal"
    color: HexColor | None = None


class ProgressNode(ContractModel):
    id: UINodeId
    type: Literal["progress"]
    props: ProgressProps


class TagItem(ContractModel):
    label: str = Field(min_length=1, max_length=40)
    tone: Emphasis = "normal"
    color: HexColor | None = None


class TagsProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    items: list[TagItem] = Field(min_length=1, max_length=20)


class TagsNode(ContractModel):
    id: UINodeId
    type: Literal["tags"]
    props: TagsProps


class StudioSectionProps(SectionProps):
    """``SectionProps`` plus the layout controls prompts actually ask for."""

    direction: Literal["row", "column"] = "column"
    gap: Literal["sm", "md", "lg"] = "md"
    align: Literal["start", "center", "end", "stretch"] = "stretch"
    justify: Literal["start", "center", "end", "between"] = "start"
    background_color: HexColor | None = None


class StudioSectionNode(ContractModel):
    id: UINodeId
    type: Literal["section"]
    props: StudioSectionProps
    children: list[StudioUINode] = Field(default_factory=list)


class StudioPageProps(PageProps):
    """``PageProps`` plus a whole-page background color."""

    background_color: HexColor | None = None


class StudioPageNode(ContractModel):
    id: UINodeId
    type: Literal["page"]
    props: StudioPageProps
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
    | TextNode
    | SearchBarNode
    | DropdownNode
    | ChartNode
    | TableNode
    | ProgressNode
    | TagsNode,
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


class StudioOrchestration(ContractModel):
    """What the orchestrator decided for one generation.

    Surfaced on the wire so the UI can show *how* the prompt, the conversation
    history and the recent feedback shaped the model call — the reasoning
    effort the escalation curve picked, the recent-rating average behind it,
    and whether a previous layout was replayed for editing.
    """

    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    feedback_average: float | None = None
    feedback_count: int = 0
    history_turns: int = 0
    used_previous_layout: bool = False


class StudioUISpec(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    generated_by: Literal["llm", "fallback", "guidance"]
    reason: str = Field(min_length=1, max_length=500)
    suggestion: str | None = Field(default=None, max_length=300)
    orchestration: StudioOrchestration | None = None
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
