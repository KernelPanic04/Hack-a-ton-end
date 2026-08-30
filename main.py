import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine, Base, get_db
from app.demo.driver import DemoDriver, DemoDriverError
from app.flow.models import StepDefinition
from app.runtime.run import RunEngine, RunEngineError
from app.runtime.pipeline import RuntimePipeline
from app.schemas.contracts import (
    ActionAcceptedEnvelope,
    ActionSubmittedEnvelope,
    RunEvent,
    RunProjection,
    UIUpdatedEnvelope,
)
from app.policy import ActionCoordinator
from app.ws import RunWebSocketHub

# Importante: cargar los modelos antes de crear tablas.
from app.models.workflow import WorkflowDefinitionModel, WorkflowVersionModel  # noqa: F401
from app.models.run import RunModel, RunEventModel, HumanDecisionModel  # noqa: F401

# Orígenes permitidos para llamadas desde el frontend (CORS).
#
# Se puede sobreescribir con la variable de entorno ALLOWED_ORIGINS: una
# lista separada por comas, por ejemplo:
#   ALLOWED_ORIGINS=https://miapp.com,https://www.miapp.com
#
# Si la variable no está definida, se usan estos valores por defecto, que
# cubren el servidor de desarrollo de Vite y el build servido por Nginx/Docker.
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

_allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
ALLOWED_ORIGINS = (
    [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
    if _allowed_origins_env
    else DEFAULT_ALLOWED_ORIGINS
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Hackathon Runtime API", lifespan=lifespan)
app.state.ws_hub = RunWebSocketHub()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DemoAdvanceRequest(BaseModel):
    """Entrada HTTP local del demo driver.

    ``runId`` usa el ID wire que devuelve ``POST /runs``. No se incorpora al
    contrato compartido porque es una envoltura HTTP, no un mensaje runtime/WS.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    run_id: str


class CreateRunRequest(BaseModel):
    """Optional target workflow version for the Phase 4 editor flow."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    workflow_version_id: str | None = None


class WorkflowVersionCreateRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    steps: list[StepDefinition] = Field(min_length=1)
    base_version: int | None = Field(default=None, ge=1)


class WorkflowVersionResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)

    workflow_id: str
    workflow_version_id: str
    version: int
    steps: list[StepDefinition]


def _run_uuid(run_id: str) -> uuid.UUID:
    """Acepta el ID wire ``run_<uuid>`` y UUID crudo para facilitar curl."""
    raw_id = run_id.removeprefix("run_")
    try:
        return uuid.UUID(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="runId inválido") from exc


def _uuid_with_prefix(value: str, prefix: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value.removeprefix(f"{prefix}_"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} inválido",
        ) from exc


def _runtime_error(exc: RunEngineError | DemoDriverError) -> HTTPException:
    message = str(exc)
    # Un run inexistente es el único error de lectura; transiciones inválidas
    # deben quedar explícitas como conflictos, no ocultarse como 500.
    code = status.HTTP_404_NOT_FOUND if "no existe" in message else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=message)


@app.get("/health", tags=["Health"])
async def health():
    """Usado por el HEALTHCHECK de Docker (ver docker/Dockerfile)."""
    return {"status": "ok"}


@app.post("/runs", response_model=RunProjection, status_code=status.HTTP_201_CREATED, tags=["Runs"])
async def create_run(
    request: CreateRunRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> RunProjection:
    """Crea un run del golden path o de una versión creada por el editor."""
    driver = DemoDriver(session)
    try:
        if request is not None and request.workflow_version_id is not None:
            version_id = _uuid_with_prefix(
                request.workflow_version_id, "wfv", "workflowVersionId"
            )
            version = await driver.run_engine.flow_engine.get_version_by_id(version_id)
            if version is None:
                raise RunEngineError(f"WorkflowVersion {version_id} no existe")
            flow = driver.run_engine.flow_engine.to_flow_definition(version)
            run = await driver.run_engine.start_run(version.workflow_id, version.id, flow)
        else:
            run = await driver.start_new_run()
    except RunEngineError as exc:
        raise _runtime_error(exc) from exc
    await RuntimePipeline(session, app.state.ws_hub).publish_current(run.id)
    return await driver.run_engine.get_projection(run.id)


@app.post(
    "/workflows/{workflow_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Workflows"],
)
async def create_workflow_version(
    workflow_id: str,
    request: WorkflowVersionCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> WorkflowVersionResponse:
    """Create immutable v(n+1) from editor-provided generic steps."""
    from app.flow.engine import FlowEngine

    engine = FlowEngine(session)
    workflow_uuid = _uuid_with_prefix(workflow_id, "wf", "workflowId")
    if await engine.get_workflow_by_id(workflow_uuid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow no existe")

    steps = list(request.steps)
    if request.base_version is not None:
        base_version = await engine.get_version(workflow_uuid, request.base_version)
        if base_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow v{request.base_version} no existe",
            )
        base_flow = engine.to_flow_definition(base_version)
        steps = [*base_flow.steps, *steps]

    try:
        version = await engine.create_version(workflow_uuid, steps)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_url=False),
        ) from exc
    return WorkflowVersionResponse(
        workflow_id=f"wf_{workflow_uuid}",
        workflow_version_id=f"wfv_{version.id}",
        version=version.version,
        steps=[StepDefinition.model_validate(step) for step in version.steps],
    )


@app.post("/demo/advance", response_model=RunProjection, tags=["Demo"])
async def advance_demo(
    request: DemoAdvanceRequest, session: AsyncSession = Depends(get_db)
) -> RunProjection:
    """Aplica el siguiente evento guionizado del golden path a un run activo."""
    run_id = _run_uuid(request.run_id)
    driver = DemoDriver(session)
    try:
        run = await driver.advance(run_id)
        await RuntimePipeline(session, app.state.ws_hub).publish_current(run.id)
        return await driver.run_engine.get_projection(run.id)
    except (RunEngineError, DemoDriverError) as exc:
        raise _runtime_error(exc) from exc


@app.post("/demo/skeleton", response_model=RunProjection, tags=["Demo"])
async def create_demo_skeleton(session: AsyncSession = Depends(get_db)) -> RunProjection:
    """Crea un run ya pausado para demostrar Gate G1 en menos de 60 s.

    Reutiliza el golden path real: crea el run y consume sus tres primeros
    eventos hasta ``DECISION_REQUIRED``. El composer determinista produce el
    árbol ``page → alert/decisionPanel/timeline/keyValue`` y el WebSocket lo
    reenvía al conectarse mediante ``latest_envelope``.
    """
    driver = DemoDriver(session)
    try:
        run = await driver.start_new_run()
        for _ in range(3):
            run = await driver.advance(run.id)
        await RuntimePipeline(session, app.state.ws_hub).publish_current(run.id)
        return await driver.run_engine.get_projection(run.id)
    except (RunEngineError, DemoDriverError) as exc:
        raise _runtime_error(exc) from exc


@app.post("/demo/moment/{moment}", response_model=RunProjection, tags=["Demo"])
async def create_demo_moment(moment: int, session: AsyncSession = Depends(get_db)) -> RunProjection:
    """Create M1/M2/M3 as a distinct run of the shared demo operation."""
    driver = DemoDriver(session)
    try:
        run = await driver.start_moment(moment)
        await RuntimePipeline(session, app.state.ws_hub).publish_current(run.id)
        return await driver.run_engine.get_projection(run.id)
    except (RunEngineError, DemoDriverError) as exc:
        raise _runtime_error(exc) from exc


@app.get("/runs/{run_id}/projection", response_model=RunProjection, tags=["Runs"])
async def get_run_projection(
    run_id: str, session: AsyncSession = Depends(get_db)
) -> RunProjection:
    """Snapshot para reconexión y polling; no depende del WebSocket."""
    try:
        return await RunEngine(session).get_projection(_run_uuid(run_id))
    except RunEngineError as exc:
        raise _runtime_error(exc) from exc


@app.get(
    "/runs/{run_id}/snapshot", response_model=UIUpdatedEnvelope, tags=["Runs"]
)
async def get_run_snapshot(
    run_id: str, session: AsyncSession = Depends(get_db)
) -> UIUpdatedEnvelope:
    """Latest validated projection + UISpec for reconnect and polling."""
    try:
        run_uuid = _run_uuid(run_id)
        await RunEngine(session).get_projection(run_uuid)
        envelope = await RuntimePipeline(session, app.state.ws_hub).latest_envelope(
            run_uuid
        )
        if envelope is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El run todavía no tiene una UISpec persistida.",
            )
        return envelope
    except RunEngineError as exc:
        raise _runtime_error(exc) from exc


@app.get("/runs/{run_id}/events", response_model=list[RunEvent], tags=["Runs"])
async def get_run_events(run_id: str, session: AsyncSession = Depends(get_db)) -> list[RunEvent]:
    """Export JSON completo, append-only, del log del run."""
    try:
        return await RunEngine(session).get_event_log(_run_uuid(run_id))
    except RunEngineError as exc:
        raise _runtime_error(exc) from exc


@app.websocket("/ws/runs/{run_id}")
async def run_websocket(
    websocket: WebSocket, run_id: str, session: AsyncSession = Depends(get_db)
) -> None:
    """Subscribe to live typed envelopes for a single demo run.

    On connection it replays the latest persisted ``UI_UPDATED`` envelope,
    then pushes future transitions for that run.
    """
    if websocket.query_params.get("token") != os.getenv("DEMO_TOKEN", "placeholder"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        run_uuid = _run_uuid(run_id)
        wire_run_id = f"run_{run_uuid}"
        await RunEngine(session).get_projection(run_uuid)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except RunEngineError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    hub: RunWebSocketHub = app.state.ws_hub
    await hub.connect(wire_run_id, websocket)
    try:
        pipeline = RuntimePipeline(session, hub)
        envelope = await pipeline.latest_envelope(run_uuid)
        if envelope is not None:
            await websocket.send_json(envelope.model_dump(mode="json"))
        while True:
            message = await websocket.receive_text()
            try:
                submitted = ActionSubmittedEnvelope.model_validate_json(message)
            except ValidationError:
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                return

            if submitted.run_id != wire_run_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            result = await ActionCoordinator(session).handle(submitted.payload, run_uuid)
            if isinstance(result, ActionAcceptedEnvelope):
                # ACTION_ACCEPTED is visible before the next deterministic UI
                # snapshot, preserving the Phase 1 click feedback.
                await hub.publish(result)
                await pipeline.publish_current(run_uuid)
            else:
                # A rejection belongs only to the tab that submitted it.
                await websocket.send_json(result.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(wire_run_id, websocket)
