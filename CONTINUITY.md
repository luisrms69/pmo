# CONTINUITY.md — pmo

**Fecha:** 2026-09-08
**Rama activa:** `feat/status-date` (base `version-16` @ v0.6.1, commit `18d30c2`).
**Ciclo:** v0.7.0 — Control a fecha de corte / Status Date (ADR-0006, **Accepted**). Cierre técnico → PR a `version-16`.

## Plan que estoy siguiendo
ADR-0006 (Accepted). Entrega por bloques (1–3) completada; cierre con bump 0.7.0 + CHANGELOG → PR único.

## Qué se implementó (v0.7.0)
- **Bloque 1** (`b4ef1d7`): Custom Field `Project.pmo_status_date` (fixture) + validación `<= today`
  (`doc_events Project.validate`). ADR-0006 (Proposed→Accepted en el cierre).
- **Bloque 2** (`c105794`): motor `pmo/status_date.py` — `build_status_report` (P4) compone Baseline as-of
  + Current + Actual (Timesheet fechado + `completed_on`) + indicadores D5. `compute_status` pura.
- **Bloque 3** (`93258df`): Script Report P4-safe `PMO Status Report` + UX (JS: default `pmo_status_date`,
  tope `today`) + docs usuario/técnico + tests de presentación.
- **Cierre** (este commit): ADR-0006 Accepted, `__version__` 0.6.1→0.7.0, CHANGELOG `[0.7.0]`.

## Validación
- Suite completa: **205/205**. Ruff + prettier limpios. (pmo NO usa MkDocs — sin gate mkdocs.)
- **E2E integrado en `proposals-acti.dev`** (Project+Tasks+Baseline Submitted+Timesheet Submitted):
  D5.1=11d, D5.2=1, D5.3=12h, D5.4=1/2, futura→ValidationError, sin-baseline→note, P4 outsider→PermissionError. **PASS.**

## Decisiones vigentes (ADR-0006)
- Status Date en `Project.pmo_status_date` (un valor, sin historial). Solo `<= today` en v0.7.0.
- Baseline vigente a la fecha = `get_effective_baseline(project, status_date)`. Current = plan de hoy (no
  reconstruye histórico). Actual = Timesheet fechado + `completed_on` (proxy). Sin % histórico.
- Fuera: EVM/forecast, CPM (#9), reservas de capacidad (#10), Planned-vs-Actual completo, fecha futura.

## Siguiente paso
`/ship commit` (cierre) → `/ship push` → `/ship pr` a `version-16`. Detenerse con el PR abierto y CI
evaluado. No merge/tag/release.

## Cuidados / no repetir
- Git solo vía `/ship`. Nunca trabajar en `version-16`. En pmo NO se usan migration patches.
- pmo NO usa MkDocs. `test-pmo.localhost` tiene 0 Companies (tests que requieran Company → E2E en site con
  Company, p. ej. `proposals-acti.dev`). BD/`bench migrate`: autorización explícita.
