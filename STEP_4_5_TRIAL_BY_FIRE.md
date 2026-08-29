# Paso 4.5 · Nuevo run con versión nueva y paso inventado

## Objetivo observable

Sin reiniciar FastAPI ni añadir código específico para un tipo de paso, crear
una versión `v(n+1)` de un workflow, iniciar un run contra esa versión y
comprobar que el paso nuevo:

1. aparece en el timeline;
2. resuelve los `inputs` que declaró desde el estado del run;
3. se ejecuta mediante el executor genérico;
4. deja evidencia en el event log; y
5. se renderiza como una `UISpec` válida. Si su resultado incluye
   `comparison`, la UI debe contener un nodo `compare` real.

Este documento implementa el paso 4.5 del roadmap. No cambia los contratos
congelados y no autoriza efectos externos: el provider sigue siendo local/mock.

## Prerrequisitos

- Backend actualizado desde `dev` con 4.1 y 4.2 (`POST /workflows/{id}/versions`
  y `GenericStepExecutor`).
- Integración de 4.3 disponible para la ruta LLM opcional.
- PostgreSQL y FastAPI iniciados.
- Para una prueba sin consumo de API:

  ```env
  LLM_UPGRADE_ENABLED=false
  GENERIC_STEP_LLM_ENABLED=false
  ```

- Para ejecutar la mejora LLM real del paso inventado:

  ```env
  OPENAI_API_KEY=...
  OPENAI_MODEL=gpt-5.4-mini
  GENERIC_STEP_LLM_ENABLED=true
  ```

`DEMO_TOKEN` no interviene en estos endpoints HTTP; solo se necesita al abrir
el WebSocket desde el frontend.

## Flujo de implementación

```text
POST /runs (v1) → workflowId
       ↓
POST /workflows/{workflowId}/versions (v2 + paso inventado)
       ↓
POST /runs { workflowVersionId: v2 }
       ↓
POST /demo/advance hasta llegar al paso nuevo
       ↓
MockProvider no tiene evento → GenericStepExecutor
       ↓
inputs resueltos → LLM opcional/fallback → RunEngine.advance
       ↓
RunProjection → composer → UISpec → timeline / compare / event log
```

## Procedimiento manual

### 1. Levantar el backend

Desde `Hack-a-ton-end`:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

La API queda disponible normalmente en `http://localhost:8000`. Espera una
respuesta `{"status":"ok"}` en `GET /health`.

### 2. Crear un run base y conservar su `workflowId`

En otra terminal PowerShell:

```powershell
$baseRun = Invoke-RestMethod -Method Post -Uri http://localhost:8000/runs
$workflowId = $baseRun.workflowId
$workflowId
```

El `workflowId` devuelto identifica el workflow al que se le creará la versión
nueva. El run base no se usa para la prueba final.

### 3. Crear v(n+1) con un paso inventado

El endpoint recibe la lista completa de pasos de la versión nueva. Incluye los
pasos que el equipo quiera conservar y agrega uno que no exista en el mock
provider. Este ejemplo usa tipos, títulos y rutas de inputs genéricos:

```powershell
$versionBody = @{
  steps = @(
    @{
      id = "collect_state"
      type = "generic.collect"
      title = "Collect state"
      objective = "Collect values needed by subsequent steps."
      inputs = @()
      requiresHumanReview = $false
    },
    @{
      id = "review_invented"
      type = "generic.review"
      title = "Review resolved values"
      objective = "Assess the resolved values and report any meaningful change."
      inputs = @("collect_state.data")
      requiresHumanReview = $false
    }
  )
} | ConvertTo-Json -Depth 8

$newVersion = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/workflows/$workflowId/versions" `
  -ContentType "application/json" `
  -Body $versionBody

$newVersion
```

Esperado: HTTP `201`, `version` incrementada y un `workflowVersionId` con
prefijo `wfv_`.

> Ajusta las rutas de `inputs` a claves que los pasos anteriores realmente
> hayan escrito en el estado. Cada ruta usa segmentos separados por punto.
> Una ruta inexistente no rompe el run: queda en `missing_inputs` y el resultado
> recibe `attention`.

### 4. Crear un run contra la versión nueva

```powershell
$runBody = @{ workflowVersionId = $newVersion.workflowVersionId } | ConvertTo-Json
$trialRun = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/runs `
  -ContentType "application/json" `
  -Body $runBody

$runId = $trialRun.runId
$runId
```

Comprueba que `$trialRun.workflowVersion` coincide con `$newVersion.version`.

### 5. Avanzar hasta el paso inventado

Ejecuta una vez por cada paso anterior al inventado:

```powershell
$advanceBody = @{ runId = $runId } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/demo/advance `
  -ContentType "application/json" `
  -Body $advanceBody
```

Cuando `MockProvider` no encuentre un evento guionizado para
`review_invented`, `DemoDriver` debe delegar en `GenericStepExecutor`. No se
debe crear un evento mock para ese `type`: ese es precisamente el caso que se
está demostrando.

### 6. Inspeccionar proyección, snapshot y event log

```powershell
$projection = Invoke-RestMethod -Uri "http://localhost:8000/runs/$runId/projection"
$snapshot = Invoke-RestMethod -Uri "http://localhost:8000/runs/$runId/snapshot"
$events = Invoke-RestMethod -Uri "http://localhost:8000/runs/$runId/events"

$projection | ConvertTo-Json -Depth 15
$snapshot.payload.uiSpec | ConvertTo-Json -Depth 20
$events | ConvertTo-Json -Depth 15
```

Si se prueba con frontend, abre el inspector de `UISpec` y conéctalo a:

```text
ws://localhost:8000/ws/runs/{runId}?token={DEMO_TOKEN}
```

## Resultado esperado

El estado del paso inventado contiene siempre el resultado determinista:

```json
{
  "resolved_inputs": {
    "input_1": {
      "source": "collect_state.data",
      "value": {}
    }
  },
  "missing_inputs": []
}
```

Con la ruta LLM habilitada y válida, también contiene:

```json
{
  "findings": ["..."],
  "comparison": null,
  "verdict": "pass",
  "summary": "..."
}
```

Cuando `comparison` no es `null`, debe respetar `CompareProps` y la `UISpec`
debe contener un nodo con `type: "compare"`. No es válido sustituirlo por un
`keyValue` con datos parecidos.

## Pruebas automatizadas requeridas

Antes de abrir el PR:

```powershell
cd C:\Users\Diego\Hack-a-ton-end
.venv\Scripts\python.exe -m unittest tests.test_generic_executor tests.test_generic_step_llm -v
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Añadir una prueba de integración para 4.5 que haga lo siguiente:

1. crea una versión nueva con un paso no guionizado;
2. inicia un run indicando `workflowVersionId`;
3. avanza hasta el paso inventado;
4. comprueba `STEP_STARTED` y `STEP_COMPLETED` para ese `stepId`;
5. comprueba `resolved_inputs` y, con mock LLM, `findings`, `verdict` y
   `summary`;
6. compone una `UISpec` válida cuyo timeline contiene el paso; y
7. cuando hay comparación, comprueba que existe un nodo `compare`.

## Definition of Done de 4.5

- [ ] La API crea `v(n+1)` sin reiniciar FastAPI.
- [ ] `POST /runs` acepta y usa `workflowVersionId`.
- [ ] El paso inventado no tiene fixture del mock provider.
- [ ] El executor resuelve sus rutas de input desde el estado del run.
- [ ] El timeline y el event log muestran el paso en ejecución y completado.
- [ ] La `UISpec` pasa Pydantic y el inspector la puede mostrar.
- [ ] `comparison` produce `compare`; sin comparación no se agrega ese nodo.
- [ ] La ruta sin key, timeout o error de proveedor conserva el fallback
  determinista.

## Handoff esperado

El PR hacia `dev` debe incluir: rama, commit, endpoints probados, resultado de
la suite, una evidencia de `GET /runs/{runId}/events` y una captura o JSON del
inspector que muestre el paso nuevo. El gate que avanza es H17; no se declara
cerrado hasta ejecutar también el trial-by-fire de 4.6.
