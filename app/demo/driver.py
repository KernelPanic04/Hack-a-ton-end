"""Demo driver (paso 2.4): reemplaza al 'mundo real' avanzando el golden path
paso a paso. `POST /demo/advance` (Fase 2) llama a `DemoDriver.advance` una
vez por click; nada aquí sabe de HTTP ni de WS."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.provider import MockProvider, MockProviderError
from app.models.run import RunModel
from app.runtime.executor import GenericStepExecutor
from app.runtime.run import RunEngine
from app.runtime.status import StoredRunStatus


class DemoDriverError(Exception):
    """El demo driver no puede avanzar el run pedido."""


class DemoDriver:
    def __init__(self, session: AsyncSession, provider: MockProvider | None = None):
        self.session = session
        self.run_engine = RunEngine(session)
        self.provider = provider or MockProvider()

    async def start_new_run(self, *, operation_id: str | None = None) -> RunModel:
        """Bootstrap de la demo: asegura el workflow del golden path (v1) y
        arranca un run nuevo contra él."""
        workflow, version_row = await self.run_engine.flow_engine.seed_golden_path()
        flow = self.run_engine.flow_engine.to_flow_definition(version_row)
        initial_state = {"_operation_id": operation_id} if operation_id else None
        return await self.run_engine.start_run(
            workflow.id, version_row.id, flow, initial_state=initial_state
        )

    async def start_moment(self, moment: int) -> RunModel:
        """Create a separate run for M1, M2 or M3 of the same demo operation."""
        if moment not in {1, 2, 3}:
            raise DemoDriverError("El momento debe ser 1, 2 o 3")
        run = await self.start_new_run(operation_id="op_muebles_del_sur_4471")
        for _ in range(moment):
            run = await self.advance(run.id)
        return run

    async def advance(self, run_id: uuid.UUID) -> RunModel:
        """Toma el paso actual del run, busca su evento guionizado en el mock
        provider y se lo aplica al reducer. Si el run está pausado esperando
        una decisión humana o ya terminó, falla explícitamente en vez de
        saltarse o reintentar el paso — esa decisión no es del driver."""
        run = await self.run_engine.get_run(run_id)
        if run.status != StoredRunStatus.RUNNING.value:
            raise DemoDriverError(
                f"Run {run_id} no está corriendo (status={run.status}); "
                "el demo driver no avanza runs pausados o terminados"
            )
        if run.current_step_id is None:
            raise DemoDriverError(f"Run {run_id} no tiene un paso actual")

        try:
            decision = getattr(run, "state", {}).get("last_decision", {})
            event = self.provider.event_for_step(
                run.current_step_id, action_id=decision.get("action_id")
            )
        except MockProviderError as exc:
            # A step added through POST /workflows/{id}/versions has no demo
            # fixture by design. Execute it from its definition and state.
            if "evento guionizado" not in str(exc):
                raise DemoDriverError(str(exc)) from exc
            return await GenericStepExecutor(self.session, self.run_engine).execute_current(run_id)

        return await self.run_engine.advance(
            run_id,
            event["step_id"],
            event["data"],
            event["verdict"],
            pending_decision=event.get("pending_decision"),
        )
