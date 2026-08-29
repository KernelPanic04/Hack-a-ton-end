"""Motor de workflow: crea y lee versiones (objetivo Rol A #1). Crear una
v(n+1) es siempre un insert nuevo — nunca se muta una versión existente — así
que queda disponible para el próximo run sin reiniciar el proceso (gate H13/H17,
paso 4.1 en Fase 4)."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flow.models import FlowDefinition, StepDefinition
from app.models.workflow import WorkflowDefinitionModel, WorkflowVersionModel


class FlowEngine:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_workflow(self, name: str) -> WorkflowDefinitionModel:
        result = await self.session.execute(
            select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.name == name)
        )
        workflow = result.scalars().first()
        if workflow:
            return workflow
        workflow = WorkflowDefinitionModel(name=name)
        self.session.add(workflow)
        await self.session.commit()
        await self.session.refresh(workflow)
        return workflow

    async def create_version(
        self, workflow_id: uuid.UUID, steps: Sequence[StepDefinition]
    ) -> WorkflowVersionModel:
        next_version = await self._next_version_number(workflow_id)
        version_row = WorkflowVersionModel(
            workflow_id=workflow_id,
            version=next_version,
            steps=[step.model_dump() for step in steps],
        )
        self.session.add(version_row)
        await self.session.commit()
        await self.session.refresh(version_row)
        return version_row

    async def get_latest_version(self, workflow_id: uuid.UUID) -> WorkflowVersionModel | None:
        result = await self.session.execute(
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == workflow_id)
            .order_by(WorkflowVersionModel.version.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_version(self, workflow_id: uuid.UUID, version: int) -> WorkflowVersionModel | None:
        result = await self.session.execute(
            select(WorkflowVersionModel).where(
                WorkflowVersionModel.workflow_id == workflow_id,
                WorkflowVersionModel.version == version,
            )
        )
        return result.scalars().first()

    async def get_version_by_id(self, version_id: uuid.UUID) -> WorkflowVersionModel | None:
        return await self.session.get(WorkflowVersionModel, version_id)

    async def _next_version_number(self, workflow_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.max(WorkflowVersionModel.version)).where(
                WorkflowVersionModel.workflow_id == workflow_id
            )
        )
        current_max = result.scalar()
        return (current_max or 0) + 1

    @staticmethod
    def to_flow_definition(version_row: WorkflowVersionModel) -> FlowDefinition:
        return FlowDefinition(
            workflow_id=str(version_row.workflow_id),
            version=version_row.version,
            steps=[StepDefinition(**step) for step in version_row.steps],
        )

    async def seed_golden_path(self) -> tuple[WorkflowDefinitionModel, WorkflowVersionModel]:
        """Bootstrap de la demo (paso 0.3/1.7): asegura que exista el
        workflow del golden path con su v1, sin duplicar si ya corrió antes."""
        from app.demo.fixture import GOLDEN_PATH_STEPS, GOLDEN_PATH_WORKFLOW_ID

        workflow = await self.get_or_create_workflow(GOLDEN_PATH_WORKFLOW_ID)
        version_row = await self.get_version(workflow.id, 1)
        if version_row is None:
            version_row = await self.create_version(workflow.id, GOLDEN_PATH_STEPS)
        return workflow, version_row
