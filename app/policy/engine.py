"""Declarative validation for human runtime actions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import HumanDecisionModel
from app.runtime.run import RunEngine
from app.schemas.contracts import ActionEvent, RunProjection


@dataclass(frozen=True)
class ActionPolicy:
    risk: str
    requires_human: bool
    payload_schema: dict[str, Any]


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "act_find_alternative": ActionPolicy(
        risk="medium",
        requires_human=True,
        payload_schema={"type": "object", "additionalProperties": False},
    ),
    "act_accept_delay": ActionPolicy(
        risk="medium",
        requires_human=True,
        payload_schema={"type": "object", "additionalProperties": False},
    ),
    "act_acknowledge": ActionPolicy(
        risk="low",
        requires_human=True,
        payload_schema={"type": "object", "additionalProperties": False},
    ),
}


class PolicyViolation(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ActionPolicyEngine:
    """Validate immutable wire events before the runtime changes a run."""

    def __init__(self, session: AsyncSession, run_engine: RunEngine | None = None) -> None:
        self.session = session
        self.run_engine = run_engine or RunEngine(session)

    async def validate(self, event: ActionEvent, run_id: uuid.UUID) -> RunProjection:
        projection = await self.run_engine.get_projection(run_id)
        if event.run_id != projection.run_id:
            raise PolicyViolation("RUN_MISMATCH", "La acción no pertenece al run del socket.")
        if event.workflow_version != projection.workflow_version:
            raise PolicyViolation("WORKFLOW_VERSION_MISMATCH", "La versión del workflow no coincide.")
        if await self._idempotency_used(run_id, event.idempotency_key):
            raise PolicyViolation("IDEMPOTENCY_REPLAY", "Esta acción ya fue procesada.")
        if event.state_version != projection.state_version:
            raise PolicyViolation("STALE_STATE_VERSION", "El estado cambió; actualiza la interfaz.")
        if projection.pending_decision is None:
            raise PolicyViolation("NO_PENDING_DECISION", "El run no tiene una decisión pendiente.")
        if event.decision_id != projection.pending_decision.decision_id:
            raise PolicyViolation("DECISION_MISMATCH", "La decisión ya no está vigente.")

        policy = ACTION_POLICIES.get(event.action_id)
        if policy is None:
            raise PolicyViolation("ACTION_UNKNOWN", "La acción solicitada no está registrada.")
        if event.action_id not in {item.action_id for item in projection.available_actions}:
            raise PolicyViolation("ACTION_NOT_AVAILABLE", "La acción no está disponible para esta decisión.")
        if not self._matches_schema(event.payload, policy.payload_schema):
            raise PolicyViolation("PAYLOAD_INVALID", "El payload no cumple el schema de la acción.")
        return projection

    @staticmethod
    def _matches_schema(payload: Any, schema: dict[str, Any]) -> bool:
        """Valida el subconjunto JSON Schema usado por las acciones P0."""
        if schema.get("type") != "object" or not isinstance(payload, dict):
            return False
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if any(key not in payload for key in required):
            return False
        if schema.get("additionalProperties") is False:
            return all(key in properties for key in payload)
        return True

    async def _idempotency_used(self, run_id: uuid.UUID, key: str) -> bool:
        result = await self.session.execute(
            select(HumanDecisionModel.payload).where(HumanDecisionModel.run_id == run_id)
        )
        return any(
            isinstance(payload, dict) and payload.get("_idempotency_key") == key
            for payload in result.scalars()
        )
