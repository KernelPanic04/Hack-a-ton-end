# Decision Log — Kernel Panic / Challenge 03

Formato: fecha, decisión, alternativas consideradas, razón, responsable, consecuencias.

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
