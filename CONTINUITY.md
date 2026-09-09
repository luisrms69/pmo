# CONTINUITY.md — pmo

**Fecha:** 2026-09-09
**Rama activa:** `feat/schedule-commit-dates` (base `version-16` @ v0.7.0, commit `17c0f61`).
**Ciclo:** v0.8.0 — Gobierno avanzado del cronograma, fase 1 (fechas comprometidas, ADR-0007 Proposed).

## Plan que estoy siguiendo
ADR-0007 (alcance mínimo): distinguir fecha **planeada/calculada** (nativa) de fecha **comprometida**
(compromiso de negocio/acordado; no se desplaza automáticamente, sí modificable por decisión autorizada).
Entrega por bloques pequeños → PR único a `version-16`. Bump `__version__ → 0.8.0` pendiente antes del PR.

## Estado por bloques
- **Bloque 1 — Custom Fields + warnings + tests. ✅ (commit en curso)**
  - `Task.pmo_deadline` (Date) y `Project.pmo_committed_end_date` (Date), por fixture. `bench migrate` en
    `test-pmo.localhost` OK (campos creados).
  - Warnings suaves (`pmo/schedule_commit.py`, `doc_events` Task.validate + Project.validate): si el fin
    planeado excede el compromiso → aviso; **no bloquea** guardado ni Actual. Campos vacíos = sin aviso.
  - Tests `test_schedule_commit.py` (6). **Suite 211/211.** Smoke test en `test-pmo.localhost`: breach→avisa+guarda,
    no-breach→guarda sin aviso, persiste.
  - **Defecto corregido en el bloque:** el warning usaba `format_date` (dependiente de locale); con sesión
    sin idioma lanzaba y bloqueaba el guardado. Se cambió a fecha ISO directa → aviso robusto, nunca bloquea.

## Alcance / límites (ADR-0007)
- Solo `pmo_deadline` + `pmo_committed_end_date` + warnings. **Sin** constraints tipados (SNET/FNLT/MSO/MFO),
  **sin** auto-reprogramación, **sin** scheduler propio.
- **`snapshot_schema_version` sigue en 1**; Baseline y Status Date **sin cambios**; ADR-0004/0006 sin modificar.

## Siguiente paso
Tras el commit del Bloque 1: definir bloques siguientes (p. ej. UX en el formulario y/o docs usuario/técnico),
bump 0.8.0 antes del PR. Sin push/PR/release aún.

## Cuidados / no repetir
- No usar `format_date`/locale-dependientes en validaciones no bloqueantes (bug framework `get_locale_value`
  con sesión sin idioma → convierte warning en excepción). Usar fecha ISO directa.
- Git solo vía `/ship`. Nunca trabajar en `version-16`. pmo NO usa migration patches ni MkDocs.
  `test-pmo.localhost` tiene 0 Companies. BD/`bench migrate`: autorización explícita.
