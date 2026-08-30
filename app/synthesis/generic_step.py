"""LLM analysis and UI adaptation for runtime-defined workflow steps."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from app.schemas.contracts import (
    CompareNode,
    CompareProps,
    ContractModel,
    StepNode,
    StepProps,
)
from app.synthesis.llm import DEFAULT_MODEL, ResponseRequest, _output_text, _request_response
from app.synthesis.llm_upgrade import describe_failure


logger = logging.getLogger(__name__)


class GenericStepLLMResult(ContractModel):
    """The complete, provider-controlled result of one generic step."""

    findings: list[str] = Field(min_length=1, max_length=10)
    comparison: CompareProps | None = None
    verdict: Literal["pass", "attention", "fail", "unknown"]
    summary: str = Field(min_length=1, max_length=500)


def generic_step_output_format() -> dict[str, Any]:
    """Create a strict Responses API schema from the Pydantic result model."""

    schema = GenericStepLLMResult.model_json_schema(by_alias=True)

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
                value.pop("discriminator", None)
            if value.get("type") == "object":
                properties = value.get("properties", {})
                value["additionalProperties"] = False
                value["required"] = list(properties)
            for child in value.values():
                normalize(child)
        elif isinstance(value, list):
            for child in value:
                normalize(child)

    normalize(schema)
    return {
        "type": "json_schema",
        "name": "generic_step_result",
        "strict": True,
        "schema": schema,
    }


def _blank_result(attempts: int, error: Exception | None) -> GenericStepLLMResult:
    reason = (
        f"No se pudo generar el análisis solicitado tras {attempts} intentos "
        f"({describe_failure(error)})."
    )
    return GenericStepLLMResult(
        findings=[reason],
        comparison=None,
        verdict="unknown",
        summary=reason,
    )


class GenericStepLLMExecutor:
    """Analyze resolved inputs while keeping the deterministic executor authoritative.

    ``analyze`` returns ``None`` on any provider, timeout, or validation failure.
    The caller therefore retains its deterministic result and can always advance
    the run without a network dependency.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 5.0,
        retries: int = 5,
        enabled: bool | None = None,
        request_response: ResponseRequest = _request_response,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.request_response = request_response
        configured_enabled = (
            enabled
            if enabled is not None
            else os.getenv("GENERIC_STEP_LLM_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"}
        )
        self.enabled = bool(self.api_key) and configured_enabled

    def _payload(
        self,
        *,
        objective: str,
        resolved_inputs: Mapping[str, Any],
        missing_inputs: list[str],
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 1400,
            "instructions": (
                "Execute one generic workflow step from its objective and resolved inputs. "
                "Return only the schema result. Findings must be grounded in the supplied "
                "inputs. Use comparison only when there are meaningful before/after values. "
                "Never invent input values or domain-specific facts."
            ),
            "input": json.dumps(
                {
                    "objective": objective,
                    "resolvedInputs": resolved_inputs,
                    "missingInputs": missing_inputs,
                },
                separators=(",", ":"),
            ),
            "text": {"format": generic_step_output_format()},
        }

    async def analyze(
        self,
        *,
        objective: str,
        resolved_inputs: Mapping[str, Any],
        missing_inputs: list[str],
    ) -> GenericStepLLMResult | None:
        """Return a validated LLM analysis.

        ``None`` means the executor is disabled (deterministic-only mode) and
        the caller should proceed with resolved-input data alone. When it is
        enabled but every retry fails, this returns a blank fallback result
        instead of ``None``: the caller would otherwise merge in nothing and
        silently look identical to a deterministic-only run.
        """
        if not self.enabled:
            return None

        payload = self._payload(
            objective=objective,
            resolved_inputs=resolved_inputs,
            missing_inputs=missing_inputs,
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.request_response,
                        payload,
                        self.api_key,
                        self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds,
                )
                return GenericStepLLMResult.model_validate_json(_output_text(response))
            except Exception as exc:  # provider, timeout and schema failures fall back
                last_error = exc
                if attempt >= self.retries:
                    logger.warning(
                        "Generic-step LLM analysis failed after %s attempts; returning blank result: %s",
                        self.retries + 1,
                        type(exc).__name__,
                    )
                    return _blank_result(self.retries + 1, last_error)
        return _blank_result(self.retries + 1, last_error)


def result_nodes(
    step_id: str,
    title: str,
    objective: str,
    result: GenericStepLLMResult,
) -> list[StepNode | CompareNode]:
    """Adapt a validated result into registry-bounded nodes.

    The comparison is deliberately represented by the ``compare`` primitive,
    never by a look-alike ``keyValue`` structure.
    """

    wire_step_id = step_id if step_id.startswith("step_") else f"step_{step_id}"
    node_suffix = re.sub(r"[^a-z0-9_-]", "_", step_id.lower())
    emphasis = (
        "critical"
        if result.verdict == "fail"
        else "warning"
        if result.verdict == "attention"
        else "normal"
    )
    nodes: list[StepNode | CompareNode] = [
        StepNode(
            id=f"ui_{node_suffix}_result",
            type="step",
            props=StepProps(
                step_id=wire_step_id,
                title=title,
                objective=objective,
                status="attention" if result.verdict in {"attention", "fail"} else "completed",
                summary=result.summary,
                verdict=result.verdict,
                emphasis=emphasis,
            ),
        )
    ]
    if result.comparison is not None:
        nodes.append(
            CompareNode(
                id=f"ui_{node_suffix}_comparison",
                type="compare",
                props=result.comparison,
            )
        )
    return nodes
