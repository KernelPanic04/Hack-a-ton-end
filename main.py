import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, AsyncSessionLocal
from app.controller.user_controller import router as user_router
from app.controller.user_test_controller import router as user_test_router
from sqlalchemy.future import select

# Importante: cargar el modelo antes de crear tablas
from app.models.user import UserModel
from app.models.user_test import UserTestModel

FAKE_USERS = [
    {"name": "Alice Backend", "email": "alice@hackathon.com"},
    {"name": "Bob Frontend", "email": "bob@hackathon.com"},
    {"name": "Charlie DevOps", "email": "charlie@hackathon.com"},
    {"name": "Diana Designer", "email": "diana@hackathon.com"},
    {"name": "Evan PM", "email": "evan@hackathon.com"},
]

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


async def seed_database_if_empty():
    """Inserta datos de prueba solo si la tabla está completamente vacía."""
    async with AsyncSessionLocal() as session:
        # Verificar si existe al menos un registro
        result = await session.execute(select(UserTestModel).limit(1))
        has_data = result.scalars().first()

        if not has_data:
            print("Base de datos vacía. Insertando datos de prueba iniciales...")
            for user_data in FAKE_USERS:
                session.add(UserTestModel(**user_data))
            await session.commit()
            print("Datos de prueba insertados automáticamente.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_database_if_empty()
    yield
    await engine.dispose()

app = FastAPI(title="Hackathon API Base", lifespan=lifespan)

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


app.include_router(user_router)
app.include_router(user_test_router)
