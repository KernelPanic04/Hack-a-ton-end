import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health():
    """Usado por el HEALTHCHECK de Docker (ver docker/Dockerfile)."""
    return {"status": "ok"}
