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

from app.schemas.contracts import AlertNode, AlertProps, AssistMessage
from app.synthesis.llm import DEFAULT_MODEL, ResponseRequest, _output_text, _request_response
from app.synthesis.llm_upgrade import describe_failure
from app.studio.schema import (
    StudioLLMOutput,
    StudioOrchestration,
    StudioPageNode,
    StudioPageProps,
    StudioUISpec,
    TextNode,
    TextProps,
)
from app.studio.store import StoredFeedback


# Graduated reasoning effort by recent average score (1-5): the worse the
# recent ratings, the more reasoning budget the next generation gets. Each
# tuple is (exclusive upper bound on the recent average, effort); the list is
# checked low-to-high and the first bound the average falls under wins. A
# missing average (no feedback yet) or one at/above the top bound gets
# DEFAULT_REASONING_EFFORT.
REASONING_EFFORT_BY_SCORE: tuple[tuple[float, str], ...] = (
    (2.0, "high"),
    (3.0, "medium"),
    (4.0, "low"),
)
DEFAULT_REASONING_EFFORT = "none"

# The recent-average boundary below which the model is asked for any extra
# reasoning effort at all (named constant kept for readability/tests).
LOW_RATING_THRESHOLD = 4.0

# Ratings at or below this score are quoted back to the model verbatim so it
# fixes the specific complaint on the next generation, not just the trend.
LOW_SCORE_COMMENT_THRESHOLD = 2


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


def _reasoning_effort(average_score: float | None) -> str:
    """Map a recent-feedback average (1-5) to a provider reasoning effort.

    Graduated rather than binary: a mildly disappointing project nudges the
    model up one notch, a badly rated one asks for its deepest reasoning. No
    feedback, or a healthy average, costs no extra reasoning at all.
    """

    if average_score is None:
        return DEFAULT_REASONING_EFFORT
    for upper_bound, effort in REASONING_EFFORT_BY_SCORE:
        if average_score < upper_bound:
            return effort
    return DEFAULT_REASONING_EFFORT


def blank_studio_spec(
    reason: str, orchestration: StudioOrchestration | None = None
) -> StudioUISpec:
    return StudioUISpec(
        generated_by="fallback",
        reason=reason,
        orchestration=orchestration,
        layout=StudioPageNode(
            id="ui_page",
            type="page",
            props=StudioPageProps(title="Interfaz no disponible"),
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


# Node types that make a layout an actual interface rather than prose. A
# general question ("¿cómo son los edificios?") comes back as a page of text
# nodes with no controls — that absence is the signal it is not a design.
UI_NODE_TYPES = frozenset(
    {
        "button",
        "metric",
        "alert",
        "timeline",
        "keyValue",
        "compare",
        "step",
        "map",
        "searchBar",
        "dropdown",
        "chart",
        "table",
        "progress",
        "tags",
    }
)


def _carries_ui(node: Any) -> bool:
    if getattr(node, "type", None) in UI_NODE_TYPES:
        return True
    for child in getattr(node, "children", None) or []:
        if _carries_ui(child):
            return True
    return False


def guidance_studio_spec(orchestration: StudioOrchestration | None = None) -> StudioUISpec:
    """Response for a prompt that reads as a question, not a UI request.

    The model still emits a (text-only) layout because the schema requires one;
    rather than present prose as a "design", the request is turned around with
    an actionable example of how to ask for an interface instead.
    """

    return StudioUISpec(
        generated_by="guidance",
        reason=(
            "Esto parece una pregunta general, no una petición de interfaz. "
            "Studio construye UIs (botones, tarjetas, secciones…) a partir de "
            "tu descripción."
        ),
        suggestion=(
            "Reformúlalo como una interfaz. Por ejemplo: “crea una tarjeta con "
            "un título, una imagen y tres puntos clave que expliquen el tema”."
        ),
        orchestration=orchestration,
        layout=StudioPageNode(
            id="ui_page",
            type="page",
            props=StudioPageProps(title="Pídelo como una interfaz"),
            children=[
                AlertNode(
                    id="ui_guidance",
                    type="alert",
                    props=AlertProps(
                        title="Esto parece una pregunta, no una interfaz",
                        message=(
                            "Studio genera interfaces, no respuestas de texto. "
                            "Describe la UI que quieres y la construyo."
                        ),
                        emphasis="warning",
                    ),
                ),
                TextNode(
                    id="ui_guidance_example",
                    type="text",
                    props=TextProps(
                        content=(
                            "Ejemplo: “crea una tarjeta con título, imagen y tres "
                            "puntos clave sobre los edificios”."
                        ),
                        variant="caption",
                    ),
                ),
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
            "to point out; do not restate reason there. Beyond basic cards "
            "and text, use searchBar for a search input, dropdown for a "
            "single-select control, table for tabular data, progress for a "
            "single 0-100 meter, tags for a list of short labels/badges, and "
            "chart (bar, line or pie) for any numeric series or comparison "
            "the prompt describes — prefer chart over a wall of metric "
            "nodes when the request is really asking to visualize data. "
            "page, section, button, text, progress, each tags item and each "
            "chart point accept an optional hex color (e.g. \"#3366ff\", "
            "backgroundColor on page/section, color elsewhere). Whenever the "
            "prompt asks to recolor the whole UI, a container, or one "
            "specific element, set that field to a concrete hex value on "
            "the exact node(s) it refers to — never describe a color change "
            "in reason without also setting the color prop that makes it "
            "real. Leave color null when the request does not mention "
            "color; do not recolor things it didn't ask about. searchBar "
            "and dropdown can be wired to actually filter a table or tags "
            "node in the same layout: set filterTarget to that node's id "
            "and the browser live-filters it client-side as the user types "
            "or picks an option — no backend call happens. Use this "
            "whenever the prompt asks for a search box or filter that "
            "should affect a table/tags also present in the layout (build "
            "the table/tags first so an id exists to reference). On "
            "dropdown, also set filterColumn to the exact table column "
            "header it should match when the request implies one category "
            "per column (e.g. a \"status\" or \"category\" column); leave "
            "filterColumn null to match the selected option against any "
            "cell. Leave filterTarget null when the prompt does not ask "
            "for filtering, or when there is no table/tags to filter. A "
            "wired dropdown's own placeholder already means \"no filter, "
            "show every row\" once selected back — never add your own "
            "catch-all option for that (e.g. \"all\"/\"todos\"), it would "
            "instead be matched as a literal value and hide every row."
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
            low_score_complaints = [
                entry.comment.strip()
                for entry in feedback
                if entry.score <= LOW_SCORE_COMMENT_THRESHOLD
                and entry.comment
                and entry.comment.strip()
            ]
            if low_score_complaints:
                quoted = "; ".join(f'"{c}"' for c in low_score_complaints)
                instructions += (
                    " The lowest-rated past generations specifically complained: "
                    f"{quoted}. Treat each as a concrete defect to fix in this "
                    "generation, not just a soft preference."
                )
        effort = _reasoning_effort(average_score)
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
        history = history or []
        feedback = feedback or []
        average = _average_score(feedback)
        orchestration = StudioOrchestration(
            reasoning_effort=_reasoning_effort(average),
            feedback_average=round(average, 2) if average is not None else None,
            feedback_count=len(feedback),
            history_turns=len(history),
            used_previous_layout=previous_layout is not None,
        )

        if not self.enabled:
            return blank_studio_spec(
                "La generación de UI por prompt está deshabilitada.", orchestration
            )

        payload = self._payload(prompt, history, previous_layout, feedback)
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
                if not _carries_ui(output.layout):
                    return guidance_studio_spec(orchestration)
                return StudioUISpec(
                    generated_by="llm",
                    reason=output.reason,
                    suggestion=output.suggestion,
                    orchestration=orchestration,
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
                        f"intentos ({describe_failure(last_error)}).",
                        orchestration,
                    )
        return blank_studio_spec(
            f"No se pudo generar la interfaz solicitada tras {self.retries + 1} "
            f"intentos ({describe_failure(last_error)}).",
            orchestration,
        )
