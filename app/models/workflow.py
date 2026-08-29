import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkflowDefinitionModel(Base):
    """Un workflow lógico (ej. 'logistica-booking'). Sus versiones concretas
    y ejecutables viven en WorkflowVersionModel."""

    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WorkflowVersionModel(Base):
    """Versión inmutable de un workflow: lista de StepDefinition serializada.
    Crear una v(n+1) es un insert nuevo, nunca un update (objetivo Rol A #1:
    crear v2 por API sin reiniciar el proceso)."""

    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
