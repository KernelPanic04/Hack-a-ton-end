# Hack-a-ton Backend Template

Plantilla base para el proyecto del Hackathon construida en Python utilizando la arquitectura **Controller-Service-Repository** (Layered Architecture) para un desarrollo rápido, escalable y mantenible.

---

## 🛠️ Stack Tecnológico

* **Framework Web:** FastAPI
* **Validación & DTOs:** Pydantic v2 (`schemas/`)
* **ORM:** SQLAlchemy 2.0 Async (`asyncpg`)
* **Base de Datos:** PostgreSQL (vía Docker)
* **Servidor ASGI:** Uvicorn

---

## 📐 Esquema General de la Arquitectura

```text
       HTTP Request (JSON)
               │
               ▼
┌──────────────────────────────────────────────┐
│           1. CONTROLLER / ROUTER             │
│        (app/controller/user_controller.py)   │
│  - Define verbos HTTP (@get, @post, etc.)    │
│  - Valida contratos de entrada/salida (DTOs) │
└──────────────────────┬───────────────────────┘
                       │ Pasa DTOs validados / Inyecta Service
                       ▼
┌──────────────────────────────────────────────┐
│              2. SERVICE LAYER                │
│         (app/services/user_service.py)       │
│  - Lógica de negocio y reglas de la app      │
│  - Coordina múltiples repositorios           │
└──────────────────────┬───────────────────────┘
                       │ Llama métodos del Repository
                       ▼
┌──────────────────────────────────────────────┐
│             3. REPOSITORY LAYER              │
│       (app/repository/user_repository.py)    │
│  - Consultas a DB (SQLAlchemy 2.0 async)     │
│  - Hereda el CRUD Genérico (base.py)         │
└──────────────────────┬───────────────────────┘
                       │ Mapea entidades (models/)
                       ▼
┌──────────────────────────────────────────────┐
│             DATABASE / PERSISTENCE           │
│        (PostgreSQL en Docker Container)      │
└──────────────────────────────────────────────┘
```

---

## 🚀 Guía Rápida de Extensión: ¿Dónde agrego código?

Para mantener tu proyecto escalable durante el hackathon, sigue este flujo según lo que necesites implementar:

### 1. Si quieres agregar un nuevo ENDPOINT (Ruta HTTP)

- **Dónde:** `app/controller/<modulo>_controller.py`
- **Ejemplo:** Agregar un `@router.put("/{user_id}")` para actualizar un usuario.
- **Flujo:** Defines el endpoint, recibes los datos con Pydantic y llamas al método correspondiente en el `Service`.

### 2. Si quieres agregar LÓGICA DE NEGOCIO

- **Dónde:** `app/services/<modulo>_service.py`
- **Ejemplo:** Validar que el email no esté duplicado antes de guardar, o calcular una puntuación.
- **Flujo:** Creas un nuevo método en el `Service`. Si la validación falla, lanzas una excepción de negocio que el `Controller` traducirá a un `HTTPException`.

### 3. Si quieres agregar una nueva QUERY (Consulta a la DB)

- **Dónde:** `app/repository/<modulo>_repository.py`
- **Ejemplo:** `get_by_email()`, `get_active_users()`, o búsquedas con filtros complejos.
- **Flujo:** Escribes el método usando la sintaxis de **SQLAlchemy 2.0** (`select(UserModel).where(...)`) y ejecutas la consulta de forma asíncrona mediante `self.session.execute()`.

---

## ➕ Pasos para agregar un nuevo MÓDULO completo (ej. `Products`)

Si tu equipo decide agregar una nueva entidad en el hackathon, solo debes seguir estos 5 pasos ordenados:

1. **Modelo (`app/models/product.py`):** Creas la entidad SQLAlchemy heredando de `Base`.
2. **Esquema (`app/schemas/product.py`):** Creas los DTOs de Pydantic (`ProductCreate`, `ProductResponse`).
3. **Repositorio (`app/repository/product_repository.py`):** Creas la clase heredando de `BaseRepository[ProductModel]`.
4. **Servicio (`app/services/product_service.py`):** Creas la clase `ProductService` e inyectas `ProductRepository`.
5. **Controlador (`app/controller/product_controller.py`):** Creas los endpoints con `APIRouter` e incluyes el router en `main.py`.
6. No olvides crear el router en main.py

---

## 📦 Requirements

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

---

## 🏃 Run the Backend Locally

### 1. Start PostgreSQL and FastAPI

```bash
docker compose -f docker/docker-compose.yml up -d
```

The backend will be available at:

```text
http://localhost:8000
```

Interactive API documentation (Swagger UI):

```text
http://localhost:8000/docs
```

### 2. Test the Backend

You can access the following endpoint:

```text
http://localhost:8000/ready
```

---

## 🛑 Stop the Backend

Stop the Docker services while preserving database data:

```bash
docker compose -f docker/docker-compose.yml down
```

Add `-v` only when you intentionally want to delete the local database.

## Railway

This repository is ready to run as a Railway `backend` service. `railway.json`
selects `docker/Dockerfile`, waits for the database-aware `/ready` endpoint and
restarts transient failures. Configure these service variables:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
PORT=8000
AUTH_USER_MODE=users
SQL_ECHO=false
DB_STARTUP_MAX_ATTEMPTS=15
DB_STARTUP_RETRY_SECONDS=2
```

`DATABASE_URL` accepts the standard `postgres://` or `postgresql://` URL Railway
provides and converts it to the async SQLAlchemy driver automatically. Startup
retries cover the case where the managed Postgres service is not ready yet.

Authentication is exposed at `POST /api/auth/register` and
`POST /api/auth/login`. Change `AUTH_USER_MODE=test_users` to use the seeded demo
accounts instead of the main `users` table; their password is
`Hackathon123!`.
