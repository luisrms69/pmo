# CONTINUITY.md — pmo

**Fecha:** 2026-08-16
**Rama activa:** `feat/task-gantt-lft-and-tag-import` (base `version-16`)
**Tarea actual:** pmo **0.1.0** — Gantt de Task por `lft` + importador de Tags nativos por CSV. Commit de la rama.

---

## Recuperación rápida

Estoy trabajando en:
`/ship commit` de **0.1.0** en `feat/task-gantt-lft-and-tag-import`. Dos capacidades implementadas,
validadas visualmente en `proposals.dev` y con 19/19 tests OK.

Plan que estoy siguiendo:
Tarea de sesión: implementar (A) Gantt de Task ordenado por `lft ASC` y (B) importador de Tags nativos
por CSV. Ver `docs/adr/0001-gantt-lft-y-tag-import.md`.

Objetivo inmediato:
Tras el commit: `/ship push` (autorización aparte) → `/ship pr` (base `version-16`).

Criterio de avance:
Cada paso git con autorización explícita separada; commit/push/pr solo vía `/ship`.

---

## Estado actual

### Ya cerrado
- Implementación de ambas capacidades + tests (19/19 OK en `test-pmo.localhost`).
- Validación funcional visual en `proposals.dev`: Gantt ordena por `lft` (ramas juntas); importador
  Dry Run/Apply/idempotencia/todo-o-nada; Tags nativos sin Custom Fields.
- Docs: ADR-0001, `docs/tecnico/arquitectura.md`, `docs/usuario/importar-tags.md`, CHANGELOG 0.1.0.

### En progreso
- Commit de la rama (este `/ship commit`).

### Pendiente inmediato
1. `/ship push` (autorización aparte).
2. `/ship pr` a `version-16`.
3. `required_status_checks` del ruleset de `pmo` cuando el CI corra por primera vez.
4. Limpiar datos demo en `proposals.dev`: `Project PROJ-0040` "PMO DEMO GANTT" + Tasks `PMO-DEMO *`
   (requiere autorización de escritura en BD).

### No repetir
- No escribir en BD sin autorización explícita (ya ocurrió por error al sembrar datos demo).
- Rutas del Desk en v16 son `/desk/...`, nunca `/app/...`.
- Git solo vía `/ship`; nunca trabajar en `version-16`.

---

## Decisiones vigentes
- **Gantt por `lft`:** vía `doctype_calendar_js` + `gantt.order_by="lft"` (nativo, sin core, solo Task > Gantt). Las flechas del Gantt son dependencias nativas (`depends_on_tasks`), ajenas.
- **Tag import:** API nativa `add_tags`; validación global todo-o-nada; Dry Run sin escritura; idempotente. Sin SQL directo ni Custom Fields.

---

## Archivos relevantes ahora

### Leer primero
- `pmo/tag_import.py` — lógica del importador (dry run / apply / detalle).
- `pmo/public/js/task_calendar_pmo.js` + `pmo/hooks.py` — Gantt por `lft`.
- `pmo/pmo/page/tag_import/` — Page administrativa.

### No tocar
- Core de ERPNext/Frappe. Datos de cliente. `.claude/` (local, no se commitea).

---

## Riesgos / cuidados
- `bench migrate` global en `proposals.dev` falla por un fixture (`custom_field.json`) de **otra app**
  (`DocumentLockedError`) — **ajeno a pmo**; su schema se instaló vía `install-app`.
- Datos demo en `proposals.dev` **sin limpiar** (a propósito, para validación visual del usuario).
