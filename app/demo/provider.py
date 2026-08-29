"""Mock provider (paso 2.3): simula el sistema externo de logística. No hay
red real ni parsing de emails — los eventos ya vienen guionizados en
`demo/fixture.py`. Existe para que `runtime/` pueda avanzar el golden path
sin depender de ninguna integración real."""

from __future__ import annotations

from copy import deepcopy

from app.demo.fixture import DECISION_OUTCOMES, SCRIPTED_EVENTS


class MockProviderError(Exception):
    """El mock provider no tiene un evento guionizado para lo que se pidió."""


class MockProvider:
    """Devuelve, en orden, los eventos guionizados del golden path. Cada
    evento trae los `inputs` que su `StepDefinition` declara y el `verdict`
    genérico que consume `synthesis/` (nunca datos de dominio fuera de aquí
    y de `demo/fixture.py`)."""

    def __init__(self, events: list[dict] | None = None):
        self._events = events if events is not None else SCRIPTED_EVENTS

    def event_count(self) -> int:
        return len(self._events)

    def event_at(self, index: int) -> dict:
        if index < 0 or index >= len(self._events):
            raise MockProviderError(f"No hay evento guionizado en el índice {index}")
        return self._events[index]

    def event_for_step(self, step_id: str, action_id: str | None = None) -> dict:
        """Return the next scripted event, applying the accepted action when
        the execution reaches a decision-dependent step."""
        normalized_action = (action_id or "").removeprefix("act_")
        if step_id in {"route_resolution", "delivery_eta"}:
            if not normalized_action:
                raise MockProviderError(
                    f"El paso '{step_id}' requiere una decisión humana aceptada"
                )
            outcome = DECISION_OUTCOMES.get(normalized_action)
            if outcome is None:
                raise MockProviderError(f"La acción '{action_id}' no tiene resultado guionizado")
            result = outcome[step_id]
            return {
                "step_id": step_id,
                "data": deepcopy(result["data"]),
                "verdict": result["verdict"],
            }
        for event in self._events:
            if event["step_id"] == step_id:
                return deepcopy(event)
        raise MockProviderError(f"No hay evento guionizado para el paso '{step_id}'")

    def index_for_step(self, step_id: str) -> int:
        for idx, event in enumerate(self._events):
            if event["step_id"] == step_id:
                return idx
        raise MockProviderError(f"No hay evento guionizado para el paso '{step_id}'")
