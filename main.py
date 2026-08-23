from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import engine, Base, AsyncSessionLocal
from app.controller.user_controller import router as user_router
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
    await seed_database_if_empty()
    yield
    await engine.dispose()

app = FastAPI(title="Hackathon API Base", lifespan=lifespan)

app.include_router(user_router)