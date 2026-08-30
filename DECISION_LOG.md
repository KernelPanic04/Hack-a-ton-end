# Decision Log — Kernel Panic / Challenge 03

Formato: fecha, decisión, alternativas consideradas, razón, responsable, consecuencias.

---

## 2026-08-29 — Roadmap v2 y adenda de contrato para momentos M1–M3

**Decisión:** adoptar `NEXTWAVE_RETO_03_v2_ROADMAP.md` como el plan posterior a
las fases 0–4 del v1. La adenda v1.1 incorpora el nodo declarativo `map`, el
identificador compartido `operationId` y la acción `act_notify_client` para el
caso Muebles del Sur Vietnam → México.

**Alternativas consideradas:** mantener las nueve primitivas originales y
simular la ruta con `keyValue`, o dejar los tres momentos dentro de un único
run. Descartadas: no prueban mapa ni evolución de la interfaz entre runs que
pide el caso final.

**Razón:** el nodo se mantiene genérico (waypoints, marker y segments) y no
entrega autoridad al LLM; el backend valida toda UISpec y conserva las acciones
permitidas. Cada momento se puede crear como un run separado de la misma
operación mediante `/demo/moment/{n}`.

**Responsable:** D, con implementación backend A/C para 4.A–4.B.

**Consecuencias:** el frontend debe actualizar su espejo TypeScript y registry
para renderizar `map` antes de GR1. Con mapa presente, un upgrade LLM que lo
omita se rechaza y queda visible la UISpec determinista.

---

## 2026-08-29 — Eliminar módulo de usuarios/auth del backend

**Decisión:** eliminar por completo el CRUD de `users`, el módulo duplicado `user_test`
(login sin contraseña), `auth_controller.py` (login/register con `AUTH_USER_MODE`) y
`app/core/security.py` (hashing de contraseñas). Se limpiaron las referencias en
`main.py` (seeding de `FAKE_USERS`, `ALTER TABLE` de compatibilidad) y `requirements.txt`
(`pwdlib`).

**Alternativas consideradas:**
- Dejar el módulo `users` y solo borrar `user_test` (duplicado). Descartada: ningún
  paso del roadmap usa login de usuarios; el único mecanismo de auth previsto es un
  `DEMO_TOKEN` estático en el handshake del WS (paso 1.1, propiedad de Rol D).
- Desconectar los routers de `main.py` sin borrar archivos. Descartada: deja código
  muerto que confunde sobre qué es parte del producto real.

**Razón:** el north star del reto es un runtime de agente con UI generativa, no un
sistema de usuarios. Mantener ese boilerplate (heredado de un template genérico de
hackathon) no aporta a ningún gate (H3/H8/H13/H17/H20) y compite por foco con el
trabajo real de Rol A (`flow/`, `runtime/`, `demo/`, tablas de run, endpoint de
snapshot).

**Responsable:** Rol A (equipo de 2 personas a cargo de runtime).

**Consecuencias:**
- `main.py` queda como esqueleto mínimo (FastAPI + CORS + lifespan + `/health`).
- Si más adelante se necesita autenticación real de usuarios (no `DEMO_TOKEN`), se
  vuelve a introducir como decisión explícita, no por herencia del template.
- `app/schemas/contracts.py` (RunProjection, UISpec, ActionEvent, RunEvent, envelope
  WS) sigue pendiente de congelamiento formal por Rol D (paso 0.1 del roadmap). Se
  crea un borrador de trabajo en este PR para no bloquear a Rol A; debe tratarse como
  no definitivo hasta que D lo firme.

## 2026-08-29 · Roadmap v2 — caso final "Muebles del Sur / Ari"

- **Decisión:** se adopta el caso final (booking Vietnam → México, agente Ari) y se actualiza `NEXTWAVE_RETO_03_ROADMAP.md` a v2 con las fases restantes 4.A–6.
- **Adenda de contratos v1.1 (implementada 2026-08-30, pasos A.1/A.2/A.4):** nodo #10 `map`
  (`MapProps` con waypoints/segments/marker genéricos, validador de referencias) en
  `app/schemas/contracts.py` + espejo TS + JSON Schemas regenerados; contratos
  `AssistRequest`/`AssistResponse` (HTTP-only, `proposedStep` reutiliza `StepDefinition`);
  `act_notify_client` (risk low) en `ACTION_POLICIES`. Test de conteo congelado
  actualizado 9→10. Suites verdes: backend 59 pass, frontend 28 pass + tsc.
  Pendiente de A.3 (regla de composición del mapa) para que el composer lo emita.
- **Alternativas consideradas:** (a) extender el envelope WS con mensajes de chat — descartado, rompería el contrato congelado; (b) llamar a OpenAI desde el front — descartado, expondría la key en el bundle; (c) mapa con tiles externos — descartado, rompe el fallback sin red; se usa SVG inline.
- **Kill criteria nuevos:** mapa → route card; chat libre → panel solo-recomendaciones; trial desde UI → editor mínimo → video de respaldo.

## 2026-08-30 · A.3 — regla de composición del mapa (map node #10) operativa

- **Problema:** el composer tenía la regla `_map` (emite `map` por forma de datos, no por nombre de paso), pero el fixture y los tests producían segmentos con claves `from`/`to`, mientras el contrato congelado `MapSegment` usa `fromId`/`toId` con `extra="forbid"`. `MapProps.model_validate` fallaba y `_map` devolvía `None` en silencio → el mapa nunca se renderizaba (M1–M3 rotos). Test `test_route_shaped_operation_data_adds_a_map_node` en rojo.
- **Decisión (firma D):** estandarizar en `fromId`/`toId` (conforma los productores al contrato firmado en A.1; no se toca el contrato Pydantic ni se aliasa la palabra reservada `from`).
- **Cambios backend:** `demo/fixture.py` (4 segmentos), `tests/test_deterministic_composer.py`, `tests/test_llm_composer.py` → `fromId`/`toId`. Suite: 64 passed, honesty test verde.
- **Cambios frontend (consistencia de contrato + fin de fork paralelo de phase-4b):** `contracts.ts` `MapSegment`→`fromId`/`toId` y `MapProps.title` agregado (faltaba en el espejo); `validation.ts` chequeo semántico de waypoints→`fromId`/`toId`; `schemaExtensions.ts` `MapSegment`→`fromId`/`toId` + `title`; `registry.ts` dedupe de la entrada `map:` y del import duplicado (artefacto de merge); `runtime.test.tsx` fixtures→`fromId`/`toId`; JSON Schemas regenerados desde el contrato. `RouteMap.tsx` implementado como SVG inline offline (role=img, sin tiles) para satisfacer los tests B.4 ya escritos. Suite front: 27 passed, tsc y oxlint limpios.
- **Nota:** PR #37 (equipo) ya resolvió el duplicado de contrato del asistente; no se tocó. La versión SVG de `RouteMap` cubre lo que los tests de phase-4b esperaban; el pulido visual pleno sigue siendo B.4 (Rol B).

---

## 2026-08-30 · Studio pasa de mockup estático a widgets reales (color, mapa, filtrado)

- **Decisión:** extender el registry de Studio (propio de `app/studio/schema.py`, sin tocar el contrato v1 congelado) con seis nodos nuevos — `searchBar`, `dropdown`, `chart` (bar/line/pie), `table`, `progress`, `tags` — y dar tres capacidades transversales que faltaban por completo: color explícito (`color`/`backgroundColor` hex, validado por regex, en `button`/`text`/`progress`/`tags`/`chart`/`page`/`section`), un mapa real (`map` reutiliza `RouteMap.tsx`/MapLibre del runtime heredado en vez del placeholder de texto plano que tenía Studio), y filtrado client-side (`filterTarget`/`filterColumn` en `searchBar`/`dropdown`, apuntando a un `table`/`tags` del mismo layout; corre 100% en el navegador vía `FilterContext`, sin round-trip).
- **Por qué llegó a esto:** pedidos directos del usuario en sesión — "quiero que mi UI genere gráficos/mapas/buscadores", "cuando pido cambiar de color no se ve el cambio", "el mapa no aparece", "el search bar no hace nada". Cada uno resultó ser un hueco real de capacidad, no un bug de wiring: no existía ningún prop de color en el schema; `map` nunca tuvo render visual, solo una lista de coordenadas; `searchBar`/`dropdown` eran inputs `disabled`/`readOnly` puramente decorativos.
- **Alternativas consideradas:** (a) dejar que el LLM "describa" el cambio de color solo en `reason` — descartada, es exactamente el bug reportado; (b) filtrado server-side (round-trip por tecla) — descartada, innecesaria para datos ya presentes en el layout y rompe la respuesta instantánea; (c) recolorear vía la paleta fija de `emphasis` en vez de hex libre — descartada, no cubre "ponlo azul", solo normal/warning/critical.
- **Consecuencias:** `app/studio/schema.py` gana un validador de árbol (`validate_tree_invariants`) que exige que `filterTarget` apunte a un nodo `table`/`tags` existente en el mismo layout — un id inventado o de tipo no filtrable se rechaza antes de llegar al frontend. Las instrucciones del LLM (`app/studio/llm.py`) se actualizaron para enseñarle cuándo usar cada capacidad nueva y para evitar un antipatrón real que produjo (una opción "Todos"/"all" redundante en dropdowns, que el filtrado interpretaría como valor literal). Suite: 26 tests de Studio, 100 backend en total.

## 2026-08-30 · Tabla de Studio: 50 → 250 filas, presupuesto de tokens y timeout subidos

- **Problema:** "tabla con todos los países del mundo" truncaba en silencio a 50 filas (alfabético A–E) por `TableProps.rows.max_length=50`; el buscador conectado (`filterTarget`) funcionaba perfectamente pero no encontraba nada fuera de ese rango, lo que se reportó como "el search bar no hace nada" — era un problema de datos, no de wiring (confirmado filtrando "Argelia", que sí estaba en las primeras 50, contra el JSON real generado).
- **Decisión:** subir `TableProps.rows` a `max_length=250` (cubre los ~195 países reales con margen), `max_output_tokens` de Studio 2400 → 6000 y `STUDIO_GENERATION_TIMEOUT_SECONDS` default 12 → 25, todo específico a `app/studio/llm.py` (no toca el composer del runtime heredado, que mantiene su propio 2400). Instrucciones del LLM actualizadas: llenar la lista completa cuando el prompt pida "todos los X" y el conteo real quepa en 250; la gráfica se queda topada en 20 puntos a propósito (un chart de 190 barras no es legible, sea cual sea el límite técnico).
- **Verificado en vivo:** el mismo prompt generó 192 países reales (A–Z) en ~11s, dentro del nuevo timeout; buscador confirmado funcionando sobre el rango completo (Uruguay, Venezuela, Vietnam, Zimbabue — los que antes faltaban).

## 2026-08-30 · Documentación: README reescritos para reflejar que Studio es la app viva

- **Problema:** ambos README (`Hack-a-ton-end` y `Hack-a-ton-front`) documentaban íntegramente el runtime de agente (landing/demo/editor/WebSocket) y no mencionaban Studio ni una vez, a pesar de que `App.tsx` del frontend renderiza únicamente `<Studio />` desde hace tiempo — no hay router, ninguna URL alcanza landing/demo/editor. Alguien nuevo en el proyecto habría seguido instrucciones para una app que ya no existe.
- **Decisión:** reescribir ambos README alrededor de la realidad actual (Studio vivo primero; runtime de agente documentado después, marcado explícitamente como código dormido — completo, probado, pero sin ruta desde el frontend). Se agregó `architecture.svg` en la raíz de este repo (cubre ambos repos: vivo vs. dormido, hasta qué tablas de Postgres y qué llamadas a OpenAI toca cada lado) y se enlazó desde ambos README.
- **Gaps concretos cerrados de paso (no solo documentados):** `STUDIO_GENERATION_ENABLED`/`STUDIO_GENERATION_TIMEOUT_SECONDS` se leían en código pero no existían en `.env.example` ni se pasaban en `docker/docker-compose.yml` — el flujo "todo con Docker" que el propio README recomienda primero no podía configurarlos. `VITE_MAP_TILE_URL` (frontend) estaba mal etiquetada como "solo runtime heredado" cuando Studio también la usa (`map` reutiliza `RouteMap.tsx`). `.env.test` (frontend) existía sin documentar en ningún lado.
- **Diferido, no implementado:** adoptar Alembic para migraciones (ver siguiente entrada) — cambia el proceso de deploy y requiere validarse contra la Postgres de producción real; se documentó como problema conocido con el fix manual, no se implementó sin confirmación explícita.

## 2026-08-30 · Problema conocido documentado: sin migraciones de esquema

- **Incidente:** `GET /studio/projects/{id}` respondía 500 en producción (Railway) con "CORS Missing Allow Origin" en el navegador — no era CORS: Starlette genera un 500 por excepción no manejada *fuera* de `CORSMiddleware`, así que esa respuesta nunca lleva el header, y el navegador lo reporta como error de CORS. La excepción real era `UndefinedColumnError: column studio_messages.suggestion does not exist` — la misma que ya había aparecido en el Postgres local de esta sesión (un volumen Docker de una corrida anterior a que `suggestion` se agregara a `StudioMessageModel`).
- **Causa raíz:** `main.py` solo llama `Base.metadata.create_all()` al arrancar, que crea tablas que faltan pero **nunca altera una tabla que ya existe**. Cualquier base (local o producción) creada antes de un cambio de modelo se desincroniza en silencio hasta que algo la toca y revienta.
- **Decisión:** documentar el problema y el fix manual (`ALTER TABLE studio_messages ADD COLUMN IF NOT EXISTS suggestion TEXT;`, corrido a mano contra Postgres local y de producción) en ambos README como troubleshooting de primera línea, en vez de adoptar Alembic sin más contexto. Sigue siendo la mejora pendiente más clara del proyecto — se repetirá con cualquier columna nueva mientras no se resuelva.
