"""Frozen v1 contracts shared by the run engine, UI synthesis, and frontend.

Pydantic is the executable authority. The TypeScript mirror lives at
``Hack-a-ton-front/src/runtime/contracts.ts``. Update both, the Phase 0 docs,
and the decision log in the same change.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)
from pydantic.alias_generators import to_camel


SCHEMA_VERSION = "1"


class ContractModel(BaseModel):
    """Strict camelCase wire model with ergonomic snake_case Python fields."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        validate_assignment=True,
    )


def _id(prefix: str) -> Field:
    return Field(
        min_length=len(prefix) + 2,
        max_length=len(prefix) + 129,
        pattern=rf"^{prefix}_[a-z0-9][a-z0-9_-]{{0,127}}$",
    )


WorkflowId: TypeAlias = Annotated[str, _id("wf")]
StepId: TypeAlias = Annotated[str, _id("step")]
RunId: TypeAlias = Annotated[str, _id("run")]
OperationId: TypeAlias = Annotated[str, _id("op")]
DecisionId: TypeAlias = Annotated[str, _id("dec")]
ActionId: TypeAlias = Annotated[str, _id("act")]
EventId: TypeAlias = Annotated[str, _id("evt")]
IdempotencyKey: TypeAlias = Annotated[str, _id("idem")]
UINodeId: TypeAlias = Annotated[str, _id("ui")]

Emphasis: TypeAlias = Literal["normal", "warning", "critical"]
DisplayValue: TypeAlias = str | int | float | bool
ComparableValue: TypeAlias = DisplayValue | None
JsonObject: TypeAlias = dict[str, JsonValue]

RunStatus: TypeAlias = Literal[
    "created", "running", "paused", "completed", "failed"
]
StepStatus: TypeAlias = Literal[
    "pending", "active", "completed", "attention", "failed"
]
ActionRisk: TypeAlias = Literal["low", "medium", "high", "critical"]


class RunEventType(str, Enum):
    """Canonical event names used by the append-only runtime log."""

    RUN_STARTED = "RUN_STARTED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STATE_UPDATED = "STATE_UPDATED"
    UI_UPDATED = "UI_UPDATED"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    ACTION_ACCEPTED = "ACTION_ACCEPTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    RUN_PAUSED = "RUN_PAUSED"
    RUN_RESUMED = "RUN_RESUMED"
    RUN_COMPLETED = "RUN_COMPLETED"
    WORKFLOW_VERSION_CREATED = "WORKFLOW_VERSION_CREATED"
    ERROR = "ERROR"


class ActionDefinition(ContractModel):
    action_id: ActionId
    label: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    risk: ActionRisk
    requires_human: bool
    payload_schema: JsonObject = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )


class DecisionRequest(ContractModel):
    decision_id: DecisionId
    step_id: StepId
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=500)
    context: JsonObject = Field(default_factory=dict)
    requested_at: AwareDatetime


class RunStepProjection(ContractModel):
    id: StepId
    type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=120)
    objective: str | None = Field(default=None, max_length=500)
    status: StepStatus
    metadata: JsonObject = Field(default_factory=dict)


class RunEvent(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    event_id: EventId
    run_id: RunId
    workflow_id: WorkflowId
    workflow_version: int = Field(ge=1)
    sequence: int = Field(ge=1)
    state_version: int = Field(ge=0)
    type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    step_id: StepId | None = None
    payload: JsonValue = Field(default_factory=dict)
    timestamp: AwareDatetime


class RunProjection(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: RunId
    operation_id: OperationId | None = None
    workflow_id: WorkflowId
    workflow_version: int = Field(ge=1)
    state_version: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    status: RunStatus
    current_step: RunStepProjection | None = None
    operation: JsonObject = Field(default_factory=dict)
    recent_events: list[RunEvent] = Field(default_factory=list, max_length=50)
    pending_decision: DecisionRequest | None = None
    available_actions: list[ActionDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_projection_invariants(self) -> RunProjection:
        action_ids = [action.action_id for action in self.available_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("availableActions must contain unique actionId values")

        if self.pending_decision is None and self.available_actions:
            raise ValueError("availableActions must be empty without pendingDecision")
        if self.pending_decision is not None and not self.available_actions:
            raise ValueError("pendingDecision requires at least one availableAction")

        sequences = [event.sequence for event in self.recent_events]
        if sequences != sorted(sequences):
            raise ValueError("recentEvents must be ordered by sequence")

        for event in self.recent_events:
            if event.run_id != self.run_id or event.workflow_id != self.workflow_id:
                raise ValueError("recentEvents must belong to this run and workflow")
            if event.workflow_version != self.workflow_version:
                raise ValueError("recentEvents must match workflowVersion")
            if event.sequence > self.last_sequence:
                raise ValueError("recentEvents cannot exceed lastSequence")

        return self


class PageProps(ContractModel):
    title: str = Field(min_length=1, max_length=120)
    subtitle: str | None = Field(default=None, max_length=240)
    eyebrow: str | None = Field(default=None, max_length=80)


class SectionProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    columns: Literal[1, 2, 3] = 1
    emphasis: Emphasis = "normal"


class MetricProps(ContractModel):
    label: str = Field(min_length=1, max_length=80)
    value: str | int | float
    supporting_text: str | None = Field(default=None, max_length=160)
    trend: Literal["up", "down", "flat"] | None = None
    emphasis: Emphasis = "normal"


class AlertProps(ContractModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    emphasis: Emphasis


class TimelineItem(ContractModel):
    id: StepId
    title: str = Field(min_length=1, max_length=120)
    status: StepStatus
    detail: str | None = Field(default=None, max_length=300)
    timestamp: AwareDatetime | None = None


class TimelineProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    items: list[TimelineItem] = Field(min_length=1)


class KeyValueItem(ContractModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=100)
    value: DisplayValue
    emphasis: Emphasis = "normal"


class KeyValueProps(ContractModel):
    title: str | None = Field(default=None, max_length=120)
    items: list[KeyValueItem] = Field(min_length=1)
    columns: Literal[1, 2] = 1


class CompareRow(ContractModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=100)
    before: ComparableValue
    after: ComparableValue
    outcome: Literal["same", "changed", "improved", "worse", "attention"]


class CompareProps(ContractModel):
    title: str = Field(min_length=1, max_length=120)
    left_label: str = Field(min_length=1, max_length=80)
    right_label: str = Field(min_length=1, max_length=80)
    rows: list[CompareRow] = Field(min_length=1)


class DecisionAction(ContractModel):
    action_id: ActionId
    label: str = Field(min_length=1, max_length=100)
    style: Literal["primary", "secondary", "danger"] = "secondary"
    requires_confirmation: bool = False


class DecisionPanelProps(ContractModel):
    decision_id: DecisionId
    title: str = Field(min_length=1, max_length=120)
    message: str | None = Field(default=None, max_length=500)
    actions: list[DecisionAction] = Field(min_length=1)
    status: Literal["idle", "submitting", "accepted", "rejected"] = "idle"
    error_message: str | None = Field(default=None, max_length=300)
    emphasis: Emphasis = "warning"

    @model_validator(mode="after")
    def validate_decision_panel(self) -> DecisionPanelProps:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("decisionPanel actions must contain unique actionId values")
        if self.status == "rejected" and not self.error_message:
            raise ValueError("rejected decisionPanel requires errorMessage")
        return self


class StepProps(ContractModel):
    step_id: StepId
    title: str = Field(min_length=1, max_length=120)
    objective: str | None = Field(default=None, max_length=500)
    status: StepStatus
    summary: str | None = Field(default=None, max_length=500)
    verdict: Literal["pass", "attention", "fail", "unknown"] | None = None
    emphasis: Emphasis = "normal"


class MapWaypoint(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    kind: Literal["origin", "stop", "destination"]


class MapMarker(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(min_length=1, max_length=120)


class MapSegment(ContractModel):
    from_id: str = Field(alias="from", min_length=1, max_length=80)
    to: str = Field(min_length=1, max_length=80)
    status: Literal["planned", "active", "diverted"]


class MapProps(ContractModel):
    waypoints: list[MapWaypoint] = Field(min_length=2)
    marker: MapMarker | None = None
    segments: list[MapSegment] = Field(min_length=1)
    emphasis: Emphasis = "normal"


class PageNode(ContractModel):
    id: UINodeId
    type: Literal["page"]
    props: PageProps
    children: list[UINode] = Field(min_length=1)


class SectionNode(ContractModel):
    id: UINodeId
    type: Literal["section"]
    props: SectionProps
    children: list[UINode] = Field(default_factory=list)


class MetricNode(ContractModel):
    id: UINodeId
    type: Literal["metric"]
    props: MetricProps


class AlertNode(ContractModel):
    id: UINodeId
    type: Literal["alert"]
    props: AlertProps


class TimelineNode(ContractModel):
    id: UINodeId
    type: Literal["timeline"]
    props: TimelineProps


class KeyValueNode(ContractModel):
    id: UINodeId
    type: Literal["keyValue"]
    props: KeyValueProps


class CompareNode(ContractModel):
    id: UINodeId
    type: Literal["compare"]
    props: CompareProps


class DecisionPanelNode(ContractModel):
    id: UINodeId
    type: Literal["decisionPanel"]
    props: DecisionPanelProps


class StepNode(ContractModel):
    id: UINodeId
    type: Literal["step"]
    props: StepProps


class MapNode(ContractModel):
    id: UINodeId
    type: Literal["map"]
    props: MapProps


UINode: TypeAlias = Annotated[
    PageNode
    | SectionNode
    | MetricNode
    | AlertNode
    | TimelineNode
    | KeyValueNode
    | CompareNode
    | DecisionPanelNode
    | StepNode
    | MapNode,
    Field(discriminator="type"),
]

PageNode.model_rebuild(_types_namespace={"UINode": UINode})
SectionNode.model_rebuild(_types_namespace={"UINode": UINode})


class UISpec(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: RunId
    workflow_id: WorkflowId
    workflow_version: int = Field(ge=1)
    state_version: int = Field(ge=0)
    generated_by: Literal["deterministic", "llm", "fallback"]
    reason: str = Field(min_length=1, max_length=500)
    layout: PageNode
    allowed_actions: list[ActionDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ui_invariants(self) -> UISpec:
        allowed_action_ids = [action.action_id for action in self.allowed_actions]
        if len(allowed_action_ids) != len(set(allowed_action_ids)):
            raise ValueError("allowedActions must contain unique actionId values")

        node_ids: set[str] = set()

        def visit(node: UINode, *, root: bool = False) -> None:
            if node.id in node_ids:
                raise ValueError("layout must contain unique node ids")
            node_ids.add(node.id)

            if not root and isinstance(node, PageNode):
                raise ValueError("page nodes cannot be nested")

            if isinstance(node, DecisionPanelNode):
                panel_action_ids = {
                    action.action_id for action in node.props.actions
                }
                unknown = panel_action_ids.difference(allowed_action_ids)
                if unknown:
                    raise ValueError(
                        "decisionPanel actions must exist in allowedActions: "
                        + ", ".join(sorted(unknown))
                    )

            if isinstance(node, (PageNode, SectionNode)):
                for child in node.children:
                    visit(child)

        visit(self.layout, root=True)
        return self


class ActionEvent(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    idempotency_key: IdempotencyKey
    run_id: RunId
    workflow_version: int = Field(ge=1)
    state_version: int = Field(ge=0)
    decision_id: DecisionId
    action_id: ActionId
    payload: JsonValue = Field(default_factory=dict)
    timestamp: AwareDatetime


ProjectionMessageType: TypeAlias = Literal[
    "RUN_STARTED",
    "STEP_STARTED",
    "STEP_COMPLETED",
    "STATE_UPDATED",
    "DECISION_REQUIRED",
    "RUN_PAUSED",
    "RUN_RESUMED",
    "RUN_COMPLETED",
]

SERVER_MESSAGE_TYPES = (
    "RUN_STARTED",
    "STEP_STARTED",
    "STEP_COMPLETED",
    "STATE_UPDATED",
    "UI_UPDATED",
    "DECISION_REQUIRED",
    "ACTION_ACCEPTED",
    "ACTION_REJECTED",
    "RUN_PAUSED",
    "RUN_RESUMED",
    "RUN_COMPLETED",
    "ERROR",
)

COMPONENT_TYPES = (
    "page",
    "section",
    "metric",
    "alert",
    "timeline",
    "keyValue",
    "compare",
    "decisionPanel",
    "step",
    "map",
)


class ProjectionPayload(ContractModel):
    event: RunEvent
    projection: RunProjection


class UIUpdatedPayload(ProjectionPayload):
    ui_spec: UISpec


class ActionAcceptedPayload(ProjectionPayload):
    idempotency_key: IdempotencyKey
    decision_id: DecisionId
    action_id: ActionId


class ActionRejectedPayload(ContractModel):
    event: RunEvent
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    idempotency_key: IdempotencyKey
    current_state_version: int = Field(ge=0)


class ErrorPayload(ContractModel):
    event: RunEvent
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    retryable: bool


def _validate_server_message(
    *, run_id: str, sequence: int, event: RunEvent
) -> None:
    if event.run_id != run_id:
        raise ValueError("envelope runId must match payload event runId")
    if event.sequence != sequence:
        raise ValueError("envelope sequence must match payload event sequence")


class ProjectionEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: ProjectionMessageType
    run_id: RunId
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    payload: ProjectionPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> ProjectionEnvelope:
        _validate_server_message(
            run_id=self.run_id, sequence=self.sequence, event=self.payload.event
        )
        if self.payload.projection.run_id != self.run_id:
            raise ValueError("envelope runId must match projection runId")
        return self


class UIUpdatedEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: Literal["UI_UPDATED"]
    run_id: RunId
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    payload: UIUpdatedPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> UIUpdatedEnvelope:
        _validate_server_message(
            run_id=self.run_id, sequence=self.sequence, event=self.payload.event
        )
        projection = self.payload.projection
        ui_spec = self.payload.ui_spec
        if projection.run_id != self.run_id or ui_spec.run_id != self.run_id:
            raise ValueError("envelope, projection, and uiSpec runId must match")
        if (
            projection.workflow_id != ui_spec.workflow_id
            or projection.workflow_version != ui_spec.workflow_version
            or projection.state_version != ui_spec.state_version
        ):
            raise ValueError("uiSpec must match the projection that generated it")
        projection_actions = {
            action.action_id for action in projection.available_actions
        }
        ui_actions = {action.action_id for action in ui_spec.allowed_actions}
        if not ui_actions.issubset(projection_actions):
            raise ValueError("uiSpec allowedActions must be a subset of projection actions")
        return self


class ActionAcceptedEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: Literal["ACTION_ACCEPTED"]
    run_id: RunId
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    payload: ActionAcceptedPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> ActionAcceptedEnvelope:
        _validate_server_message(
            run_id=self.run_id, sequence=self.sequence, event=self.payload.event
        )
        if self.payload.projection.run_id != self.run_id:
            raise ValueError("envelope runId must match projection runId")
        return self


class ActionRejectedEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: Literal["ACTION_REJECTED"]
    run_id: RunId
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    payload: ActionRejectedPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> ActionRejectedEnvelope:
        _validate_server_message(
            run_id=self.run_id, sequence=self.sequence, event=self.payload.event
        )
        return self


class ErrorEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: Literal["ERROR"]
    run_id: RunId
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    payload: ErrorPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> ErrorEnvelope:
        _validate_server_message(
            run_id=self.run_id, sequence=self.sequence, event=self.payload.event
        )
        return self


class ActionSubmittedEnvelope(ContractModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    type: Literal["ACTION_SUBMITTED"]
    run_id: RunId
    sequence: int = Field(ge=0)
    timestamp: AwareDatetime
    payload: ActionEvent

    @model_validator(mode="after")
    def validate_envelope(self) -> ActionSubmittedEnvelope:
        if self.payload.run_id != self.run_id:
            raise ValueError("envelope runId must match ActionEvent runId")
        return self


ServerEnvelope: TypeAlias = Annotated[
    ProjectionEnvelope
    | UIUpdatedEnvelope
    | ActionAcceptedEnvelope
    | ActionRejectedEnvelope
    | ErrorEnvelope,
    Field(discriminator="type"),
]

WebSocketEnvelope: TypeAlias = Annotated[
    ProjectionEnvelope
    | UIUpdatedEnvelope
    | ActionAcceptedEnvelope
    | ActionRejectedEnvelope
    | ErrorEnvelope
    | ActionSubmittedEnvelope,
    Field(discriminator="type"),
]
