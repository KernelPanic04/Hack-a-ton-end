from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import engine, Base
from app.controller.user_controller import router as user_router

# Importante: cargar el modelo antes de crear tablas
from app.models.user import UserModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Hackathon API Base", lifespan=lifespan)

app.include_router(user_router)