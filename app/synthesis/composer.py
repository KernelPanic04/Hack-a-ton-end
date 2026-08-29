"""Deterministic, domain-neutral composition from a RunProjection to a UISpec."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.contracts import (
    ActionDefinition,
    AlertNode,
    AlertProps,
    DecisionAction,
    DecisionPanelNode,
    DecisionPanelProps,
    KeyValueItem,
    KeyValueNode,
    KeyValueProps,
    MetricNode,
    MetricProps,
    PageNode,
    PageProps,
    RunProjection,
    SectionNode,
    SectionProps,
    StepNode,
    StepProps,
    TimelineItem,
    TimelineNode,
    TimelineProps,
    UISpec,
)

_ATTENTION_VERDICTS = {"attention", "fail"}


def _label(value: str) -> str:
    """Turn opaque identifiers into presentable labels without domain rules."""

    return value.removeprefix("step_").replace("_", " ").replace("-", " ").title()


def _scalar_items(value: Any, *, prefix: str = "") -> Iterable[KeyValueItem]:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _scalar_items(child, prefix=path)
    elif isinstance(value, (str, int, float, bool)):
        yield KeyValueItem(key=prefix or "value", label=_label(prefix or "value"), value=value)


def _contains_attention(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_attention(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_attention(child) for child in value)
    return value in _ATTENTION_VERDICTS


def _timeline(projection: RunProjection) -> TimelineNode:
    by_step: dict[str, TimelineItem] = {}
    for event in projection.recent_events:
        if event.step_id is None:
            continue
        status = "active"
        if event.type == "STEP_COMPLETED":
            status = "completed"
        elif event.type == "DECISION_REQUIRED":
            status = "attention"
        elif event.type == "ERROR":
            status = "failed"
        by_step[event.step_id] = TimelineItem(
            id=event.step_id,
            title=_label(event.step_id),
            status=status,
            timestamp=event.timestamp,
        )

    if projection.current_step is not None:
        by_step[projection.current_step.id] = TimelineItem(
            id=projection.current_step.id,
            title=projection.current_step.title,
            status=projection.current_step.status,
        )

    items = list(by_step.values())
    if not items:
        # Timeline requires one item; this generic placeholder is valid before
        # a run has a current step or event history.
        items = [
            TimelineItem(
                id="step_initializing",
                title="Initializing",
                status="pending",
            )
        ]
    return TimelineNode(
        id="ui_timeline",
        type="timeline",
        props=TimelineProps(title="Activity", items=items),
    )


def _current_step(projection: RunProjection) -> StepNode | None:
    step = projection.current_step
    if step is None:
        return None
    verdict = "attention" if step.status == "attention" else "unknown"
    return StepNode(
        id="ui_current_step",
        type="step",
        props=StepProps(
            step_id=step.id,
            title=step.title,
            objective=step.objective,
            status=step.status,
            verdict=verdict,
            emphasis="warning" if step.status == "attention" else "normal",
        ),
    )


def _context(projection: RunProjection) -> KeyValueNode | None:
    items = list(_scalar_items(projection.operation))[:8]
    if not items:
        return None
    return KeyValueNode(
        id="ui_context",
        type="keyValue",
        props=KeyValueProps(title="Context", items=items, columns=2),
    )


def _decision_actions(actions: list[ActionDefinition]) -> list[DecisionAction]:
    return [
        DecisionAction(
            action_id=action.action_id,
            label=action.label,
            style="danger" if action.risk in {"high", "critical"} else "primary",
            requires_confirmation=action.requires_human,
        )
        for action in actions
    ]


def _decision_section(projection: RunProjection) -> SectionNode:
    decision = projection.pending_decision
    if decision is None:
        raise ValueError("decision section requires a pending decision")
    return SectionNode(
        id="ui_decision_section",
        type="section",
        props=SectionProps(title="Decision required", emphasis="warning"),
        children=[
            DecisionPanelNode(
                id="ui_decision",
                type="decisionPanel",
                props=DecisionPanelProps(
                    decision_id=decision.decision_id,
                    title=decision.title,
                    message=decision.prompt,
                    actions=_decision_actions(projection.available_actions),
                    emphasis="warning",
                ),
            )
        ],
    )


def compose(projection: RunProjection) -> UISpec:
    """Compose a valid UISpec using only generic contract metadata."""

    current = _current_step(projection)
    timeline = _timeline(projection)
    context = _context(projection)
    attention = (
        projection.current_step is not None and projection.current_step.status == "attention"
    ) or _contains_attention(projection.operation)

    page_children: list[Any]
    if projection.pending_decision is not None:
        page_children = [_decision_section(projection)]
        activity_children = [timeline]
        if current is not None:
            activity_children.insert(0, current)
        page_children.append(
            SectionNode(
                id="ui_activity_section",
                type="section",
                props=SectionProps(title="Current activity", columns=1),
                children=activity_children,
            )
        )
        reason = "A pending decision makes the permitted human actions the primary layout."
    elif attention:
        page_children = [
            AlertNode(
                id="ui_attention",
                type="alert",
                props=AlertProps(
                    title="Attention required",
                    message="The current run contains an attention-level result.",
                    emphasis="warning",
                ),
            ),
            SectionNode(
                id="ui_activity_section",
                type="section",
                props=SectionProps(title="Current activity", emphasis="warning"),
                children=[node for node in (current, timeline) if node is not None],
            ),
        ]
        reason = "An attention-level result changes the layout to foreground the alert."
    else:
        page_children = [
            SectionNode(
                id="ui_summary_section",
                type="section",
                props=SectionProps(title="Run summary", columns=2),
                children=[
                    MetricNode(
                        id="ui_run_status",
                        type="metric",
                        props=MetricProps(
                            label="Run status",
                            value=projection.status.title(),
                            emphasis="normal",
                        ),
                    ),
                    *([current] if current is not None else []),
                ],
            ),
            SectionNode(
                id="ui_activity_section",
                type="section",
                props=SectionProps(title="Activity"),
                children=[timeline],
            ),
        ]
        reason = "A stable run uses a summary-first layout with activity context."

    if context is not None:
        page_children.append(
            SectionNode(
                id="ui_context_section",
                type="section",
                props=SectionProps(title="Context"),
                children=[context],
            )
        )

    return UISpec(
        run_id=projection.run_id,
        workflow_id=projection.workflow_id,
        workflow_version=projection.workflow_version,
        state_version=projection.state_version,
        generated_by="deterministic",
        reason=reason,
        layout=PageNode(
            id="ui_page",
            type="page",
            props=PageProps(
                title="Run overview",
                subtitle=projection.current_step.title if projection.current_step else None,
            ),
            children=page_children,
        ),
        allowed_actions=projection.available_actions,
    )


class DeterministicComposer:
    """Compatibility adapter for runtime integrations that use an object API."""

    def compose(self, projection: RunProjection) -> UISpec:
        return compose(projection)
