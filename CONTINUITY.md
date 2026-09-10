# CONTINUITY.md — pmo

**Fecha:** 2026-09-09
**Rama activa:** `feat/planned-vs-actual` (base `version-16` @ v0.8.0, commit `eb4e897`).
**Ciclo:** v0.9.0 — Planificado vs Real (ADR-0008, **Accepted** 2026-09-09). Bump `__version__ → 0.9.0` incluido.

## Plan que estoy siguiendo
ADR-0008 (capacidad de **reporting**, no planificación): poner lado a lado esfuerzo Planned vs Actual por
Project/Task con datos ya nativos. Entrega en 2 bloques → PR único a `version-16`.
- **Bloque 1:** Script Report `PMO Planned vs Actual` + helpers as-of + tests + docs.
- **Bloque 2:** Workspace público `PMO Control` con 4 shortcuts (Planned vs Actual, Status Report, Baseline
  Comparison, Change Register). No tocar `PMO Capacity`. Sin Number Cards ni charts.

## Estado por bloques
- **Bloque 1 — Report + as-of + tests + docs. ✅ (commit en curso)**
  - Report `PMO Planned vs Actual` (Script Report `is_standard`, `ref_doctype` Project). Planned=
    `Task.expected_time`; Actual = `actual_time` nativo o Timesheet submitted **as-of** `status_date`;
    Variance = `Actual - Planned`; % Consumed (guarda /0). Detalle por Task hoja, total Project excluye
    `is_group`. P4 en `execute()` (Script Report ignora pqc).
  - Helpers `pmo/actual.py`: `get_actual_hours_asof`, `get_actual_hours_by_task_asof`. Corte inclusivo
    `from_time <= timestamp(status_date,'24:00:00')` (≡ `date(from_time) <= status_date`), docstatus=1,
    SQL parametrizada.
  - `bench migrate` en `test-pmo.localhost` OK — Report registrado.
  - Tests `test_planned_vs_actual.py` (11): puros (`_rows`/`_pct`/`_columns`, exclusión is_group) +
    integración (corte as-of cuenta el propio día y excluye el siguiente; `execute()` end-to-end; P4
    bloquea no-miembros). **Suite 222/222.**
  - Docs: ADR-0008 (Proposed), `docs/usuario/planificado-vs-real.md`, sección en `arquitectura.md`,
    CHANGELOG `[0.9.0]`. Bump `__version__ 0.8.0 → 0.9.0`.
- **Bloque 2 — Workspace `PMO Control`. ✅ (commit en curso)**
  - `pmo/pmo/workspace/pmo_control/pmo_control.json` (public, module PMO, `is_standard`; roles Projects
    User / PMO Executive Access / System Manager). 4 shortcuts tipo Report → `PMO Planned vs Actual`,
    `PMO Status Report`, `PMO Baseline Comparison`, `PMO Change Register`. Sin charts/number_cards.
    `PMO Capacity` intacto. Mismo patrón de shortcuts que Capacity.
  - `bench migrate` en `test-pmo.localhost` OK — Workspace sincronizado (verificado en BD: 4 shortcuts;
    Capacity con sus 3 originales).
  - Tests `test_control_workspace.py` (5). **Suite 227/227.**

## Alcance / límites (ADR-0008)
- Sin motor nuevo, DocTypes, Custom Fields ni cambios a Baseline (`snapshot_schema_version` sigue en 1).
- Fuera de alcance: EVM (EV/PV/AC), CPI/SPI, forecast (EAC/ETC), planned time-phased/BCWS, Baseline como
  fuente del plan, CPM (#9), reservas de capacidad (#10), constraints/deadlines, Number Cards/charts.

## Siguiente paso
**PR #13** abierto contra `version-16` (https://github.com/luisrms69/pmo/pull/13). Bloques 1+2 y cierre
documental (ADR-0008 Accepted) pusheados. Esperando CI. Tras merge (lo hace el usuario en GitHub):
`/sync-check` → `/ship release` v0.9.0 (tag + GitHub Release). Sin merge/tag/release aún.

## Cuidados / no repetir
- La suite corre en **dos lotes** (integración + unitarios): `Ran 194...OK` + `Ran 25...OK` = 222. No leer
  solo el último "Ran N" con `tail` (oculta el lote grande).
- Timesheet Detail **recalcula `hours`** desde `from_time`/`to_time` al insertar: en tests, declarar spans
  coherentes con las horas esperadas.
- No usar `format_date`/locale-dependientes en código no bloqueante (bug framework `get_locale_value`).
- Git solo vía `/ship`. Nunca trabajar en `version-16`. pmo NO usa migration patches ni MkDocs.
  BD/`bench migrate`: autorización explícita.
