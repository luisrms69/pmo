# CONTINUITY.md — pmo

**Fecha:** 2026-09-11
**Rama activa:** `feat/pmo-reporting-architecture` (base `version-16` @ v0.15.0, commit `ba1070f` con ADR-0011)
**Tarea actual:** Reporte Ejecutivo v1 sobre la arquitectura canónica de ADR-0011 — recién commiteado.

---

## Recuperación rápida

Estoy trabajando en:
La **arquitectura de reporting canónica de Project Control** (ADR-0011). B1 (pestaña embebida en Project)
fue **abandonado**; el reporte vive ahora en la Page `PMO Control de Proyecto` como pestaña **Reporte
Ejecutivo**, con un **builder único** (`build_project_control`) y un **template único** (`executive.html`)
compartido con el Print Format `PMO Project Status`.

Plan que estoy siguiendo:
ADR-0011 (`docs/adr/0011-project-control-canonical-context.md`) + matriz de secciones acordada con el
usuario. Bloques por dominio, uno a la vez.

Objetivo inmediato:
v1 commiteado. Nos **detenemos** antes del siguiente bloque (autorización explícita del usuario).

Criterio de avance:
Commit v1 con los archivos del builder/template/Page/tests/docs + i18n; working tree limpio.

---

## Estado actual

### Ya cerrado
- **ADR-0011** versionado (`ba1070f`).
- **Reporte Ejecutivo v1** implementado y commiteado: `build_project_control` (secciones project/executive/
  schedule/scope_changes) + `executive.html` + 5ª pestaña en la Page (endpoint `get_executive_html`) +
  Print Format como consumidor + `pmo_project_status` como wrapper.
- **Fuente única de salud** `pmo/health.py` (pmo_portfolio re-exporta).
- **Corrección de horas**: reporte usa `indicators.actual_hours_to_date` (Timesheet ≤ corte), no el acumulado.
- Tests: `test_project_control` 12/12; suite completa 240+41 OK (1 skip PDF). Lint limpio.
- Limpieza en dev: eliminados los 2 Custom Fields residuales de B1 en `pmo-v16.dev` y `test-pmo.localhost`.
- `feat/pmo-project-control-b1` **congelada** en `26c7dbb` (no tocar).

### Pendiente inmediato
1. Validación GUI: abrir la Page en `pmo-v16.dev` (8412), pestaña Reporte Ejecutivo (con/sin baseline) y
   confirmar que las 4 pestañas previas siguen operando.
2. `/ship push` + `/ship pr` (bump SemVer vs `upstream/version-16`; v1 añade funcionalidad → MINOR).
3. Siguiente bloque **solo con autorización** (bloque interno: Capacity/RRHH/costos; luego tareas sin
   responsable + Planning Maturity; después HTML/PDF export y Portal).

### No repetir / no ampliar
- No reintroducir la pestaña embebida en Project, Custom Fields, ni `get_header`.
- No crear un segundo builder ni HTML paralelo (ADR-0011: un builder, un template, muchos consumidores).
- No incluir Project Updates en v1 (diferido: el DocType nativo es débil, sin % ni narrativa consolidada).

---

## Decisiones vigentes
- **Contexto canónico único** `build_project_control()`; vistas = consumidores (ADR-0011).
- **Horas reales del reporte** = `actual_hours_to_date` (gobernado por corte). `Project.actual_time` solo
  para contextos sin corte. Nunca `Σ Task.actual_time` como fuente canónica.
- **`audience`** (internal/portal) filtra exposición server-side, NUNCA permisos (P4 la impone el motor).
  `portal` oculta Change Requests en `Draft`.
- **KPI renombrado**: `tasks_due_by_cutoff_pct` = "Tareas previstas al corte" (no "avance esperado").
- **Costos**: al abordarlos, usar nativos de Project; NO llamar "original" a `estimated_costing` (definir
  fuente congelada antes).
- Builder devuelve `frappe._dict` en profundidad (dot-access en render_template y printview).

---

## Archivos relevantes ahora
### Leer primero
- `pmo/project_control.py` — builder canónico + endpoint.
- `pmo/templates/project_control/executive.html` — template único.
- `pmo/health.py` — salud canónica.
### No tocar
- `feat/pmo-project-control-b1` (rama congelada).

---

## Riesgos / cuidados
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Tras i18n/build, `clear-cache` para que el servidor tome traducciones nuevas.
- El bump de versión del PR se calcula contra `upstream/version-16`, una sola vez, antes del PR.

## Información faltante
- Ninguna para continuar; el siguiente bloque depende de la autorización del usuario.
