"""Boundary between a model-generated layout and trusted run metadata."""

from typing import Any

from app.schemas.contracts import ContractModel, PageNode, UISpec


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
