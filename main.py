from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, AsyncSessionLocal
from app.controller.user_controller import router as user_router
from app.controller.user_test_controller import router as user_test_router
from app.controller.auth_controller import router as auth_router
from sqlalchemy import text
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
        # Compatibilidad con bases creadas antes de agregar autenticación.
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
        ))
    await seed_database_if_empty()
    yield
    await engine.dispose()

app = FastAPI(title="Hackathon API Base", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(user_test_router)
