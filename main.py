import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, AsyncSessionLocal
from app.controller.user_controller import router as user_router
from app.controller.user_test_controller import router as user_test_router
from app.controller.auth_controller import router as auth_router
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select

# Importante: cargar el modelo antes de crear tablas
from app.models.user import UserModel
from app.models.user_test import UserTestModel
from app.core.security import password_hash

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

_allowed_origins_env = os.getenv("CORS_ORIGINS") or os.getenv("ALLOWED_ORIGINS")
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
                session.add(UserTestModel(
                    **user_data,
                    password_hash=password_hash.hash("Hackathon123!"),
                ))
            await session.commit()
            print("Datos de prueba insertados automáticamente.")


async def initialize_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Compatibilidad con bases creadas antes de agregar autenticación.
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
        ))
        await conn.execute(text(
            "ALTER TABLE test_users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
        ))
        await conn.execute(
            text("UPDATE test_users SET password_hash = :password_hash WHERE password_hash IS NULL"),
            {"password_hash": password_hash.hash("Hackathon123!")},
        )
    await seed_database_if_empty()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Railway no implementa depends_on: la API puede arrancar unos segundos
    # antes que PostgreSQL. Reintentamos de forma acotada antes de fallar para
    # que el despliegue no dependa de una carrera entre servicios.
    max_attempts = max(1, int(os.getenv("DB_STARTUP_MAX_ATTEMPTS", "15")))
    retry_delay = max(0.1, float(os.getenv("DB_STARTUP_RETRY_SECONDS", "2")))

    for attempt in range(1, max_attempts + 1):
        try:
            await initialize_database()
            break
        except SQLAlchemyError:
            if attempt == max_attempts:
                raise
            print(
                f"PostgreSQL no está disponible (intento {attempt}/{max_attempts}); "
                f"reintentando en {retry_delay:g}s..."
            )
            await engine.dispose()
            await asyncio.sleep(retry_delay)

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
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready():
    """Comprueba que la API también puede consultar PostgreSQL."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


app.include_router(user_router)
app.include_router(user_test_router)
app.include_router(auth_router)
