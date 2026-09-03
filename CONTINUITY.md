# CONTINUITY.md — pmo

**Fecha:** 2026-09-03
**Rama activa:** `feat/capacity-planning` (base `version-16`) — bloque **Capacity Planning (ADR-0003)**.
**Tarea actual:** Implementación incremental de ADR-0003. Incrementos 1 (PMO Capacity), 2 (PMO Resource
Allocation), 3 (Availability) cerrados como checkpoints locales. Sigue el siguiente incremento (Actual).

---

## Recuperación rápida

Estoy trabajando en:
Capacity Planning por incrementos en una sola rama; **un solo PR** al cerrar el bloque completo (como P0).
Sin push ni PR hasta el cierre. Cada incremento = checkpoint local `/ship commit` sin push.

Plan que estoy siguiendo:
`docs/adr/0003-resource-capacity.md`. Los 4 conceptos separados: Capacity (persistido) · Availability
(derivado) · Allocation (persistido/día) · Actual (derivado de Timesheet).

Objetivo inmediato:
Siguiente incremento — **Actual** (tiempo real desde Timesheet). **Regla fijada:** Actual debe coincidir
con los reportes oficiales de Timesheet de ERPNext (identificar campos/filtros/estados exactos y reutilizar
esa fuente/semántica; justificar cualquier diferencia antes de implementar). Después: reportes/KPIs (P4).

---

## Estado actual (bloque Capacity)

### P0 privacidad — CERRADO y liberado
- PR #2 mergeado a `version-16`; **release v0.2.0** (tag + GitHub Release alineados). Ver ADR-0002.

### Incrementos ADR-0003 cerrados (checkpoints locales, sin push)
- **Inc. 1 — `PMO Capacity`** (`168fee9`): DocType efectivo-datado (employee opcional = global/override,
  from_date, capacity_hours_per_day). `get_capacity(employee, date, throw=False)` única función de
  resolución (override → global → None, sin 8h). Validación valor>0 y unicidad scope+from_date con
  GLOBAL único. Tests 10.
- **Inc. 2 — `PMO Resource Allocation`** (`ba16605`): cabecera **submittable** (Draft editable/materializable,
  Submit congela, Amend replanifica) + child `PMO Allocation Day`. Materialización Even sobre días
  laborables reales (Holiday List nativa: `get_holiday_list_for_employee` + `is_holiday`). Privacidad P4 a
  nivel documento (`pqc`+`has_permission` ligados a visibilidad del Project; executive read-only). No
  concede acceso al Project ni crea ToDo. Tests 12 + 4 privacidad.
- **Inc. 3 — Availability** (pendiente de commit en este turno): `pmo/availability.py`
  `get_availability(employee, date)` + `get_availability_range(...)`. **Derivado, NO persistido.**
  Capacity − festivos (Holiday List) − Leave aprobada (**HRMS opcional**, query directa mínima sobre
  `Leave Application` porque `get_leaves_for_period` no aplica). `cap None → None` (no 0). Medio día →
  cap/2. Tests 10. **Suite 70/70 OK.**

### Pendiente
1. **Commit Inc. 3 — Availability** (este turno, sin push).
2. **Siguiente incremento — Actual** (Timesheet; regla: == reportes oficiales de Timesheet).
3. **Reportes/KPIs de utilización con enmascarado P4** (bucket "Comprometido (confidencial)", agregación
   server-side). Reportes siguen fuera hasta su incremento.
4. **Cierre del bloque:** actualizar **ADR-0003 D3** (Draft/Confirmed → `docstatus` submittable, decisión
   tomada en Inc. 2), documentación técnica + usuario de Capacity, bump **0.3.0** (MINOR), migrar
   `pmo-v16.dev`, PR único a `version-16`.

---

## Decisiones vigentes (no todas en código aún)
- **Actual == Timesheet oficial:** no crear cálculos paralelos; reutilizar fuente/semántica de los reportes
  oficiales de Timesheet. Justificar cualquier diferencia antes de implementar.
- **Submittable en vez de status custom** (Inc. 2): `docstatus` cubre confirmar/congelar/replanificar.
  Falta reflejarlo en ADR-0003 D3 al cierre.
- **Availability derivada, no persistida**; HRMS opcional; la integración real con `Leave Application`
  queda **pendiente de validar en un site con HRMS** (la lógica half/full está cubierta unitariamente).
- Privacidad de `PMO Resource Allocation` hereda el boundary de Project (ADR-0002/D5); child hereda del padre.

---

## No repetir / cuidados
- **Aislamiento de tests:** `IntegrationTestCase` no revierte entre tests aquí → limpiar en `setUp`
  (`frappe.db.delete(...)`) y usar helpers idempotentes (Project por `project_name` único, Employee, HL).
- **Employee en tests:** crear con `ignore_mandatory=True` (sin Company) y **sin** `gender` (Gender "Other"
  no existe en test-pmo); poner `holiday_list` directo para que `get_holiday_list_for_employee` resuelva.
- `set_value(owner)` **después** del último `save()` del doc (evita `TimestampMismatchError`).
- Availability no tiene DocType → **no requiere migrate**.
- Git solo vía `/ship`. No trabajar en `version-16`. Rutas Desk v16 = `/desk/...`.

---

## Archivos relevantes ahora
- `pmo/capacity.py`, `pmo/allocation.py`, `pmo/availability.py`.
- `pmo/pmo/doctype/{pmo_capacity,pmo_resource_allocation,pmo_allocation_day}/`.
- `pmo/permissions.py` (+ allocation pqc/has_permission), `pmo/hooks.py` (wiring).
- Tests: `pmo/pmo/tests/test_{capacity,allocation,allocation_privacy,availability}.py`.
