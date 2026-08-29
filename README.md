# Hack-a-ton-end · NextWave 2026 Challenge 03

Backend FastAPI del runtime de agentes de Kernel Panic. La rama `dev` contiene
la arquitectura modular vigente: workflows versionados, reducer de runs, event
log append-only, fixture/demo driver y contratos Pydantic compartidos. Consulta
`AGENTS.md` para el roadmap y los gates de entrega.

## Arquitectura actual

| Ruta | Responsabilidad |
|---|---|
| `app/flow/` | Definiciones y versiones inmutables de workflows |
| `app/runtime/` | Ejecución, transiciones y proyección de runs |
| `app/demo/` | Golden path, mock provider y demo driver |
| `app/models/` | Tablas SQLAlchemy de workflows, runs, eventos y decisiones |
| `app/schemas/contracts.py` | Contrato v1 ejecutable para backend/frontend/WS |
| `main.py` | Aplicación FastAPI, CORS, lifecycle y healthcheck |

La arquitectura Controller–Service–Repository del template anterior ya no es
la estructura principal del runtime. Los módulos se organizan por capacidad del
roadmap y comparten PostgreSQL dentro del mismo monolito modular.

## Requisitos

- Docker con Docker Compose para el flujo recomendado.
- Python 3.12+ solamente si se ejecutará FastAPI fuera de Docker.

## Variables de entorno

```bash
cp .env.example .env
```

| Variable | Default | Uso |
|---|---:|---|
| `BACKEND_PORT` | `8000` | Puerto de FastAPI publicado en el host |
| `POSTGRES_PORT` | `5433` | Puerto de PostgreSQL publicado en el host |
| `PORT` | `8000` | Puerto interno de FastAPI en el contenedor |
| `DEMO_TOKEN` | placeholder | Token compartido del handshake WebSocket de demo |
| `ALLOWED_ORIGINS` | frontend `5173`/`3000` | Lista CORS separada por comas |

`DEMO_TOKEN` debe coincidir con `VITE_DEMO_TOKEN` del frontend. Es un control
exclusivo de la demo, no una credencial de producción. Nunca commitees `.env`.

## Inicio recomendado: backend completo con Docker

Desde la raíz del repositorio:

```bash
docker compose -f docker/docker-compose.yml up --build -d
docker compose -f docker/docker-compose.yml ps
curl --fail http://localhost:8000/health
```

Servicios publicados:

| Servicio | URL/puerto del host | Puerto interno |
|---|---|---:|
| FastAPI | `http://localhost:8000` | `8000` |
| Swagger | `http://localhost:8000/docs` | `8000` |
| Health | `http://localhost:8000/health` | `8000` |
| PostgreSQL | `localhost:5433` | `5432` |

Compose ya levanta FastAPI; no ejecutes además `uvicorn` en el puerto 8000.

Si esos puertos están ocupados, cambia `.env` sin editar Compose:

```env
BACKEND_PORT=18000
POSTGRES_PORT=15433
```

En ese caso, el healthcheck queda en `http://localhost:18000/health`. Si el
frontend apunta directamente al backend, actualiza también `VITE_API_URL`.

## Desarrollo local de FastAPI

Levanta solamente PostgreSQL y ejecuta la API en el host:

```bash
docker compose -f docker/docker-compose.yml up -d postgres
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

La configuración Python usa por defecto PostgreSQL en `localhost:5433`. Si
cambias `POSTGRES_PORT`, define una `DATABASE_URL` equivalente para Uvicorn.

## Contratos v1

`app/schemas/contracts.py` es la autoridad ejecutable. Incluye:

- `RunEvent` append-only y `RunProjection`.
- `UISpec` con `reason` obligatorio y las nueve primitivas autorizadas.
- `ActionEvent` sin `eventId` creado por cliente.
- Envelope WebSocket tipado y los doce mensajes de servidor P0.
- IDs wire prefijados (`run_`, `wf_`, `step_`, `act_`, etc.).

El runtime conserva UUIDs y step IDs internos; `RunEngine.get_projection()` los
adapta al contrato wire sin cambiar la persistencia de la arquitectura nueva.

## HTTP del runtime (Rol A)

Estos endpoints no dependen del WebSocket y permiten conducir y recuperar la
demo por HTTP. Los identificadores devueltos usan el formato wire (`run_<uuid>`).

| Método | Ruta | Resultado |
|---|---|---|
| `POST` | `/runs` | Crea el run v1 del golden path y devuelve su `RunProjection` inicial. |
| `POST` | `/demo/advance` | Recibe `{"runId":"run_<uuid>"}`, aplica el siguiente evento guionizado y devuelve la proyección. |
| `GET` | `/runs/{runId}/projection` | Devuelve el snapshot actual para polling/reconexión. |
| `GET` | `/runs/{runId}/events` | Devuelve el event log append-only completo como `RunEvent[]`. |

Ejemplo de avance:

```bash
curl -X POST http://localhost:8000/runs
curl -X POST http://localhost:8000/demo/advance \
  -H 'content-type: application/json' \
  -d '{"runId":"run_<uuid-devuelto>"}'
```

`/projection` devuelve la proyección del runtime. La `UISpec` se añadirá a ese
snapshot al integrar el pipeline de síntesis del paso 2.6; todavía no existe
un compositor en este repositorio.

## Pruebas

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app main.py
docker compose -f docker/docker-compose.yml config --quiet
```

Las pruebas cubren invariantes de contratos, serialización camelCase, ausencia
de `eventId` en `ActionEvent`, registry/mensajes congelados y adaptación del
runtime actual a `RunProjection`.

## Apagado

```bash
docker compose -f docker/docker-compose.yml down
```

El volumen de PostgreSQL se conserva. Usa `down -v` solo cuando quieras borrar
deliberadamente todos los datos locales del proyecto.
