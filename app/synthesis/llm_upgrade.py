"""Boundary between a model-generated layout and trusted run metadata."""

from typing import Any

from app.schemas.contracts import (
    AlertNode,
    AlertProps,
    ContractModel,
    PageNode,
    PageProps,
    RunProjection,
    UISpec,
)


class LLMUISpecUpgrade(ContractModel):
    """The only shape a model provider may generate.

    IDs, state versions, and action definitions remain under backend authority
    and are copied from the deterministic baseline after this model validates.
    """

    reason: str
    layout: PageNode


def strict_output_schema() -> dict[str, Any]:
    """Generate the strict, provider-facing schema for an LLM upgrade."""

    schema = LLMUISpecUpgrade.model_json_schema(by_alias=True)

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
    return schema


def structured_output_format() -> dict[str, Any]:
    """Responses API JSON-schema configuration for the later LLM composer."""

    return {
        "type": "json_schema",
        "name": "ui_spec_upgrade",
        "strict": True,
        "schema": strict_output_schema(),
    }


def validate_llm_upgrade(payload: str | bytes | bytearray) -> LLMUISpecUpgrade:
    """Parse a provider response before it can affect the displayed UI."""

    return LLMUISpecUpgrade.model_validate_json(payload)


def merge_llm_upgrade(baseline: UISpec, upgrade: LLMUISpecUpgrade) -> UISpec:
    """Preserve trusted IDs, versions, and allowed actions from the baseline."""

    return UISpec(
        schema_version=baseline.schema_version,
        run_id=baseline.run_id,
        workflow_id=baseline.workflow_id,
        workflow_version=baseline.workflow_version,
        state_version=baseline.state_version,
        generated_by="llm",
        reason=upgrade.reason,
        layout=upgrade.layout,
        allowed_actions=baseline.allowed_actions,
    )


MAX_FAILURE_DETAIL_LENGTH = 160


def describe_failure(error: Exception | None) -> str:
    """A short, provider-safe description of the exception behind a fallback.

    Only the exception type and its own message are used — never the request
    payload or the API key — and the detail is truncated so it always fits
    inside the ``reason``/``message`` length limits.
    """

    if error is None:
        return "motivo desconocido"
    label = type(error).__name__
    detail = str(error).strip()
    if not detail:
        return label
    if len(detail) > MAX_FAILURE_DETAIL_LENGTH:
        detail = detail[:MAX_FAILURE_DETAIL_LENGTH].rstrip() + "…"
    return f"{label}: {detail}"


def blank_ui_spec(projection: RunProjection, reason: str) -> UISpec:
    """A minimal, contract-valid placeholder shown when no LLM-built layout exists.

    Used while the LLM composer is generating the requested layout and after it
    exhausts its retries; never a guessed deterministic layout unrelated to the
    request. ``allowed_actions`` still comes from the trusted projection so
    pending decisions remain actionable even in this state.
    """

    return UISpec(
        run_id=projection.run_id,
        workflow_id=projection.workflow_id,
        workflow_version=projection.workflow_version,
        state_version=projection.state_version,
        generated_by="fallback",
        reason=reason,
        layout=PageNode(
            id="ui_page",
            type="page",
            props=PageProps(title="Run overview"),
            children=[
                AlertNode(
                    id="ui_blank_fallback",
                    type="alert",
                    props=AlertProps(
                        title="Interfaz no disponible",
                        message=reason,
                        emphasis="warning",
                    ),
                )
            ],
        ),
        allowed_actions=projection.available_actions,
    )
