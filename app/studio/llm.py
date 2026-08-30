"""Generate a Studio UI layout from a free-text prompt.

No ``RunProjection`` is involved: this is a standalone, one-shot LLM call.
There is no deterministic equivalent to fall back to (a fixed layout cannot
stand in for an arbitrary prompt), so failure falls straight to a blank
placeholder carrying the real error, using the same retry-then-blank pattern
as the run composer (see ``app/synthesis/llm.py``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from app.schemas.contracts import AlertNode, AlertProps, AssistMessage, PageProps
from app.synthesis.llm import DEFAULT_MODEL, ResponseRequest, _output_text, _request_response
from app.synthesis.llm_upgrade import describe_failure
from app.studio.schema import StudioLLMOutput, StudioPageNode, StudioUISpec
from app.studio.store import StoredFeedback


LOW_RATING_THRESHOLD = 3.0
"""Average of the 1-5 ``StoredFeedback`` scores below which the model is
asked to spend more reasoning effort on the next generation."""


logger = logging.getLogger(__name__)


def _strict_output_schema() -> dict[str, Any]:
    schema = StudioLLMOutput.model_json_schema(by_alias=True)

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
        "name": "studio_ui_generation",
        "strict": True,
        "schema": schema,
    }


def _average_score(feedback: list[StoredFeedback]) -> float | None:
    if not feedback:
        return None
    return sum(entry.score for entry in feedback) / len(feedback)


def blank_studio_spec(reason: str) -> StudioUISpec:
    return StudioUISpec(
        generated_by="fallback",
        reason=reason,
        layout=StudioPageNode(
            id="ui_page",
            type="page",
            props=PageProps(title="Interfaz no disponible"),
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
    )


class StudioUIGenerator:
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
            else float(os.getenv("STUDIO_GENERATION_TIMEOUT_SECONDS", "12"))
        )
        self.retries = retries
        self.request_response = request_response
        configured_enabled = (
            enabled
            if enabled is not None
            else os.getenv("STUDIO_GENERATION_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"}
        )
        self.enabled = bool(self.api_key) and configured_enabled

    def _payload(
        self,
        prompt: str,
        history: list[AssistMessage],
        previous_layout: StudioPageNode | None,
        feedback: list[StoredFeedback],
    ) -> dict[str, Any]:
        input_payload: dict[str, Any] = {
            "prompt": prompt,
            "history": [turn.model_dump(mode="json", by_alias=True) for turn in history],
        }
        if previous_layout is not None:
            input_payload["previousLayout"] = previous_layout.model_dump(
                mode="json", by_alias=True
            )
        instructions = (
            "Build a declarative UI layout for the user's free-text request. "
            "Use only node types and props permitted by the output schema; "
            "never invent one. Interpret layout instructions (grouping, "
            "side-by-side, stacked, spacing) using the section node's "
            "direction/gap/align/justify props. If previousLayout is present, "
            "treat the newest prompt as an edit/refinement of it — reuse its "
            "node ids and content where the request doesn't change them — "
            "using history only for conversational context; otherwise build "
            "fresh. Keep labels concise and explain your interpretation of "
            "the request in reason. Separately, if the prompt's request "
            "implies a layout or UX pattern that is usually suboptimal (e.g. "
            "stacking a pair of related actions instead of pairing them "
            "side by side), set suggestion to one short, actionable tip "
            "about that — talk to the user, not about the JSON you produced. "
            "Leave suggestion null when the request has no such improvement "
            "to point out; do not restate reason there."
        )
        average_score = _average_score(feedback)
        if feedback:
            input_payload["feedbackHistory"] = [
                {"score": entry.score, "comment": entry.comment} for entry in feedback
            ]
            instructions += (
                " feedbackHistory holds this project's most recent 1-5 ratings "
                "(and optional comments) of past generations, oldest first. "
                "Favor layout choices similar to what earned high scores and "
                "avoid whatever low-scored comments called out."
            )
        effort = "low" if average_score is not None and average_score < LOW_RATING_THRESHOLD else "none"
        return {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": effort},
            "max_output_tokens": 2400,
            "instructions": instructions,
            "input": json.dumps(input_payload, separators=(",", ":")),
            "text": {"format": _strict_output_schema()},
        }

    async def generate(
        self,
        prompt: str,
        *,
        history: list[AssistMessage] | None = None,
        previous_layout: StudioPageNode | None = None,
        feedback: list[StoredFeedback] | None = None,
    ) -> StudioUISpec:
        if not self.enabled:
            return blank_studio_spec("La generación de UI por prompt está deshabilitada.")

        payload = self._payload(prompt, history or [], previous_layout, feedback or [])
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
                output = StudioLLMOutput.model_validate_json(_output_text(response))
                return StudioUISpec(
                    generated_by="llm",
                    reason=output.reason,
                    suggestion=output.suggestion,
                    layout=output.layout,
                )
            except Exception as exc:  # provider, timeout and schema failures all fall back
                last_error = exc
                if attempt >= self.retries:
                    logger.warning(
                        "Studio UI generation failed after %s attempts; showing blank fallback: %s",
                        self.retries + 1,
                        type(exc).__name__,
                    )
                    return blank_studio_spec(
                        f"No se pudo generar la interfaz solicitada tras {self.retries + 1} "
                        f"intentos ({describe_failure(last_error)})."
                    )
        return blank_studio_spec(
            f"No se pudo generar la interfaz solicitada tras {self.retries + 1} "
            f"intentos ({describe_failure(last_error)})."
        )
