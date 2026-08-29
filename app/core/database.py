import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Local (fuera de Docker): usa el valor por defecto de abajo, que apunta al
# Postgres de docker/docker-compose.yml publicado en el puerto 5433 (evita el
# conflicto con un Postgres nativo de Windows escuchando en 5432).
#
# Docker / despliegue: se sobreescribe con la variable de entorno DATABASE_URL.
# docker/docker-compose.yml se la pasa al servicio "backend" apuntando al
# servicio "postgres" por su nombre en la red interna de Docker, puerto 5432
# (el puerto interno del contenedor, no el 5433 publicado al host).
#
# Proveedores como Railway/Render entregan DATABASE_URL con el esquema
# postgresql:// (o el legado postgres://), sin especificar el driver. El
# motor async de SQLAlchemy necesita el driver asyncpg explícito, así que
# lo normalizamos aquí en vez de exigir que la variable de entorno ya venga
# en el formato correcto.
def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = _to_asyncpg_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://hack_user:hack_password@localhost:5433/hackathon_db",
    )
)

engine = create_async_engine(
    DATABASE_URL,
    echo=_env_flag("SQL_ECHO"),
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Clase base de la cual heredarán todos los modelos de DB"""

    pass


# Dependency Injection for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
