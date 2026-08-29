"""Generic, deterministic ``RunProjection`` to ``UISpec`` composer.

This module deliberately knows only the frozen runtime contract.  It selects a
layout from run status, verdict-like values, pending human work and the shapes
of values in the projection; domain fixtures remain outside synthesis.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.contracts import RunProjection, UISpec


class DeterministicComposer:
    """Build a valid UI tree synchronously, with no network or model calls."""

    def compose(self, projection: RunProjection) -> UISpec:
        prefix = f"ui_{projection.state_version}"
        has_anomaly = self._has_attention(projection)
        values = self._values(projection.operation)
        if projection.pending_decision is not None:
            children, reason = self._decision_layout(projection, prefix, values)
        elif has_anomaly:
            children, reason = self._anomaly_layout(projection, prefix, values)
        else:
            children, reason = self._standard_layout(projection, prefix, values)

        return UISpec.model_validate(
            {
                "runId": projection.run_id,
                "workflowId": projection.workflow_id,
                "workflowVersion": projection.workflow_version,
                "stateVersion": projection.state_version,
                "generatedBy": "deterministic",
                "reason": reason,
                "layout": {
                    "id": f"{prefix}_page",
                    "type": "page",
                    "props": {"title": "Agent run", "eyebrow": "Live runtime"},
                    "children": children,
                },
                "allowedActions": projection.available_actions,
            }
        )

    def _standard_layout(
        self, projection: RunProjection, prefix: str, values: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str]:
        execution_children = self._step_and_timeline(projection, prefix, emphasis="normal")
        children: list[dict[str, Any]] = [
            {
                "id": f"{prefix}_summary",
                "type": "section",
                "props": {"title": "Run status", "columns": 2},
                "children": [
                    self._metric(prefix, "status", "Status", projection.status),
                    self._metric(prefix, "version", "State version", projection.state_version),
                ],
            },
            {
                "id": f"{prefix}_execution",
                "type": "section",
                "props": {"title": "Execution", "columns": 1},
                "children": execution_children,
            },
        ]
        if values:
            children.append(self._value_node(prefix, values, emphasis="normal"))
        return children, "Run status and generic metadata select the standard layout."

    def _anomaly_layout(
        self, projection: RunProjection, prefix: str, values: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str]:
        evidence = self._step_and_timeline(projection, prefix, emphasis="warning")
        if values:
            evidence.append(self._value_node(prefix, values, emphasis="warning"))
        children: list[dict[str, Any]] = [
            {
                "id": f"{prefix}_alert",
                "type": "alert",
                "props": {
                    "title": "Attention required",
                    "message": "Runtime metadata reports an attention or failure verdict.",
                    "emphasis": "warning",
                },
            },
            {
                "id": f"{prefix}_evidence",
                "type": "section",
                "props": {"title": "Attention evidence", "columns": 1, "emphasis": "warning"},
                "children": evidence,
            },
        ]
        return children, "An attention or failure verdict selects the anomaly layout."

    def _decision_layout(
        self, projection: RunProjection, prefix: str, values: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str]:
        decision = projection.pending_decision
        assert decision is not None
        children: list[dict[str, Any]] = [
            {
                "id": f"{prefix}_decision_alert",
                "type": "alert",
                "props": {"title": "Human review required", "message": decision.prompt, "emphasis": "warning"},
            },
            {
                "id": f"{prefix}_decision",
                "type": "decisionPanel",
                "props": {
                    "decisionId": decision.decision_id,
                    "title": decision.title,
                    "message": decision.prompt,
                    "actions": [
                        {
                            "actionId": action.action_id,
                            "label": action.label,
                            "style": "primary" if index == 0 else "secondary",
                        }
                        for index, action in enumerate(projection.available_actions)
                    ],
                },
            },
        ]
        timeline = self._timeline(projection, prefix)
        if timeline is not None:
            children.append(timeline)
        if values:
            children.append(self._value_node(prefix, values, emphasis="warning"))
        return children, "Pending human review selects the decision layout."

    @staticmethod
    def _metric(prefix: str, suffix: str, label: str, value: str | int) -> dict[str, Any]:
        return {"id": f"{prefix}_{suffix}", "type": "metric", "props": {"label": label, "value": value}}

    def _step_and_timeline(
        self, projection: RunProjection, prefix: str, emphasis: str
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        if projection.current_step is not None:
            step = projection.current_step
            nodes.append(
                {
                    "id": f"{prefix}_step",
                    "type": "step",
                    "props": {
                        "stepId": step.id,
                        "title": step.title,
                        "objective": step.objective,
                        "status": step.status,
                        "verdict": "attention" if emphasis == "warning" else "unknown",
                        "emphasis": emphasis,
                    },
                }
            )
        timeline = self._timeline(projection, prefix)
        if timeline is not None:
            nodes.append(timeline)
        return nodes

    @staticmethod
    def _value_node(prefix: str, values: list[dict[str, Any]], emphasis: str) -> dict[str, Any]:
        return {
            "id": f"{prefix}_values",
            "type": "keyValue",
            "props": {
                "title": "Current data",
                "items": [{**value, "emphasis": emphasis} for value in values],
                "columns": 2,
            },
        }

    @staticmethod
    def _has_attention(projection: RunProjection) -> bool:
        current = projection.current_step
        if current is not None and current.status in {"attention", "failed"}:
            return True
        return any(
            value in {"attention", "fail"}
            for key, value in DeterministicComposer._scalar_items(projection.operation)
            if key.endswith("verdict") and isinstance(value, str)
        )

    @staticmethod
    def _timeline(projection: RunProjection, prefix: str) -> dict[str, Any] | None:
        items_by_step: dict[str, dict[str, Any]] = {}
        for event in projection.recent_events:
            if event.step_id is None:
                continue
            status = "completed" if event.type == "STEP_COMPLETED" else "active"
            if event.type == "DECISION_REQUIRED":
                status = "attention"
            items_by_step[event.step_id] = {
                "id": event.step_id,
                "title": event.step_id.removeprefix("step_").replace("_", " ").title(),
                "status": status,
                "timestamp": event.timestamp,
            }
        if not items_by_step:
            return None
        return {
            "id": f"{prefix}_timeline",
            "type": "timeline",
            "props": {"title": "Execution timeline", "items": list(items_by_step.values())},
        }

    @staticmethod
    def _values(operation: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for key, value in DeterministicComposer._scalar_items(operation):
            values.append(
                {
                    "key": key,
                    "label": key.replace("_", " ").replace(".", " ").title(),
                    "value": value,
                }
            )
            if len(values) == 8:
                break
        return values

    @staticmethod
    def _scalar_items(value: Any, path: str = "") -> Iterable[tuple[str, str | int | float | bool]]:
        if isinstance(value, dict):
            for key, nested in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                yield from DeterministicComposer._scalar_items(nested, next_path)
        elif isinstance(value, (str, int, float, bool)) and path:
            yield path, value
