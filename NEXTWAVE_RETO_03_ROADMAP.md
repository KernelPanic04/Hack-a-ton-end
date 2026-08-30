# NextWave 2026 · Challenge 03 — Roadmap ejecutable y roles (v2)

> **v2 — actualizado tras la auditoría de código de ambos repos y la definición del caso final "Muebles del Sur / Ari".** Las fases 0–4 del v1 están mayormente construidas (ver sección 3); este documento las comprime en una tabla de estado y detalla las fases restantes hacia el producto final. El v1 completo vive en el historial de git.
>
> **Cómo usarlo:** igual que siempre — cada persona lee su rol (sección 2) y su columna en cada fase (sección 4). Lane D administra los gates y los kill criteria.

## 1. Reglas del roadmap (sin cambios)

- `main` demostrable siempre; merge obligatorio en cada gate.
- Cada fase tiene **DoD**: si no se cumple, se aplica el kill criteria — no se "estira" la fase.
- Presupuesto restante estimado: **~14–16 horas útiles** entre 4 personas. Reloj relativo `R0…R14` (R0 = próxima sesión de trabajo).
- Cambios de contrato solo con firma de D (adenda v1.1, ver 4.A).

## 2. El caso final (norte de la demo)

**Muebles del Sur** — importador de muebles Vietnam → México. **Ari** es el agente que gestiona bookings y monitorea embarques.

| Momento | Guion | Lo que el jurado ve |
|---|---|---|
| M1 | Llega email de Booking Confirmation; Ari extrae carrier, buque, puertos, ETD/ETA, contenedores y crea la operación | **La interfaz nace**: mapa con la ruta Vietnam → México, card del booking, contenedores |
| M2 | El buque zarpa; nuevo run de monitoreo | El front cambia solo: posición del buque en el mapa, contenedores "en tránsito" |
| M3 | Transbordo no planeado, ETA +9 días | El mapa redibuja la ruta y aparece el panel de decisión: **esperar / buscar alternativa / notificar al cliente final** |
| M4 (trial) | El jurado agrega un paso al flow (ej. "validar el BoL contra el booking antes de confirmar") | La interfaz lo refleja sola, sin reiniciar nada |

Transversal a los 4 momentos: **el chat de Ari** — panel conversacional que explica el estado, recomienda opciones (chips que disparan acciones reales) y puede proponer el paso nuevo del trial.

## 3. Estado actual (auditoría, código real en `dev`)

| Fase v1 | Estado | Evidencia / hueco |
|---|---|---|
| 0 Congelamiento (0.1–0.7) | ✅ | Contratos en `app/schemas/contracts.py` + `src/runtime/contracts.ts`; registry de 9 tipos; fixture; DECISION_LOG |
| 1 Walking skeleton (1.1–1.8) | ✅ | Hub WS, `/demo/skeleton`, Renderer+registry, `useRunSocket`, tablas, composer v0 |
| 2 Golden path (2.1–2.11) | ✅ | Flow versionado, reducer, mock provider guionizado, `/demo/advance`, snapshot, composer determinista con layouts distintos |
| 3 Loop humano + LLM (3.1–3.10) | ✅ | Pausa `DECISION_REQUIRED`, policy declarativa + rechazos, `LLMComposer` (Responses API, structured output, timeout 5s), `generatedBy`/`reason`, inspector, polling fallback |
| 4 Trial-by-fire backend (4.1–4.3, 4.7) | ✅ | `POST /workflows/{id}/versions`, generic step executor determinista + LLM, export de eventos |
| 4.4 Editor en el front | ❌ | No existe `src/editor/`; hoy el trial se hace por PowerShell/curl (`STEP_4_5_TRIAL_BY_FIRE.md`) — inaceptable para demo en vivo |
| 4.6 Ensayo del trial | ❌ | Pendiente |
| 5–6 Freeze + entrega | ❌ | Pendiente |

**Huecos nuevos que el caso final expone (no estaban en v1):**

1. **Mapa** — no existe ningún nodo geográfico en el registry (9 tipos, ninguno de mapa) ni coordenadas en el fixture. M1, M2 y M3 dependen de él.
2. **Fixture con la ruta equivocada** — hoy el golden path va Valparaíso → Rotterdam. El caso es Vietnam → México. Solo toca `demo/fixture.py` (los strings de dominio ya viven confinados ahí — el grep de honestidad sigue pasando).
3. **Tercera opción de decisión** — la policy tiene `act_find_alternative` y `act_accept_delay`; falta `act_notify_client` con su outcome guionizado.
4. **Evolución entre runs** — el reto pide "UI evoluciona a través de runs sucesivos" y el guion habla de Run 1/2/3. Hoy todo pasa dentro de un solo run avanzado por el driver. Falta que cada momento sea un run nuevo sobre la misma operación.
5. **Chat de Ari** — no hay superficie conversacional en el front; el LLM solo llega como layout re-ordenado + badge en el inspector. La única entrada humana es el click en `decisionPanel`.
6. **Dashboard.tsx** es un placeholder hardcodeado — se recorta del guion o se cablea al final (decisión de D).

## 4. Fases restantes

### Fase 4.A · R0–R1 — Adenda de contratos v1.1 (todos en una mesa, como H0)

| # | Paso | Responsable |
|---|---|---|
| A.1 | Congelar nodo **#10 `map`**: props genéricas — `waypoints: [{id, label, lat, lon, kind: origin\|stop\|destination}]`, `marker?: {lat, lon, label}` (posición actual), `segments: [{from, to, status: planned\|active\|diverted}]`, `emphasis`. Sin strings de dominio en el contrato (nada de "vessel") | D escribe, B y C firman |
| A.2 | Congelar contrato del asistente **fuera** del envelope WS congelado: `POST /runs/{id}/assist` con `AssistRequest {message, history[]}` / `AssistResponse {reply, recommendedActions: [{actionId, rationale}], proposedStep?: StepDefinition}` | D |
| A.3 | Regla de composición del mapa: el composer emite `map` cuando los datos del paso traen waypoints/coordenadas — detección por forma de datos, no por nombre de paso | C valida |
| A.4 | Alta de `act_notify_client` en `ACTION_POLICIES` (risk low) + registrar la adenda en `DECISION_LOG.md` | D |

**DoD R1:** adenda mergeada en ambos repos (Pydantic + TS + schemas JSON regenerados), sin romper tests existentes.

### Fase 4.B · R1–R5 — Momentos M1–M3 (retheme + mapa + multi-run)

| # | Paso | Responsable |
|---|---|---|
| B.1 | Retheme de `demo/fixture.py`: booking BK-4471 Cái Mép (Vietnam) → Manzanillo (México), buque inventado, 3 contenedores con IDs, ETD/ETA, transbordo no planeado (ej. Busan) con +9 días; **coordenadas** en los datos de cada evento; email de booking con campos parseados (carrier, buque, puertos, ETD/ETA, contenedores) para la card de M1 | A |
| B.2 | Outcome guionizado de `notify_client` en `DECISION_OUTCOMES` (ETA se mantiene +9, cliente notificado, riesgo bajo) y `wait`≙`accept_delay` con label "Esperar" | A |
| B.3 | **Multi-run**: `POST /demo/moment/{n}` — crea un run nuevo de la misma operación auto-avanzado hasta el momento n (mismo patrón que `/demo/skeleton`); `operationId` compartido en la proyección para que el front liste la historia | A |
| B.4 | Componente `map` en el ui-kit: SVG inline (proyección equirectangular, sin tiles externos → sigue funcionando sin red), ruta con estados planned/active/diverted, marker animado, énfasis warning/critical al desviarse | B |
| B.5 | Panel de historia de runs en `Demo.tsx`: los runs previos de la operación quedan listados/accesibles — evidencia visible de "la UI evoluciona entre runs" | B |
| B.6 | Composer determinista: regla genérica de mapa (A.3) + booking card (`keyValue`) + sección de contenedores en M1; layout M2 con `map` + `metric`; layout M3 con `map` desviado + `alert` + `decisionPanel` de 3 acciones | C |
| B.7 | Prompt del `LLMComposer` actualizado para que el upgrade pueda reordenar jerarquías con `map` presente (el mapa nunca se elimina en un upgrade) | C |
| B.8 | Integración R4: correr M1→M2→M3 completo entre los 4 | D |

**DoD R5 (GATE GR1):** los tres momentos se demuestran con runs separados, mapa vivo y decisión de 3 opciones aplicada. **Kill criteria:** si el mapa no respira en R4, M1–M3 se demuestran con "route card" (`timeline` + `keyValue` de puertos) y el mapa sale del alcance — nadie lo menciona en la defensa.

### Fase 4.C · R5–R9 — Ari: chat asistente + editor del trial

> Regla de seguridad no negociable: la key de OpenAI **nunca** viaja al front. El front consume `POST /runs/{id}/assist`; el backend arma el contexto y llama a Responses API reutilizando la plomería de `synthesis/llm.py`.

| # | Paso | Responsable |
|---|---|---|
| C.1 | `POST /runs/{id}/assist`: contexto = `RunProjection` + últimos N eventos + `availableActions` de la decisión pendiente; structured output estricto (`AssistResponse`); timeout 5 s, un retry, kill switch `ASSISTANT_ENABLED` | A (endpoint) + C (prompt/schema) |
| C.2 | Persona de Ari en el prompt: explica el estado del embarque, recomienda una de las `availableActions` con rationale, y solo puede recomendar acciones que la policy acepta (el schema copia los actionIds válidos, mismo patrón que `llm_upgrade.py`) | C |
| C.3 | `AssistantPanel` en el front: panel lateral junto al Renderer — hilo de mensajes, input, y **chips de acción recomendada que llaman a `runtime.submitAction`** (la recomendación de Ari dispara el `ACTION_SUBMITTED` real → policy → UI se reestructura por WS) | B |
| C.4 | `proposedStep`: si el usuario le pide a Ari un paso nuevo (ej. "valida el BoL contra el booking"), la respuesta incluye un `StepDefinition`; el panel muestra el diff y un botón "Crear v(n+1) y correr" → `POST /workflows/{id}/versions` + `POST /runs` | A + B |
| C.5 | `editor/`: formulario mínimo del v1 (title, objective, inputs como picker de claves del estado, requiresHumanReview) — es la **ruta garantizada** del trial; el chat de C.4 es el "wow", el editor es el plan B en la misma pantalla | B |
| C.6 | Paso de ensayo "validar BoL contra booking": datos de BoL inventados en el estado de la operación (B.1) para que el generic step executor tenga qué comparar → nodo `compare` real en pantalla | A + C |
| C.7 | Integración R8: trial completo desde la UI — por chat y por editor — sin tocar una terminal | D |

**DoD R9 (GATE GR2):** (a) Ari responde en el panel, recomienda una acción y el chip ejecuta la decisión real con feedback inmediato; (b) el paso inventado se crea desde la UI (chat o editor) y el siguiente run lo ejecuta y renderiza. **Kill criteria:** si el chat libre no converge en R8, el panel queda **solo-recomendaciones** (sin input libre: Ari comenta cada transición y ofrece chips) — sigue cumpliendo "human inputs alter agent decisions". Si el editor tampoco llega, el trial vuelve al video de respaldo (kill del v1).

### Fase 5 · R9–R12 — Freeze, fallbacks y pulido (v1 + nuevos)

| # | Paso | Responsable |
|---|---|---|
| 5.1 | Fallbacks: sin key (`LLM_UPGRADE_ENABLED=false`, `ASSISTANT_ENABLED=false`) → demo completa determinista con panel oculto; matar WS → polling; sin red → todo local incluido el mapa SVG | A + C |
| 5.2 | Reconexión a mitad de run + historia de runs sobrevive refresh | B |
| 5.3 | Dos horas de pulido visual: transición de 200 ms al reestructurar, animación del marker del mapa, estados vacíos del chat | B |
| 5.4 | Grep de honestidad ampliado: `grep -i "booking\|vessel\|bol\|muebles\|ari" app/synthesis/ src/runtime/` vacío (dominio solo en `demo/` y en textos que vienen del provider) | C + A |
| 5.5 | Decidir Dashboard.tsx: cablear con datos de la operación o sacarlo de la navegación | D |
| 5.6 | Deploy Railway solo si todo respira; demo oficial local; limpieza de repo | D |

**DoD R12 (GATE GR3):** freeze absoluto; cualquier cambio posterior = bugfix aprobado por D.

### Fase 6 · R12–R14 — Entrega y ensayos (igual que v1, con guion nuevo)

| # | Paso | Responsable |
|---|---|---|
| 6.1 | Ensayo 1 cronometrado del guion M1→M4 con Ari; lista de tropiezos | Todos, D dirige |
| 6.2 | Video de respaldo en ensayo 2 (pantalla + narración) | D |
| 6.3 | Slides: north star, diagrama, los 4 momentos, la frontera de autoridad del LLM (layout sí, estado no; recomendaciones sí, ejecución solo vía policy), decision log | D + B |
| 6.4 | "Loop en 60 segundos" de memoria, cada uno | Todos |
| 6.5 | Ensayo 3: A hace de juez e inventa el paso del trial en el momento, por el chat de Ari | Todos |
| 6.6 | Revisión final del repo público: README, diagrama, DECISION_LOG, export del event log | D |

## 5. Objetivos nuevos por rol (se suman a los del v1 ya cumplidos)

- **Rol A (Runtime):** multi-run por operación (B.3), retheme + outcomes (B.1/B.2), endpoint assist (C.1), datos de BoL para el trial (C.6).
- **Rol B (Interface):** componente `map` (#10) (B.4), historia de runs (B.5), `AssistantPanel` con chips de acción (C.3/C.4), `editor/` (C.5), pulido (5.3).
- **Rol C (Synthesis):** regla genérica de mapa en composer (B.6), prompt de upgrade con mapa (B.7), persona y structured output de Ari acotado a acciones válidas (C.1/C.2), grep de honestidad ampliado (5.4).
- **Rol D (Integration):** adenda de contratos v1.1 (A.1–A.4), policy `act_notify_client`, gates GR1–GR3, guion de demo de los 4 momentos, entregables.

## 6. Mapa de dependencias actualizado

```text
D: adenda v1.1 (A.1–A.2) ──→ desbloquea B.4 (map), C.1 (assist), B.6 (composer map)
A: fixture retheme (B.1) ──→ B.6 layouts M1–M3 y C.6 datos de BoL
A: multi-run (B.3)       ──→ B.5 historia de runs
A: assist endpoint (C.1) ──→ B: AssistantPanel (C.3)
C: proposedStep (C.4)    ──→ B: botón crear v(n+1); fallback: editor (C.5) no depende de C
```

Regla intacta: si tu dependencia no llegó, mockeas y sigues — nadie espera más de 30 minutos sin avisar a D.

## 7. Tablero de gates v2

| Gate | Reloj | Pregunta única | Si NO |
|---|---|---|---|
| GR1 | R5 | ¿M1–M3 con runs separados, mapa vivo y decisión de 3 opciones? | Route card sin mapa; mapa fuera del alcance |
| GR2 | R9 | ¿Ari recomienda y ejecuta por chip + trial desde la UI? | Panel solo-recomendaciones; trial por editor; si no, video |
| GR3 | R12 | ¿Fallbacks probados (sin key, sin WS, sin red) y freeze? | Recortar guion de demo |

---

> **Regla final:** este roadmap se modifica solo en el decision log, con la firma de D. La v2 queda registrada ahí como decisión de alcance del caso final.
