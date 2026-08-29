"""Demo driver (paso 2.4): reemplaza al 'mundo real' avanzando el golden path
paso a paso. `POST /demo/advance` (Fase 2) llama a `DemoDriver.advance` una
vez por click; nada aquí sabe de HTTP ni de WS."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.provider import MockProvider, MockProviderError
from app.models.run import RunModel
from app.runtime.run import RunEngine
from app.runtime.status import StoredRunStatus


class DemoDriverError(Exception):
    """El demo driver no puede avanzar el run pedido."""


class DemoDriver:
    def __init__(self, session: AsyncSession, provider: MockProvider | None = None):
        self.session = session
        self.run_engine = RunEngine(session)
        self.provider = provider or MockProvider()

    async def start_new_run(self) -> RunModel:
        """Bootstrap de la demo: asegura el workflow del golden path (v1) y
        arranca un run nuevo contra él."""
        workflow, version_row = await self.run_engine.flow_engine.seed_golden_path()
        flow = self.run_engine.flow_engine.to_flow_definition(version_row)
        return await self.run_engine.start_run(workflow.id, version_row.id, flow)

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
            event = self.provider.event_for_step(run.current_step_id)
        except MockProviderError as exc:
            raise DemoDriverError(str(exc)) from exc

        return await self.run_engine.advance(
            run_id,
            event["step_id"],
            event["data"],
            event["verdict"],
            pending_decision=event.get("pending_decision"),
        )
