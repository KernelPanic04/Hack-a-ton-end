"""Bounded, advisory Responses API integration for the Ari chat panel."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from app.schemas.contracts import AssistRequest, AssistResponse, RunEvent, RunProjection
from app.synthesis.llm import DEFAULT_MODEL, ResponseRequest, _output_text, _request_response


logger = logging.getLogger(__name__)


def _strict_schema() -> dict[str, Any]:
    schema = AssistResponse.model_json_schema(by_alias=True)

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
    return {"type": "json_schema", "name": "ari_assist", "strict": True, "schema": schema}


class AriAssistant:
    """Explain a trusted projection without authority to change it.

    Any output action is checked again against ``availableActions``. The
    frontend must submit it through the existing policy/WebSocket path.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 5.0,
        retries: int = 1,
        enabled: bool | None = None,
        request_response: ResponseRequest = _request_response,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.request_response = request_response
        configured = (
            enabled
            if enabled is not None
            else os.getenv("ASSISTANT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        )
        self.enabled = bool(self.api_key) and configured

    def _payload(
        self, projection: RunProjection, events: list[RunEvent], request: AssistRequest
    ) -> dict[str, Any]:
        action_ids = [action.action_id for action in projection.available_actions]
        context = {
            "projection": projection.model_dump(mode="json", by_alias=True),
            "recentEvents": [event.model_dump(mode="json", by_alias=True) for event in events[-20:]],
            "availableActionIds": action_ids,
            "history": [turn.model_dump(mode="json", by_alias=True) for turn in request.history],
            "message": request.message,
        }
        return {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 1_200,
            "instructions": (
                "You are Ari, an operations assistant. Explain only facts grounded in the supplied "
                "run projection and events. You may recommend only action IDs in availableActionIds; "
                "never claim an action was executed. Recommend at most one action when a decision is "
                "pending. If the user asks for a new workflow step, propose one generic StepDefinition "
                "using only available state paths; otherwise proposedStep must be null. Return only the "
                "strict schema result."
            ),
            "input": json.dumps(context, separators=(",", ":")),
            "text": {"format": _strict_schema()},
        }

    @staticmethod
    def _fallback(projection: RunProjection) -> AssistResponse:
        step = projection.current_step.title if projection.current_step else "the run"
        if projection.pending_decision is not None:
            return AssistResponse(
                reply=f"{step} is waiting for a human decision. Use the available actions to continue.",
            )
        return AssistResponse(reply=f"{step} is currently {projection.status}.")

    async def respond(
        self, projection: RunProjection, events: list[RunEvent], request: AssistRequest
    ) -> AssistResponse:
        if not self.enabled:
            return self._fallback(projection)

        payload = self._payload(projection, events, request)
        for attempt in range(self.retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.request_response, payload, self.api_key, self.timeout_seconds
                    ),
                    timeout=self.timeout_seconds,
                )
                result = AssistResponse.model_validate_json(_output_text(response))
                allowed = {action.action_id for action in projection.available_actions}
                invalid = {item.action_id for item in result.recommended_actions}.difference(allowed)
                if invalid:
                    raise ValueError("assistant recommended an unavailable action")
                return result
            except Exception as exc:
                if attempt >= self.retries:
                    logger.warning("Ari assistant failed; deterministic reply returned: %s", type(exc).__name__)
                    return self._fallback(projection)
        return self._fallback(projection)
