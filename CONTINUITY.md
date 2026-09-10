# CONTINUITY.md — pmo

**Fecha:** 2026-09-09
**Rama activa:** `feat/forecast-deviations` (base `version-16` @ v0.9.0, commit `063c7b5`).
**Ciclo:** v0.10.0 — Forecast vigente y desviaciones (ADR-0009, **Accepted**). Bump a 0.10.0 incluido.

## Plan que estoy siguiendo
ADR-0009: el forecast vigente es el plan vivo de ERPNext (`expected_end_date`/`exp_end_date`); PMO **no**
crea un segundo motor predictivo, solo agrega señales de desviación. Entrega en 2 bloques → PR único a
`version-16`.
- **Bloque 1:** motor/composición (`compute_status`) + tests.
- **Bloque 2:** presentación en `PMO Status Report` (tabla única ampliada por Task + tarjetas de desviación
  + rótulo "Forecast vigente") + docs + CHANGELOG + bump 0.10.0.

## Estado por bloques
- **Bloque 1 — motor + tests. ✅ (commit en curso)**
  - `compute_status` extendido (params opcionales retrocompatibles) + helper `_current_task_map` +
    `build_status_report` pasa `pmo_committed_end_date` y el mapa de forecast por Task.
  - Nuevas señales: `slip_vs_committed_days` (Project), `forecast_exceeds_commitment.count` (Tasks cuyo
    forecast excede `pmo_deadline`, distinto de vencida), `tasks_vs_baseline` (tabla única: baseline/current/
    slip/deadline/vencida), `committed_end_date` en el retorno.
  - Preservado sin cambios: `final_date_slip_days`, `tasks_overdue_at_cutoff`, `counts`, `actual_hours_to_date`.
  - Tests `test_forecast_deviations.py` (6). Sin regresión (status_date 10/10, status_report 4/4).
    **Suite 233/233.**
- **Bloque 2 — presentación + docs + bump. ✅ (commit en curso)**
  - `PMO Status Report`: `_columns`/`_rows`/`_summary` ampliados — tabla única por Task (baseline/forecast/
    slip/deadline/vencida, orden por slip desc) + tarjetas de forecast vigente y desviaciones vs Baseline y
    vs compromiso. `PMO Planned vs Actual` intacto. No requiere migrate (lógica del Script Report, no fixture).
  - ADR-0009 → Accepted; docs usuario/arquitectura/CHANGELOG; bump 0.9.0 → 0.10.0.
  - Suite 233/233; presentación 4/4.

## Alcance / límites (ADR-0009)
- Sin DocTypes/Custom Fields/esquema (`snapshot_schema_version` = 1). Sin patch. `PMO Planned vs Actual`
  intacto (solo referencia documental).
- Fuera: EAC/ETC, forecast por `progress`, EVM/CPI/SPI, CPM (#9), reservas (#10), constraints tipados,
  segunda fecha final calculada.

## Siguiente paso
Bloques 1 y 2 commiteados en `feat/forecast-deviations`. Falta: `/ship push` → `/ship pr` (base `version-16`)
→ esperar CI. Tras merge (usuario): `/sync-check` → `/ship release` v0.10.0. Sin push/PR/release aún.

## Cuidados / no repetir
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N" con `tail`.
- `compute_status` debe seguir aceptando la firma de 5 args (retrocompatibilidad; hay test).
- Git solo vía `/ship`. Nunca trabajar en `version-16`. pmo NO usa migration patches ni MkDocs.
  BD/`bench migrate`: autorización explícita.
