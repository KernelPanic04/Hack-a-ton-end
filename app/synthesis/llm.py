"""Progressive, contract-safe UISpec upgrades through the Responses API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from app.schemas.contracts import RunProjection, UISpec
from app.synthesis.llm_upgrade import (
    blank_ui_spec,
    describe_failure,
    merge_llm_upgrade,
    structured_output_format,
    validate_llm_upgrade,
)


RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-mini"
logger = logging.getLogger(__name__)

ResponseRequest = Callable[[dict[str, Any], str, float], dict[str, Any]]


def _contains_map(node: Any) -> bool:
    if getattr(node, "type", None) == "map":
        return True
    return any(_contains_map(child) for child in getattr(node, "children", []))


def _map_props(node: Any) -> list[dict[str, Any]]:
    current = []
    if getattr(node, "type", None) == "map":
        current.append(node.props.model_dump(mode="json", by_alias=True))
    for child in getattr(node, "children", []):
        current.extend(_map_props(child))
    return current


def _output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                return content["text"]
    raise ValueError("Responses API returned no output_text content")


def _request_response(
    payload: dict[str, Any], api_key: str, timeout_seconds: float
) -> dict[str, Any]:
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(  # nosec B310: the destination is a fixed HTTPS endpoint
        request, timeout=timeout_seconds
    ) as response:
        return json.loads(response.read().decode("utf-8"))


class LLMComposer:
    """Upgrade a deterministic UISpec without taking authority over run state.

    The model may only return ``reason`` and a registry-bounded ``layout``.
    Identifiers, versions and allowed actions are copied from the deterministic
    baseline and the merged UISpec is validated again by Pydantic.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        retries: int = 5,
        enabled: bool | None = None,
        request_response: ResponseRequest = _request_response,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("LLM_UPGRADE_TIMEOUT_SECONDS", "12"))
        )
        self.retries = retries
        self.request_response = request_response
        configured_enabled = (
            enabled
            if enabled is not None
            else os.getenv("LLM_UPGRADE_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"}
        )
        self.enabled = bool(self.api_key) and configured_enabled

    def _payload(self, projection: RunProjection, baseline: UISpec) -> dict[str, Any]:
        allowed_action_ids = [
            action.action_id for action in projection.available_actions
        ]
        input_payload = {
            "projection": projection.model_dump(mode="json", by_alias=True),
            "deterministicLayout": baseline.layout.model_dump(
                mode="json", by_alias=True
            ),
            "availableActionIds": allowed_action_ids,
        }
        return {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 2400,
            "instructions": (
                "Improve the hierarchy of the supplied declarative run UI. "
                "Use only nodes permitted by the output schema. Never invent "
                "run metadata or actions. If you render a decisionPanel, its "
                "actionId values must come exactly from availableActionIds. "
                "If deterministicLayout contains a map node, preserve a map node "
                "with its route data while reorganizing the hierarchy. "
                "Keep labels concise and explain the layout choice in reason."
            ),
            "input": json.dumps(input_payload, separators=(",", ":")),
            "text": {"format": structured_output_format()},
        }

    async def compose_upgrade(
        self, projection: RunProjection, baseline: UISpec
    ) -> UISpec | None:
        """Return a validated LLM upgrade.

        ``None`` means the composer is disabled (deterministic-only mode, see
        ``LLM_UPGRADE_ENABLED``/``OPENAI_API_KEY``) and the caller should keep
        showing the deterministic baseline. When the composer is enabled but
        every retry fails, this returns a blank fallback ``UISpec`` instead of
        the deterministic baseline: a guessed layout unrelated to what the LLM
        was asked to build is worse than an explicit "not available" screen.
        """

        if not self.enabled:
            return None

        payload = self._payload(projection, baseline)
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
                upgrade = validate_llm_upgrade(_output_text(response))
                if _contains_map(baseline.layout) and _map_props(baseline.layout) != _map_props(upgrade.layout):
                    raise ValueError("LLM upgrade changed or removed a trusted map node")
                return merge_llm_upgrade(baseline, upgrade)
            except Exception as exc:  # provider, timeout and schema failures all fall back
                last_error = exc
                if attempt >= self.retries:
                    logger.warning(
                        "LLM UISpec upgrade failed after %s attempts; showing blank fallback: %s",
                        self.retries + 1,
                        type(exc).__name__,
                    )
                    return blank_ui_spec(
                        projection,
                        reason=(
                            f"No se pudo generar la interfaz solicitada tras {self.retries + 1} "
                            f"intentos ({describe_failure(last_error)})."
                        ),
                    )
        return blank_ui_spec(
            projection,
            reason=(
                f"No se pudo generar la interfaz solicitada tras {self.retries + 1} "
                f"intentos ({describe_failure(last_error)})."
            ),
        )
