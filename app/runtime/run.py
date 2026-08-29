"""Reducer del run (objetivos Rol A #2, #3, #5): aplica transiciones, persiste
el estado en `runs` y deja un RunEvent append-only por cada una. El paso
guionizado o el generic step executor (Fase 4) llaman a `advance`; una
decisión humana llama a `resolve_decision`.

La validación de policy (token, run activo, idempotencyKey) es de
`policy/engine.py` (Rol D, paso 3.3). Aquí solo se valida consistencia de
dominio: el run está en el estado correcto, el paso coincide, la acción está
entre las disponibles y el `stateVersion` sigue vigente.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flow.engine import FlowEngine
from app.flow.models import FlowDefinition
from app.models.run import HumanDecisionModel, RunEventModel, RunModel
from app.schemas.contracts import PendingDecision, RunEventType, RunProjection, RunStatus

_PENDING_DECISION_KEY = "_pending_decision"


class RunEngineError(Exception):
    """Error de dominio del runtime (run inexistente, transición inválida, acción rechazada)."""


class RunEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.flow_engine = FlowEngine(session)

    async def start_run(
        self,
        workflow_id: uuid.UUID,
        workflow_version_id: uuid.UUID,
        flow: FlowDefinition,
    ) -> RunModel:
        first_step = flow.first_step()
        run = RunModel(
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            status=RunStatus.RUNNING.value,
            current_step_id=first_step.id,
            state={},
            state_version=0,
        )
        self.session.add(run)
        await self.session.flush()
        await self._append_event(run, RunEventType.RUN_STARTED, {"step_id": first_step.id})
        await self._append_event(run, RunEventType.STEP_STARTED, {"step_id": first_step.id})
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def advance(
        self,
        run_id: uuid.UUID,
        step_id: str,
        data: dict[str, Any],
        verdict: str,
        pending_decision: dict[str, Any] | None = None,
    ) -> RunModel:
        """Aplica el resultado de un paso (guionizado por demo/driver.py, o
        producido por el generic step executor en Fase 4) sobre el paso
        actual del run."""
        run = await self._get_run_or_raise(run_id)
        if run.status != RunStatus.RUNNING.value:
            raise RunEngineError(f"Run {run_id} no está corriendo (status={run.status})")
        if run.current_step_id != step_id:
            raise RunEngineError(
                f"Step '{step_id}' no coincide con el paso actual '{run.current_step_id}'"
            )

        flow = await self._flow_for_run(run)
        new_state = {**run.state, step_id: {"data": data, "verdict": verdict}}
        run.state_version += 1

        if pending_decision:
            new_state[_PENDING_DECISION_KEY] = pending_decision
            run.state = new_state
            run.status = RunStatus.DECISION_REQUIRED.value
            await self._append_event(
                run,
                RunEventType.DECISION_REQUIRED,
                {"step_id": step_id, "pending_decision": pending_decision},
            )
            await self.session.commit()
            await self.session.refresh(run)
            return run

        run.state = new_state
        await self._append_event(run, RunEventType.STEP_COMPLETED, {"step_id": step_id, "data": data})

        next_step = flow.next_step(step_id)
        if next_step is None:
            run.status = RunStatus.COMPLETED.value
            run.current_step_id = None
            await self._append_event(run, RunEventType.RUN_COMPLETED, {})
        else:
            run.current_step_id = next_step.id
            await self._append_event(run, RunEventType.STEP_STARTED, {"step_id": next_step.id})

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def resolve_decision(
        self,
        run_id: uuid.UUID,
        action_id: str,
        payload: dict[str, Any],
        state_version: int,
    ) -> RunModel:
        """Aplica una decisión humana sobre un run pausado (objetivo Rol A #3).
        Rechaza en vivo si el `stateVersion` quedó stale o la acción no está
        entre las disponibles (paso 3.4)."""
        run = await self._get_run_or_raise(run_id)
        if run.status != RunStatus.DECISION_REQUIRED.value:
            raise RunEngineError(f"Run {run_id} no tiene una decisión pendiente")

        if run.state_version != state_version:
            await self._append_event(
                run,
                RunEventType.ACTION_REJECTED,
                {"action_id": action_id, "reason": "stale_state_version"},
            )
            await self.session.commit()
            raise RunEngineError("stateVersion desactualizado: la decisión se rechaza")

        pending = run.state.get(_PENDING_DECISION_KEY) or {}
        available_actions = pending.get("available_actions", [])
        if action_id not in available_actions:
            await self._append_event(
                run,
                RunEventType.ACTION_REJECTED,
                {"action_id": action_id, "reason": "action_not_available"},
            )
            await self.session.commit()
            raise RunEngineError(f"Acción '{action_id}' no disponible para este run")

        self.session.add(
            HumanDecisionModel(
                run_id=run.id,
                action_id=action_id,
                payload=payload,
                status="accepted",
                resolved_at=datetime.now(timezone.utc),
            )
        )

        new_state = {k: v for k, v in run.state.items() if k != _PENDING_DECISION_KEY}
        new_state["last_decision"] = {"action_id": action_id, "payload": payload}
        run.state = new_state
        run.state_version += 1
        run.status = RunStatus.RUNNING.value

        await self._append_event(run, RunEventType.ACTION_ACCEPTED, {"action_id": action_id, "payload": payload})
        await self._append_event(run, RunEventType.RUN_RESUMED, {"action_id": action_id})

        flow = await self._flow_for_run(run)
        next_step = flow.next_step(run.current_step_id)
        if next_step is not None:
            run.current_step_id = next_step.id
            await self._append_event(run, RunEventType.STEP_STARTED, {"step_id": next_step.id})

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_projection(self, run_id: uuid.UUID) -> RunProjection:
        run = await self._get_run_or_raise(run_id)
        version_row = await self.flow_engine.get_version_by_id(run.workflow_version_id)
        pending = run.state.get(_PENDING_DECISION_KEY) if run.status == RunStatus.DECISION_REQUIRED.value else None
        return RunProjection(
            run_id=run.id,
            workflow_id=run.workflow_id,
            workflow_version=version_row.version if version_row else 0,
            status=RunStatus(run.status),
            current_step_id=run.current_step_id,
            state={k: v for k, v in run.state.items() if k != _PENDING_DECISION_KEY},
            pending_decision=PendingDecision(**pending) if pending else None,
            available_actions=(pending or {}).get("available_actions", []),
            state_version=run.state_version,
            ui=None,
            updated_at=run.updated_at,
        )

    async def get_run(self, run_id: uuid.UUID) -> RunModel:
        return await self._get_run_or_raise(run_id)

    async def export_events(self, run_id: uuid.UUID) -> list[RunEventModel]:
        """Event log completo de un run, en orden — usado por GET
        /runs/{id}/events (paso 4.7) para el export de la defensa."""
        result = await self.session.execute(
            select(RunEventModel).where(RunEventModel.run_id == run_id).order_by(RunEventModel.created_at)
        )
        return list(result.scalars().all())

    async def _get_run_or_raise(self, run_id: uuid.UUID) -> RunModel:
        run = await self.session.get(RunModel, run_id)
        if run is None:
            raise RunEngineError(f"Run {run_id} no existe")
        return run

    async def _flow_for_run(self, run: RunModel) -> FlowDefinition:
        version_row = await self.flow_engine.get_version_by_id(run.workflow_version_id)
        if version_row is None:
            raise RunEngineError(f"WorkflowVersion {run.workflow_version_id} no existe")
        return self.flow_engine.to_flow_definition(version_row)

    async def _append_event(self, run: RunModel, event_type: RunEventType, payload: dict[str, Any]) -> None:
        self.session.add(
            RunEventModel(
                run_id=run.id,
                type=event_type.value,
                payload=payload,
                state_version=run.state_version,
            )
        )
