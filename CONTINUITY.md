# CONTINUITY.md — pmo

**Fecha:** 2026-09-08
**Rama activa:** `feat/status-date` (base `version-16` @ v0.6.1, commit `18d30c2`).
**Ciclo:** v0.7.0 — Control a fecha de corte / Status Date (ADR-0006, Proposed).

## Plan que estoy siguiendo
`docs/adr/0006-status-date.md` (ADR-0006). Entrega por bloques hacia un PR único a `version-16`.
Bump `__version__ → 0.7.0` (MINOR) pendiente **antes del PR** (aún no aplicado).

## Estado por bloques
- **Bloque 1 — Status Date persistente + validación. ✅ (commit en curso)**
  - Custom Field `Project.pmo_status_date` (Date, fixture; `bench migrate` requerido — corrido en
    `test-pmo.localhost`, exit 0). `doc_events` `Project.validate` → `pmo.status_date.validate_project_status_date`
    (D2: rechaza fecha futura; vacío válido). Tests `test_status_date.py` (4). **Suite 195/195.**
- **Bloque 2 — Motor (siguiente).** `pmo/status_date.py`: composición Baseline (`get_effective_baseline`
  as_of) + Current (`build_snapshot`) + Actual (Timesheet a fecha, `pmo/actual.py`) + indicadores D5.
  Whitelisted P4 + tests. **No** Planned-vs-Actual de horas (diferido), **no** regla todo-o-nada.
- **Bloque 3 — Reporte P4-safe `PMO Status Report`** + UX + docs usuario/técnico + tests.

## Decisiones vigentes (ADR-0006, resumen)
- Status Date vive en `Project.pmo_status_date` (un valor; sin DocType ni historial). Solo `<= today` en v0.7.0.
- Baseline vigente a la fecha = `get_effective_baseline(project, status_date)` (ADR-0004, sin modificar 0004).
- Current = plan de hoy evaluado contra el corte (NO reconstruye plan histórico).
- Actual = Timesheet fechado (fiable) + `completed_on <= status_date` (proxy). Sin % histórico.
- Indicadores D5: (1) deslizamiento de fecha final Baseline vs Current (días); (2) tareas que debían estar
  terminadas a la fecha y no lo estaban; (3) Actual hours acumuladas a la fecha; (4) conteos simples fiables.
- Fuera: EVM, forecast, CPM (#9), reservas de capacidad (#10), Planned-vs-Actual completo, fecha futura.

## Cuidados / no repetir
- Git solo vía `/ship`. Nunca trabajar en `version-16`. En pmo NO se usan migration patches.
- **pmo NO usa MkDocs** (no hay `mkdocs.yml`): no usar `mkdocs build --strict` como gate aquí.
- `test-pmo.localhost` tiene 0 Companies → tests que requieran Company deben skip o probar la lógica pura.
- BD / `bench migrate`: autorización explícita. Tests en `test-pmo.localhost`.
