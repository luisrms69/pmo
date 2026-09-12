# CONTINUITY.md — pmo

**Fecha:** 2026-09-11
**Rama activa:** `feat/pmo-reporting-architecture` (base `version-16` @ v0.15.0; ADR-0011 en `ba1070f`, Reporte Ejecutivo v1 en `bf57b19`)
**Tarea actual:** Planning Maturity + tareas sin responsable (sobre `build_project_control`) — recién commiteado.

---

## Recuperación rápida

Estoy trabajando en:
La **arquitectura de reporting canónica de Project Control** (ADR-0011). El Reporte Ejecutivo vive en la
Page `PMO Control de Proyecto` (pestaña) con **un builder único** (`build_project_control`) y **un template
único** (`executive.html`) compartido con el Print Format. Este bloque añadió la sección `planning`.

Plan que estoy siguiendo:
ADR-0011 + matriz de secciones acordada con el usuario. Bloques por dominio, uno a la vez, con gate de
no-duplicación antes de cada commit.

Objetivo inmediato:
Bloque de Planning Maturity commiteado. Nos **detenemos**; el siguiente bloque requiere autorización.

Criterio de avance:
Commit con código+tests+i18n+docs+CONTINUITY; `one_offs/` (seed DEMO) fuera de git; working tree limpio.

---

## Estado actual

### Ya cerrado
- ADR-0011 (`ba1070f`); Reporte Ejecutivo v1 (`bf57b19`).
- **Planning Maturity + tareas sin responsable** (este bloque): sección `planning` en
  `build_project_control` + template + excepción visible; responsable = **ToDo Open** (no `!= Cancelled`).
- Dataset DEMO en `pmo-v16.dev`: **PROJ-0008 "DEMO-UI Control Center"** (imperfecto a propósito), sembrado
  por `one_offs/seed_demo_control.py` (idempotente con teardown, **gitignored**, dev-only).
- Auditoría de no-duplicación: sin duplicación material; único candidato futuro = `planned_hours`.
- Tests: `test_project_control` 18/18; suite completa 246+41 OK.

### Pendiente inmediato
1. Validación visual del Reporte Ejecutivo en PROJ-0008 (Page, `pmo-v16.dev` 8412) — la hace el usuario.
2. `/ship push` + `/ship pr` (bump SemVer vs `upstream/version-16`; el conjunto de la rama añade
   funcionalidad → **MINOR**, objetivo tentativo `0.16.0`; recalcular al momento del PR).
3. Siguiente bloque **solo con autorización** (interno: Capacity/RRHH/costos; luego HTML/PDF export; Portal).

### No repetir / no ampliar
- No extraer `planned_hours` ahora (cleanup futuro, solo si se toca `pmo_portfolio`).
- No segunda fuente de verdad; todo entra por `build_project_control` (ADR-0011).
- No incluir Project Updates (diferido: DocType nativo débil).

---

## Decisiones vigentes
- **Responsable vigente = ToDo `Open`** (semántica nativa; más estricto que `_has_active_todo`=`!=Cancelled`,
  que es para visibilidad). Un ToDo Closed no cuenta como responsable; una tarea Completed no es alerta.
- **Planning Maturity** = promedio simple de los componentes **evaluables** (None excluido; ninguno → None)
  de 5 métricas sobre hojas (responsable/inicio/fin/estimación/en baseline vigente). Denominadores
  explícitos; comp. baseline = None sin baseline; tareas creadas tras la baseline bajan la cobertura (drift).
- **Horas reales del reporte** = `indicators.actual_hours_to_date` (Timesheet ≤ corte). `planned_hours` =
  Σ `Task.expected_time` hojas (repetida en `_effort_totals`; consolidación futura, no bloqueante).
- `audience` (internal/portal) filtra exposición server-side, nunca permisos (P4 por el motor).

---

## Archivos relevantes ahora
### Leer primero
- `pmo/project_control.py` — builder canónico (secciones project/executive/schedule/planning/scope_changes).
- `pmo/templates/project_control/executive.html` — template único.
- `pmo/health.py` — salud canónica.
### Fuera de git (no commitear)
- `one_offs/seed_demo_control.py` — seed DEMO dev-only (reproducible con teardown).

---

## Riesgos / cuidados
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Tras i18n/build → `clear-cache` para que el servidor tome traducciones nuevas.
- El seed de PROJ-0008 hace teardown de sus dependientes (solo de ese proyecto) antes de reconstruir.

## Información faltante
- Ninguna para continuar; el siguiente bloque depende de la autorización del usuario.
