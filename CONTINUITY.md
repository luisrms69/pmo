# CONTINUITY.md — pmo

**Fecha:** 2026-09-03
**Rama activa:** `feat/capacity-planning` (base `version-16`) — bloque **Capacity Planning (ADR-0003)**.
**Tarea actual:** **Cierre del bloque** Capacity Planning: documentación hecha, bump 0.3.0; pendiente
migrar `pmo-v16.dev`, correr suite y abrir el **único PR** del bloque.

---

## Recuperación rápida

Capacity Planning por incrementos en una sola rama; **un solo PR** al cerrar el bloque (como P0).
El bloque quedó **rediseñado**: derivado de Task + Assignment, sin DocType de asignación paralelo.

---

## Estado del bloque (commits locales, sin push)

- `168fee9` **PMO Capacity** (persistido, efectivo-datado).
- `ba16605` PMO Resource Allocation — **eliminado** en `342aacb` (era captura duplicada de Task+Assignment).
- `f9388a2` **Availability** (derivada).
- `342aacb` **refactor**: elimina el DocType paralelo; Capacity Planning = derivación de Task + Assignment.
- `55b95cd` **Actual** (Timesheet oficial).
- `e2b8900` **Planned Load** (Task + Assignment; `ToDo.pmo_planned_hours`; retornos estructurados).
- `54e2254` **Reporte PMO Capacity Planning** (P4 server-side + KPIs).
- *(pendiente de commit)* **Cierre documental**: `docs/tecnico/arquitectura.md`, `docs/usuario/capacity-planning.md`,
  ADR-0003 (impacto/acceso), `docs/CHANGELOG.md` [0.3.0], `pmo/__init__.py` → **0.3.0**, este CONTINUITY.

**Suite:** 88/88 OK en `test-pmo.localhost`.

## Arquitectura vigente
- **Capacity** (`pmo/capacity.py`) · **Availability** (`pmo/availability.py`) · **Actual** (`pmo/actual.py`) ·
  **Planned Load** (`pmo/planned_load.py`) · **lógica pura** `build_allocation_days` (`pmo/allocation.py`).
- **Reporte** `pmo/pmo/report/pmo_capacity_planning/` (Script Report, P4 en `execute()`).
- Objetos: DocType `PMO Capacity`; Custom Field `ToDo-pmo_planned_hours` (fixture); DocPerm `report` en
  PMO Capacity para Employee/Executive. Todo lo demás derivado; sin captura paralela.

## Pendiente para cerrar el bloque
1. **Commit del cierre documental + bump 0.3.0** (requiere autorización).
2. **Migrar `pmo-v16.dev`** (importa PMO Capacity, Custom Field ToDo, Report, permisos) — escritura de BD,
   requiere autorización. Objetos nuevos en dev: `tabPMO Capacity`, CF `ToDo-pmo_planned_hours`, Report
   `PMO Capacity Planning`, DocPerm de PMO Capacity.
3. **Suite completa** + **PR único** a `version-16` (push + PR, autorizaciones separadas).

## Decisiones vigentes
- **Actual == Timesheet oficial** (`daily_timesheet_summary`): no cálculos paralelos.
- Planned Load derivado de Task + Assignment; `ToDo.pmo_planned_hours` solo override; bridge
  `Employee.user_id` fail-closed (ambiguo → excluido).
- Reporte P4: `Comprometido (confidencial) = total − Σ visibles`; identidades confidenciales nunca al cliente.
- Acceso al reporte: `Report.roles` + `report` sobre `PMO Capacity` (Employee solo `report`); row-level en `execute()`.
- Plan vigente (sin snapshots) en el MVP.

## No repetir / cuidados
- Tests: `IntegrationTestCase` no revierte entre tests → limpiar en `setUp` (`frappe.db.delete`); helpers idempotentes.
- Employee de test: sin `gender`, `user_id` por `db.set_value` (evita validación que toca Company), `holiday_list` directo.
- Timesheet de test: `docstatus=1` por `db.set_value` (el `on_submit` guarda el Project → requiere Company/stock).
- Project.name = naming series (`PROJ-####`), no `project_name`.
- Ambiguous chars en docstrings/comentarios → usar ASCII (ruff RUF001/002).
- Git solo vía `/ship`. No trabajar en `version-16`. Rutas Desk v16 = `/desk/...`.
