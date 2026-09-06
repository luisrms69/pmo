# CONTINUITY.md — pmo

**Fecha:** 2026-09-05
**Rama activa:** `feat/schedule-baselines` (base `version-16` @ v0.4.0).
**Tarea actual:** **v0.5.0 — Schedule Governance & Baselines.** Bloques 0–3 ✅. bump `__version__`→0.5.0,
CHANGELOG `[0.5.0]`, ADR-0004 `Accepted`. `test-pmo.localhost` y `pmo-v16.dev` migrados (DocType nuevo);
engine validado sobre DEMO en dev. **Pendiente: `/ship push` + `/ship pr` a `version-16`** (autorizados);
merge y `/ship release v0.5.0` tras revisar el PR.

---

## Recuperación rápida

ADR-0004 (Proposed) aprobado como arquitectura. Objetivo v0.5.0: gobierno de cronograma + baselines sobre
ERPNext nativo, sin fork. Referencia viva: `docs/adr/0004-schedule-governance-and-baselines.md`.

---

## Plan por bloques (un PR único a `version-16`)

- **Bloque 0 — ADR-0004 (docs).** Escribir e incorporar ADR-0004 (Proposed). *(commit en curso)*
- **Bloque 1 — Intervención Task (D1/D2/D3) ✅ HECHO.** Mixin **`pmo.overrides.PMOTaskScheduleMixin`**
  (nota: se usó el módulo `pmo/overrides.py` existente, no `pmo.overrides.task` — `overrides` es módulo, no
  paquete; sin cambio de decisión) vía `extend_doctype_class` en `hooks.py`; redefine **solo**
  `validate_parent_expected_end_date` y `validate_parent_project_dates` (no bloquear). Tests
  `test_schedule_governance.py` (6): guard de drift, ruta nativa vs mixin forzando `frappe.in_test=False`
  (atributo de módulo, no `flags`), y path `task.save()` que usa Timesheet. **Suite 137/137.**
- **Bloque 2 — `PMO Project Baseline` (D4–D7) ✅ HECHO.** DocType submittable (autoname `PMO-BL-.#####`);
  engine `pmo/baseline.py` (snapshot canónico + hash sha256 determinista + preflight + baseline vigente
  as-of); controller (invariantes de lineage lineal + `before_submit`); P4 en `permissions.py`
  (`has_permission_baseline` read=`is_project_visible`, write/submit=owner, Executive read-only;
  `get_permission_query_conditions_baseline`) + hooks. `override_hours` en snapshot solo si
  `pmo_planned_hours>0` (coherente con el motor). Tests `test_project_baseline.py` (12). **Suite 149/149.**
  Docs usuario (`baselines.md`) + técnico.
- **Bloque 3 — Cierre.** Bump `__version__` → 0.5.0 (MINOR desde v0.4.0), CHANGELOG `[0.5.0]`; `/ship push`
  + `/ship pr`; tras merge `/ship release` `v0.5.0`.

## Decisiones vigentes (ADR-0004, resumen)
- 4 planos: Baseline / Current(Forecast) / Actual / Constraint(diferido).
- Task group = summary/WBS con fechas **no vinculantes** (pueden quedar stale; sin rollup dinámico; warning
  en preflight). `Project.expected_*` = forecast, no límite de la realidad.
- Intervención: **mixin `extend_doctype_class` sobre Task**, solo los dos submétodos (upgrade-safe; guard
  de drift; reconcilia drift upstream `7b0df4b` que ya restringe los 4 campos por abajo/arriba).
- `PMO Project Baseline` submittable: lineage lineal (`baseline_type`, `supersedes_baseline`, sin
  `is_current`), **Opción B** (sin future-effective; `effective_date <= approved_at`), aprobación fijada en
  Submit (`approved_by`/`approved_at`), snapshot canónico (`schema_version`+`hash`) con `description` y
  assignments `{user, employee, override_hours, effective_hours}`.
- **Autoridad de aprobación = Project Owner** (Executive read-only; Manager sin cambios; separación de
  funciones/CCB → v0.6.0). Read del Baseline respeta P4 (`is_project_visible`).
- Capacity Planning **sin cambios**. Change Control/`erpnext_proposals` **fuera** de ADR-0004 (posible
  ADR-0005 en v0.6.0). Comparador de snapshots = issue #5 (diferido).

## Verificaciones hechas (spike)
- `task.py:98-99` llama submétodos vía `self.<m>()` → override por MRO válido sin tocar `validate_dates()`.
- `validate_parent_project_dates` local (16.32.1) solo usa `expected_end_date`; `7b0df4b` no está en el
  bench; nuestra semántica es independiente del cuerpo upstream.
- Timesheet `:182` hace `Task.save()` → dispara la validación sobre `act_*` (bug real a desbloquear).
- `extend_doctype_class` y `override_doctype_class` existen en v16 (`base_document.py`); `erpnext_proposals`
  usa `extend_doctype_class` para Quotation (precedente).
- `Task.description` nativo (Text Editor). `get_planned_hours_per_assignee` devuelve horas efectivas.

## Cuidados / no repetir
- Git solo vía `/ship`. No trabajar en `version-16`. Rutas Desk v16 = `/desk/...`.
- one_offs/ ignorado. Consola rompe multilínea → one-off plano con `exec(open(...).read())`.
- Tests: `frappe.in_test` hace early-return en la validación nativa → forzar `frappe.flags.in_test=False`
  en `try/finally` para ejercer la ruta de producción, o llamar al método directamente.
- ADR como referencia, no dogma: si aparece limitación real/alternativa más simple, reportar antes de
  desviarse (sin re-abrir toda la arquitectura).
