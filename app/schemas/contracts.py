"""Contratos compartidos del runtime (RunProjection, UISpec, ActionEvent, RunEvent, envelope WS).

BORRADOR DE TRABAJO — el roadmap (CLAUDE.md, paso 0.1) asigna el congelamiento
formal de estos contratos a Rol D, con firma de los cuatro roles antes de H1.
Este módulo existe para no bloquear a Rol A mientras eso ocurre (regla: "si una
dependencia no llega, se mockea y se sigue"). No debe tratarse como definitivo.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    RUNNING = "running"
    DECISION_REQUIRED = "decision_required"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class UISpec(BaseModel):
    """Nodo del árbol de UI generado por synthesis/. Recursivo: un `page`
    contiene `section`s, que contienen componentes del registry."""

    type: str
    props: dict[str, Any] = Field(default_factory=dict)
    children: list["UISpec"] = Field(default_factory=list)
    generated_by: Literal["deterministic", "llm"] = "deterministic"
    reason: str | None = None
    state_version: int = 0


class PendingDecision(BaseModel):
    prompt: str
    available_actions: list[str] = Field(default_factory=list)


class RunProjection(BaseModel):
    """Snapshot completo de un run: lo que sirve tanto para el push por WS
    como para GET /runs/{id}/projection (reconexión y polling)."""

    run_id: UUID
    workflow_id: UUID
    workflow_version: int
    status: RunStatus
    current_step_id: str | None
    state: dict[str, Any] = Field(default_factory=dict)
    pending_decision: PendingDecision | None = None
    available_actions: list[str] = Field(default_factory=list)
    state_version: int
    ui: UISpec | None = None
    updated_at: datetime


class ActionEvent(BaseModel):
    """Acción humana enviada desde el frontend. Sin `eventId` de cliente:
    el idempotencyKey y el id del evento los genera/valida el backend."""

    run_id: UUID
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state_version: int
    idempotency_key: str


class RunEventType(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    UI_UPDATED = "UI_UPDATED"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    ACTION_ACCEPTED = "ACTION_ACCEPTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    RUN_PAUSED = "RUN_PAUSED"
    RUN_RESUMED = "RUN_RESUMED"
    RUN_COMPLETED = "RUN_COMPLETED"
    WORKFLOW_VERSION_CREATED = "WORKFLOW_VERSION_CREATED"
    ERROR = "ERROR"


class RunEvent(BaseModel):
    """Entrada append-only del event log (persistida en run_events)."""

    id: UUID
    run_id: UUID
    type: RunEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    state_version: int
    created_at: datetime


class WSEnvelope(BaseModel):
    """Mensaje tipado del hub WebSocket (ws/hub.py, propiedad de Rol D)."""

    type: RunEventType
    run_id: UUID
    state_version: int
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
