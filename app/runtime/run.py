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
from app.runtime.status import StoredRunStatus
from app.schemas.contracts import (
    ActionDefinition,
    DecisionRequest,
    RunEvent,
    RunEventType,
    RunProjection,
    RunStepProjection,
    UISpec,
)

_PENDING_DECISION_KEY = "_pending_decision"
_UI_SPEC_KEY = "_ui_spec"
_OPERATION_ID_KEY = "_operation_id"


def _wire_id(prefix: str, value: object) -> str:
    raw = str(value)
    return raw if raw.startswith(f"{prefix}_") else f"{prefix}_{raw}"


def _projection_status(stored_status: str) -> str:
    return {
        StoredRunStatus.RUNNING.value: "running",
        StoredRunStatus.DECISION_REQUIRED.value: "paused",
        StoredRunStatus.PAUSED.value: "paused",
        StoredRunStatus.COMPLETED.value: "completed",
        StoredRunStatus.ERROR.value: "failed",
    }[stored_status]


def _action_definition(action_id: str) -> ActionDefinition:
    normalized = _wire_id("act", action_id)
    labels = {
        "act_accept_delay": "Esperar",
        "act_find_alternative": "Buscar alternativa",
        "act_notify_client": "Notificar al cliente",
    }
    return ActionDefinition(
        action_id=normalized,
        label=labels.get(normalized, normalized.removeprefix("act_").replace("_", " ").title()),
        risk="low" if normalized == "act_notify_client" else "medium",
        requires_human=True,
    )


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
        initial_state: dict[str, Any] | None = None,
    ) -> RunModel:
        first_step = flow.first_step()
        run = RunModel(
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            status=StoredRunStatus.RUNNING.value,
            current_step_id=first_step.id,
            state=initial_state or {},
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
        if run.status != StoredRunStatus.RUNNING.value:
            raise RunEngineError(f"Run {run_id} no está corriendo (status={run.status})")
        if run.current_step_id != step_id:
            raise RunEngineError(
                f"Step '{step_id}' no coincide con el paso actual '{run.current_step_id}'"
            )

        flow = await self._flow_for_run(run)
        new_state = {**run.state, step_id: {"data": data, "verdict": verdict}}
        run.state_version += 1

        if pending_decision:
            prepared_decision = {
                **pending_decision,
                "decision_id": _wire_id("dec", uuid.uuid4()),
                "step_id": _wire_id("step", step_id),
                "title": pending_decision.get("title", "Human decision required"),
                "context": pending_decision.get("context", data),
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "available_actions": [
                    _wire_id("act", action_id)
                    for action_id in pending_decision.get("available_actions", [])
                ],
            }
            new_state[_PENDING_DECISION_KEY] = prepared_decision
            run.state = new_state
            run.status = StoredRunStatus.DECISION_REQUIRED.value
            await self._append_event(
                run,
                RunEventType.DECISION_REQUIRED,
                {"step_id": step_id, "pending_decision": prepared_decision},
            )
            await self.session.commit()
            await self.session.refresh(run)
            return run

        run.state = new_state
        await self._append_event(run, RunEventType.STEP_COMPLETED, {"step_id": step_id, "data": data})

        next_step = flow.next_step(step_id)
        if next_step is None:
            run.status = StoredRunStatus.COMPLETED.value
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
        idempotency_key: str | None = None,
    ) -> RunModel:
        """Aplica una decisión humana sobre un run pausado (objetivo Rol A #3).
        Rechaza en vivo si el `stateVersion` quedó stale o la acción no está
        entre las disponibles (paso 3.4)."""
        run = await self._get_run_or_raise(run_id)
        if run.status != StoredRunStatus.DECISION_REQUIRED.value:
            raise RunEngineError(f"Run {run_id} no tiene una decisión pendiente")
        if run.current_step_id is None:
            raise RunEngineError(f"Run {run_id} no tiene un paso pendiente de revisión")

        action_id = _wire_id("act", action_id)
        reviewed_step_id = run.current_step_id

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
                payload={**payload, **({"_idempotency_key": idempotency_key} if idempotency_key else {})},
                status="accepted",
                resolved_at=datetime.now(timezone.utc),
            )
        )

        new_state = {k: v for k, v in run.state.items() if k != _PENDING_DECISION_KEY}
        new_state["last_decision"] = {"action_id": action_id, "payload": payload}
        run.state = new_state
        run.state_version += 1
        run.status = StoredRunStatus.RUNNING.value

        await self._append_event(run, RunEventType.ACTION_ACCEPTED, {"action_id": action_id, "payload": payload})
        await self._append_event(run, RunEventType.RUN_RESUMED, {"action_id": action_id})

        reviewed_step = new_state.get(reviewed_step_id, {})
        reviewed_data = (
            reviewed_step.get("data", {}) if isinstance(reviewed_step, dict) else {}
        )
        await self._append_event(
            run,
            RunEventType.STEP_COMPLETED,
            {"step_id": reviewed_step_id, "data": reviewed_data},
        )

        flow = await self._flow_for_run(run)
        next_step = flow.next_step(reviewed_step_id)
        if next_step is None:
            run.status = StoredRunStatus.COMPLETED.value
            run.current_step_id = None
            await self._append_event(run, RunEventType.RUN_COMPLETED, {})
        else:
            run.current_step_id = next_step.id
            await self._append_event(run, RunEventType.STEP_STARTED, {"step_id": next_step.id})

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def record_action_rejection(
        self, run_id: uuid.UUID, action_id: str, reason: str
    ) -> RunEvent:
        """Append a policy rejection without mutating the runtime state."""
        run = await self._get_run_or_raise(run_id)
        await self._append_event(
            run,
            RunEventType.ACTION_REJECTED,
            {"action_id": _wire_id("act", action_id), "reason": reason},
        )
        await self.session.commit()
        return (await self.get_event_log(run.id))[-1]

    async def get_projection(self, run_id: uuid.UUID) -> RunProjection:
        run = await self._get_run_or_raise(run_id)
        version_row = await self.flow_engine.get_version_by_id(run.workflow_version_id)
        if version_row is None:
            raise RunEngineError(f"WorkflowVersion {run.workflow_version_id} no existe")

        flow = self.flow_engine.to_flow_definition(version_row)
        pending = (
            run.state.get(_PENDING_DECISION_KEY)
            if run.status == StoredRunStatus.DECISION_REQUIRED.value
            else None
        )
        available_actions = [
            _action_definition(action_id)
            for action_id in (pending or {}).get("available_actions", [])
        ]
        wire_run_id = _wire_id("run", run.id)
        wire_workflow_id = _wire_id("wf", run.workflow_id)

        event_rows = await self.export_events(run.id)
        recent_events = self._to_contract_events(
            event_rows, wire_run_id, wire_workflow_id, version_row.version
        )

        current_step = None
        if run.current_step_id is not None:
            step = flow.step_by_id(run.current_step_id)
            if step is None:
                raise RunEngineError(
                    f"Step {run.current_step_id} no existe en WorkflowVersion "
                    f"{run.workflow_version_id}"
                )
            current_step = RunStepProjection(
                id=_wire_id("step", step.id),
                type=step.type,
                title=step.title,
                objective=step.objective,
                status=(
                    "attention"
                    if run.status == StoredRunStatus.DECISION_REQUIRED.value
                    else "active"
                ),
                metadata={
                    "inputs": step.inputs,
                    "requiresHumanReview": step.requires_human_review,
                },
            )

        pending_request = None
        if pending:
            pending_request = DecisionRequest(
                decision_id=_wire_id(
                    "dec", pending.get("decision_id", f"{run.id}-{run.state_version}")
                ),
                step_id=_wire_id(
                    "step", pending.get("step_id", run.current_step_id or "unknown")
                ),
                title=pending.get("title", "Human decision required"),
                prompt=pending["prompt"],
                context=pending.get("context", {}),
                requested_at=pending.get("requested_at", run.updated_at),
            )

        return RunProjection(
            run_id=wire_run_id,
            operation_id=run.state.get(_OPERATION_ID_KEY),
            workflow_id=wire_workflow_id,
            workflow_version=version_row.version,
            state_version=run.state_version,
            last_sequence=len(event_rows),
            status=_projection_status(run.status),
            current_step=current_step,
            operation={
                key: value
                for key, value in run.state.items()
                if key not in {_PENDING_DECISION_KEY, _UI_SPEC_KEY, _OPERATION_ID_KEY}
            },
            recent_events=recent_events[-50:],
            pending_decision=pending_request,
            available_actions=available_actions,
        )

    async def save_ui_spec(self, run_id: uuid.UUID, ui_spec: UISpec) -> RunEvent:
        """Persist the latest generated UI and record its delivery event.

        The UI has the same state version as the projection that generated it;
        persisting it inside the run's JSON state keeps this Phase 2 addition
        migration-free while the shared snapshot contract remains frozen.
        """
        run = await self._get_run_or_raise(run_id)
        expected_run_id = _wire_id("run", run.id)
        if ui_spec.run_id != expected_run_id:
            raise RunEngineError("uiSpec no pertenece al run indicado")

        run.state = {
            **run.state,
            _UI_SPEC_KEY: ui_spec.model_dump(mode="json"),
        }
        await self._append_event(run, RunEventType.UI_UPDATED, {"generated_by": ui_spec.generated_by})
        await self.session.commit()
        await self.session.refresh(run)
        return (await self.get_event_log(run.id))[-1]

    async def get_last_ui_spec(self, run_id: uuid.UUID) -> UISpec | None:
        """Return the persisted deterministic snapshot when one exists."""
        run = await self._get_run_or_raise(run_id)
        stored = run.state.get(_UI_SPEC_KEY)
        return UISpec.model_validate(stored) if stored is not None else None

    async def get_run(self, run_id: uuid.UUID) -> RunModel:
        return await self._get_run_or_raise(run_id)

    async def export_events(self, run_id: uuid.UUID) -> list[RunEventModel]:
        """Event log completo de un run, en orden — usado por GET
        /runs/{id}/events (paso 4.7) para el export de la defensa."""
        result = await self.session.execute(
            select(RunEventModel).where(RunEventModel.run_id == run_id).order_by(RunEventModel.created_at)
        )
        return list(result.scalars().all())

    async def get_event_log(self, run_id: uuid.UUID) -> list[RunEvent]:
        """Exporta el log completo con el contrato wire de ``RunEvent``.

        A diferencia de ``RunProjection.recent_events``, esta lista no se
        recorta a 50 entradas y por eso es la fuente de ``GET /runs/{id}/events``.
        """
        run = await self._get_run_or_raise(run_id)
        version_row = await self.flow_engine.get_version_by_id(run.workflow_version_id)
        if version_row is None:
            raise RunEngineError(f"WorkflowVersion {run.workflow_version_id} no existe")
        rows = await self.export_events(run.id)
        return self._to_contract_events(
            rows,
            _wire_id("run", run.id),
            _wire_id("wf", run.workflow_id),
            version_row.version,
        )

    async def record_action_rejection(
        self,
        run_id: uuid.UUID,
        action_id: str,
        reason: str,
    ) -> RunEvent:
        """Registra un rechazo de transporte/policy que no muta la proyección.

        ``resolve_decision`` conserva sus validaciones de dominio. Este método
        cubre rechazos previos (decisionId ajeno, payload no objeto, versiones
        incompatibles) para que incluso el camino negativo sea append-only.
        """
        run = await self._get_run_or_raise(run_id)
        await self._append_event(
            run,
            RunEventType.ACTION_REJECTED,
            {"action_id": _wire_id("act", action_id), "reason": reason},
        )
        await self.session.commit()
        return (await self.get_event_log(run.id))[-1]

    async def latest_event(
        self,
        run_id: uuid.UUID,
        event_type: RunEventType,
    ) -> RunEvent | None:
        """Devuelve el último evento wire de un tipo para construir envelopes."""
        events = await self.get_event_log(run_id)
        return next((event for event in reversed(events) if event.type == event_type.value), None)

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

    @staticmethod
    def _to_contract_events(
        rows: list[RunEventModel],
        wire_run_id: str,
        wire_workflow_id: str,
        workflow_version: int,
    ) -> list[RunEvent]:
        return [
            RunEvent(
                event_id=_wire_id("evt", row.id),
                run_id=wire_run_id,
                workflow_id=wire_workflow_id,
                workflow_version=workflow_version,
                sequence=sequence,
                state_version=row.state_version,
                type=row.type,
                step_id=(
                    _wire_id("step", row.payload["step_id"])
                    if isinstance(row.payload, dict) and row.payload.get("step_id")
                    else None
                ),
                payload=row.payload,
                timestamp=row.created_at,
            )
            for sequence, row in enumerate(rows, start=1)
        ]

    async def _append_event(self, run: RunModel, event_type: RunEventType, payload: dict[str, Any]) -> None:
        self.session.add(
            RunEventModel(
                run_id=run.id,
                type=event_type.value,
                payload=payload,
                state_version=run.state_version,
            )
        )
