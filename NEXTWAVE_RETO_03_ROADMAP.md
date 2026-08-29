# NextWave 2026 · Challenge 03 — Roadmap ejecutable y roles

> Plan de construcción paso a paso para **Kernel Panic**, derivado del brief y de la revisión crítica (`NEXTWAVE_RETO_03_REVISION_CRITICA.md`). Cuatro roles, siete fases con gates, y objetivos medibles por rol.
>
> **Cómo usarlo:** cada persona lee su rol (sección 2) y su columna en cada fase (sección 3). Lane D administra los gates y los kill criteria. Si una tarea no aparece aquí, no se hace sin pasar por el decision log.

## 1. Reglas del roadmap

- Presupuesto real: **~60 horas útiles** entre 4 personas (no 96). Las fases ya lo descuentan.
- `main` demostrable siempre; merge obligatorio en cada gate (H3, H8, H13, H17, H20).
- Cada fase tiene **Definition of Done (DoD)**: si no se cumple, se aplica el kill criteria de la revisión crítica, no se "estira" la fase.
- Convención de nombres usada abajo (ajustable, pero decidan en H0 y no lo vuelvan a discutir):

```text
Backend (Hack-a-ton-end/app/)
  flow/        definiciones, versiones y motor de workflow
  runtime/     ejecución de runs, reducer, agente, executor genérico
  synthesis/   composer determinista + composer LLM
  policy/      policy engine y validación de acciones
  ws/          hub WebSocket y envelope
  demo/        fixture, mock provider, demo driver

Frontend (Hack-a-ton-front/src/)
  runtime/     Renderer, registry, reducer, socket, tipos congelados
  components/ui-kit/   los 9 componentes del registry
  inspector/   drawer de UISpec
  editor/      editor mínimo de workflow
```

## 2. Los cuatro roles

### Rol A — Runtime Engineer (backend: flow, runs, agente)

> **Misión:** que exista un run vivo: workflow versionado, estado que avanza, eventos que se emiten y un agente que ejecuta pasos — incluidos pasos que nadie programó.

Es dueño de: `flow/`, `runtime/`, `demo/`, las tablas de base de datos y el endpoint de snapshot.

**Objetivos del rol (medibles):**

1. Motor de workflow con versiones: crear v2 de un flow por API sin reiniciar el proceso. *(DoD: gate H13/H17)*
2. Golden path de 5 pasos corriendo end-to-end contra el mock provider, avanzado por el demo driver. *(gate H8)*
3. Run pausable y reanudable por una decisión humana validada. *(gate H13)*
4. Generic step executor: un paso inventado en runtime produce findings reales desde el estado. *(gate H17)*
5. Event log append-only escrito en cada transición, exportable como JSON para la defensa. *(gate H17)*

### Rol B — Interface Engineer (frontend: renderer, realtime, estética)

> **Misión:** que cualquier `UISpec` válida se convierta en una pantalla bonita, y que ninguna `UISpec` inválida rompa nada.

Es dueño de: `runtime/` del frontend, los 9 componentes del ui-kit, el inspector, los design tokens y el pulido visual.

**Objetivos del rol:**

1. Renderer recursivo + registry: dado un JSON de `UISpec`, pinta el árbol; tipo desconocido → `GenericStepCard`; props rotas → error boundary por nodo, nunca pantalla blanca. *(gate H3)*
2. Cliente WS con reconexión por re-fetch de snapshot, y fallback de polling activable por flag. *(gate H13)*
3. Los 9 componentes del registry con design tokens coherentes (énfasis normal/warning/critical). *(gate H8 los 6 básicos; H13 los 9)*
4. Inspector de `UISpec` (drawer): JSON vivo, `generatedBy`, `reason`, `stateVersion`. *(gate H13)*
5. Dos layouts estructuralmente distintos (normal vs anomalía) verificables en el inspector. *(gate H13)*

### Rol C — Synthesis Engineer (composers, LLM, contratos de IA)

> **Misión:** que la UI se genere de verdad: primero determinista en <50 ms, luego mejorada por el LLM — y que se pueda probar que no hay pantallas disfrazadas.

Es dueño de: `synthesis/`, el prompt y structured outputs, la validación Pydantic de `UISpec`, y la parte LLM del generic step executor.

**Objetivos del rol:**

1. Composer determinista que produce `UISpec` solo desde metadatos genéricos (`step.type`, `verdict`, `pendingDecision`, tipos de datos) — `grep -i "booking\|vessel\|bol" synthesis/` devuelve vacío. *(gate H8)*
2. Composer LLM con structured outputs, timeout 5 s, un retry, validado contra registry y `availableActions`; si falla, la determinista ya está en pantalla. *(gate H13)*
3. Patrón de mejora progresiva funcionando: la UI se refina visiblemente ~2 s después de cada transición, con `generatedBy` y `reason` correctos. *(gate H13)*
4. Structured output del generic step executor (`findings`, `comparison?`, `verdict`, `summary`) integrado con el Rol A. *(gate H17)*
5. Latencia y cuota de la API del modelo medidas desde el entorno real en H0, con cifras en el decision log. *(gate H3)*

### Rol D — Integration Captain (contratos, policy, gates, entregables)

> **Misión:** que las piezas de A, B y C se toquen cada 3 horas, que el alcance no crezca, y que la defensa técnica esté lista sin robarle horas al código.

Es dueño de: contratos congelados y tipos TS, `policy/`, `ws/` (envelope y hub los monta él para desbloquear a A y B), walking skeleton, decision log, README, diagrama, slides, ensayos. **Es la única persona autorizada a mover el alcance y decreta los kill criteria.**

**Objetivos del rol:**

1. Contratos congelados y tipos TS escritos a mano antes de H1; cero cambios de contrato después de H8 sin su firma. *(gate H1)*
2. Walking skeleton E2E (WS → renderer → click → `ActionEvent` → log) en `main`. *(gate H3)*
3. Policy engine declarativo + validación completa de `ActionEvent` (token, run activo, decisión pendiente, `stateVersion`, idempotencia), con el rechazo en vivo reproducible. *(gate H13)*
4. Cadencia de integración cada 3 h ejecutada; `main` nunca >3 h sin ser demostrable. *(continuo)*
5. Entregables completos: README, diagrama, decision log, slides, video de respaldo grabado, tres ensayos cronometrados. *(H24)*

## 3. Roadmap paso a paso

### Fase 0 · H0–H1 — Congelamiento

Todos juntos, una sola mesa. Nadie escribe features.

| # | Paso | Responsable |
|---|---|---|
| 0.1 | Congelar `RunProjection`, `UISpec` (+`reason`), `ActionEvent` (sin `eventId` de cliente), `RunEvent`, envelope WS. Publicarlos como módulos Pydantic en `app/schemas/contracts.py` y tipos TS en `src/runtime/contracts.ts` | D escribe, todos firman |
| 0.2 | Acordar registry de 9 componentes y sus props exactas (una tabla, no código) | B propone, C valida que puede componerlos |
| 0.3 | Definir golden path de 5 pasos y el fixture (email de booking + eventos guionizados del buque) | A |
| 0.4 | Definir design tokens: espaciados, jerarquía tipográfica, colores de énfasis normal/warning/critical sobre el Tailwind existente | B |
| 0.5 | Medir latencia real de la API del modelo con structured outputs (key real, red real); anotar cifras | C |
| 0.6 | Verificar que los 4 corren ambos repos con `docker compose up`; token estático `DEMO_TOKEN` en env | D |
| 0.7 | Crear `DECISION_LOG.md` con las decisiones ya cerradas de la revisión crítica | D |

**DoD H1:** contratos en ambos repos, registry acordado, fixture escrito, los 4 entornos corriendo.

### Fase 1 · H1–H3 — Walking skeleton

Objetivo: un click viaja el loop completo con datos falsos.

| # | Paso | Responsable |
|---|---|---|
| 1.1 | `ws/hub.py`: hub en memoria `{runId: [conexiones]}`, handshake con `DEMO_TOKEN`, envelope tipado | D |
| 1.2 | Endpoint `POST /demo/skeleton`: emite por WS una `UISpec` hardcodeada (page → section → metric + decisionPanel) | D |
| 1.3 | `runtime/Renderer.tsx` + `registry.ts` con `page`, `section`, `metric`, `decisionPanel`, `step` (versión fea, sin estilo) | B |
| 1.4 | `useRunSocket.ts` + reducer frontend: recibe envelope, guarda `UISpec`, la pinta | B |
| 1.5 | Click en `decisionPanel` → `ActionEvent` por WS → backend lo loguea y responde `ACTION_ACCEPTED` | B + D |
| 1.6 | Esqueleto de tablas: `workflow_definitions`, `workflow_versions`, `runs`, `run_events`, `human_decisions` (SQLAlchemy, `create_all`) | A |
| 1.7 | Replays de `RunProjection` grabadas en `demo/fixtures/` para que C trabaje sin depender de A | A |
| 1.8 | Composer determinista v0 contra la fixture grabada: produce `UISpec` válida (Pydantic pasa) | C |

**DoD H3 (GATE):** demo de 60 segundos: levantar, ver UI renderizada por WS, click, log en backend. Si falla → kill criteria: WS se degrada a polling y el skeleton cierra en H4 como sea.

### Fase 2 · H3–H8 — Golden path real con UI determinista

Objetivo: el run completo de Muebles del Sur se ve en pantalla, generado, sin LLM.

| # | Paso | Responsable |
|---|---|---|
| 2.1 | `flow/models.py` + `flow/engine.py`: definición de workflow (pasos con `title`, `objective`, `inputs`, `requiresHumanReview`), versión 1 del flow logístico sembrada | A |
| 2.2 | `runtime/run.py`: reducer de run — estado en memoria, JSON persistido en la fila del run, `RunEvent` append en cada transición | A |
| 2.3 | `demo/provider.py`: mock provider guionizado (salida del buque, transbordo, ETA +9 días) | A |
| 2.4 | `demo/driver.py` + `POST /demo/advance`: cada llamada dispara el siguiente evento del guion | A |
| 2.5 | `GET /runs/{id}/projection`: snapshot completo (proyección + última `UISpec`) — sirve para reconexión Y polling | A |
| 2.6 | Pipeline de emisión: transición → `RunProjection` → composer determinista → `UISpec` → WS | A + C |
| 2.7 | Composer determinista v1: layouts distintos por situación (normal / decisión pendiente / anomalía), solo con metadatos genéricos | C |
| 2.8 | Componentes `alert`, `timeline`, `keyValue` con design tokens; restyling de los 5 del skeleton | B |
| 2.9 | Reducer frontend maneja los 12 mensajes P0 (`RUN_STARTED` … `ERROR`) | B |
| 2.10 | Primer borrador del diagrama de arquitectura y README (30 min, no más) | D |
| 2.11 | Integración H6: correr el golden path completo entre los 4, lista de huecos, reasignar | D |

**DoD H8 (GATE):** `POST /runs` + clicks de `/demo/advance` → los 5 pasos se ven en pantalla con UI generada determinista, timeline vivo y anomalía renderizada. Si falla → kill criteria: se elimina el composer LLM del alcance y C se vuelca al golden path.

### Fase 3 · H8–H13 — Loop humano cerrado + LLM + inspector

Objetivo: la decisión humana cambia el curso del agente; la UI se mejora sola con el LLM; todo es inspeccionable.

| # | Paso | Responsable |
|---|---|---|
| 3.1 | Pausa de run en `DECISION_REQUIRED` (transbordo detectado): `pendingDecision` + `availableActions` en la proyección | A |
| 3.2 | Rama de consecuencia: acción `find_alternative` → agente "busca" en el mock provider → nueva ruta, días recuperados → `RUN_RESUMED` + nueva UI | A |
| 3.3 | `policy/engine.py`: tabla `actionId → {risk, requiresHuman, payloadSchema}` + validación completa de `ActionEvent` (token, run, decisión pendiente, `stateVersion`, idempotencyKey) | D |
| 3.4 | `ACTION_REJECTED` con motivo legible; probar el rechazo por estado viejo con dos pestañas y dejarlo guionizado | D |
| 3.5 | `synthesis/llm.py`: composer LLM con structured outputs, timeout 5 s, un retry, validación contra registry y acciones; integrado como upgrade sobre la determinista | C |
| 3.6 | `generatedBy` + `reason` fluyendo hasta el frontend en ambas rutas | C |
| 3.7 | Componentes `compare` (diff genérico de dos objetos) y `decisionPanel` final con estados (enviando / aceptada / rechazada) | B |
| 3.8 | `inspector/`: drawer con JSON vivo de la `UISpec`, `generatedBy`, `reason`, `stateVersion` | B |
| 3.9 | Verificar los dos layouts estructuralmente distintos en el inspector (árboles diferentes, no mismos nodos con otros datos) | B + C |
| 3.10 | Integración H12: demo de los momentos 1–3 del guion completa | D |

**DoD H13 (GATE):** demo momentos 1–3 + rechazo en vivo + inspector mostrando upgrade determinista→LLM. Si falla → kill criteria: se elimina el editor visual de la fase 4 (trial-by-fire por `POST` con JSON en pantalla).

### Fase 4 · H13–H17 — Trial-by-fire

Objetivo: un paso que nadie programó se crea, se ejecuta y se renderiza.

| # | Paso | Responsable |
|---|---|---|
| 4.1 | `POST /workflows/{id}/versions`: crear v(n+1) con un paso nuevo; evento `workflow.version.created` al log | A |
| 4.2 | Generic step executor determinista: resolver `inputs` contra el estado, mostrar en `keyValue`, marcar `attention`, pedir revisión si aplica | A |
| 4.3 | Generic step executor LLM: objetivo + inputs resueltos → `{findings, comparison?, verdict, summary}`; si hay `comparison`, el sintetizador usa `compare` | C |
| 4.4 | `editor/`: formulario mínimo (title, objective, inputs como picker de claves del estado, requiresHumanReview) → crea versión → muestra diff del flow → botón "Run with v(n+1)" | B |
| 4.5 | Nuevo run con la versión nueva: el paso inventado aparece en timeline y se ejecuta de verdad | A + C |
| 4.6 | Ensayo del trial-by-fire con un paso que **nadie del equipo haya probado antes** (lo inventa D en el momento) | D |
| 4.7 | Export del event log como JSON (`GET /runs/{id}/events`) para la defensa | A |

**DoD H17 (GATE):** D teclea un paso inventado en el editor, sin reiniciar nada, y el siguiente run lo ejecuta y renderiza con `generatedBy` visible. Si falla → el trial-by-fire sale del guion en vivo y va al video de respaldo.

### Fase 5 · H17–H20 — Freeze, fallbacks y pulido

Feature freeze. Solo estabilidad, estética y seguridad.

| # | Paso | Responsable |
|---|---|---|
| 5.1 | Probar los fallbacks de verdad: matar el LLM (env sin key) → demo completa determinista; matar el WS → polling; sin red → todo local | A + C |
| 5.2 | Reconexión: cerrar pestaña a mitad de run, reabrir, re-fetch de snapshot, seguir | B |
| 5.3 | Dos horas de pulido visual exclusivo: espaciados, transiciones al reestructurar (200 ms, no más), estados vacíos | B |
| 5.4 | Grep de honestidad en `synthesis/`: cero strings del dominio; revisión cruzada de composer por A | C + A |
| 5.5 | Deploy Railway **solo si todo lo anterior respira**; la demo oficial es local | D |
| 5.6 | Limpieza de logs, datos fake y endpoints muertos; repo público con README real | D |

**DoD H20:** freeze absoluto. Cualquier cambio posterior = bugfix aprobado por D.

### Fase 6 · H20–H24 — Entrega y ensayos

| # | Paso | Responsable |
|---|---|---|
| 6.1 | Ensayo 1 completo con demo driver, cronometrado; lista de tropiezos | Todos, D dirige |
| 6.2 | Grabar video de respaldo durante el ensayo 2 (pantalla + narración) | D |
| 6.3 | Slides: north star, diagrama, los 4 momentos, seguridad, decision log | D + B |
| 6.4 | Cada uno ensaya el "loop en 60 segundos" hasta decirlo sin el slide | Todos |
| 6.5 | Ensayo 3 con roles de presentación fijados; el juez simulado (A) inventa el paso del trial-by-fire | Todos |
| 6.6 | Revisión final del repo público: README, diagrama, `DECISION_LOG.md`, export del event log | D |

## 4. Mapa de dependencias entre roles

```text
D: contratos (0.1) ──→ desbloquea a A, B y C
D: hub WS (1.1)    ──→ A emite (2.6), B escucha (1.4)
A: fixtures (1.7)  ──→ C trabaja sin esperar al engine
A: proyección (2.5)──→ B reconexión (5.2) y polling
C: composer (2.7)  ──→ B ve UISpecs reales (2.8)
A: pausa (3.1)     ──→ D policy (3.3) ──→ B decisionPanel final (3.7)
A: versiones (4.1) ──→ B editor (4.4)
A+C: executor (4.2/4.3) ──→ gate H17
```

Regla: si tu dependencia no llegó, **mockeas y sigues** — nadie espera a nadie más de 30 minutos sin avisar a D.

## 5. Tablero de gates (para imprimir y pegar en la mesa)

| Gate | Hora | Pregunta única | Si NO |
|---|---|---|---|
| G1 | H3 | ¿Un click viaja WS → renderer → ActionEvent → log? | Polling; cerrar skeleton H4 |
| G2 | H8 | ¿Golden path de 5 pasos con UI determinista? | Cortar LLM composer |
| G3 | H13 | ¿Decisión humana cambia el run + inspector + rechazo? | Cortar editor visual |
| G4 | H17 | ¿Paso inventado por D se ejecuta y renderiza? | Trial-by-fire al video |
| G5 | H20 | ¿Fallbacks probados y freeze declarado? | Recortar guion de demo |

---

> **Regla final:** este roadmap se modifica solo en el decision log, con la firma de D. La discusión ya ocurrió — en el brief y en la revisión crítica. Ahora se ejecuta.
