# CONTINUITY.md — pmo

**Fecha:** 2026-09-05
**Rama activa:** `feat/capacity-views` (base `version-16`).
**Tarea actual:** **Cierre de `0.4.0`** — `PMO Capacity Page` (arquitectura D) + 5 vistas. Bloque
completo (vistas + Page) en **un único PR** hacia `version-16`. Commit de cierre + commit correctivo de
versión (0.5.0 → **0.4.0**, gate estricto: base `version-16=0.3.0` + un MINOR); **pendiente PR único**.

---

## Recuperación rápida

Capacity Planning se presenta con una **Frappe Page propia** (`capacity_planning`, arquitectura D) que
consume los Script Reports P4-safe vía `frappe.desk.query_report.run` (P4 en `execute()`, per-usuario) +
`pmo.capacity_page.get_resources`. El cliente **no** recalcula ni reconstruye P4. **Insights descartado**
(caché de query no aislada por observador → fuga P4; sin embedding inline en v3.13.1).

---

## Estado de la etapa (0.4.0)

Cinco vistas **funcionales y probadas** en la Page:
1. **Mapa de calor de capacidad** — Empleado×periodo, `util_planned`, sticky, tooltip.
2. **Uso de recursos** — detalle Capacity/Availability/Planned/Free/Utilización.
3. **Uso de recursos por proyecto** — un empleado; matriz Proyecto×periodo (modo temporal del report).
4. **Disponibilidad restante** — `Free`; Availability=0 → `—` (estado propio).
5. **Trabajo por recurso** — un empleado; jerarquía Proyecto→Tarea; consolidado confidencial solo horas.

Controles: Desde/Hasta + Día/Semana/Mes (unidad Horas); panel **Empleados** (buscador, multiselección,
selección persistente). Gráficas con `frappe.Chart`.

**Backend:** `PMO Resource Usage by Project` ampliado con **modo temporal** (`granularity` Day/Week/Month
→ matriz Proyecto×periodo, solo Planned, mismo P4); ruta sin `granularity` compatible. Motor/P4 intactos.

**Suite:** 131/131 OK en `test-pmo.localhost`. ruff + prettier limpios. `pmo-v16.dev` migrado+build hechos.

## Regla de seguridad fijada (P4 presentación)
- KPIs/gráficas **dentro** del Script Report o materializadas per-usuario en la Page (sin caché compartida).
- **Prohibido** Dashboard Chart / Number Card `type=Report` sobre reports enmascarados (`@cache_source`
  clave `chart-data:{name}`, sin usuario → fuga). **Insights** tampoco: su caché de query es observer-agnóstica.
- El gate de permiso del Report solo se cruza vía `query_report.run` (la Page); cubierto por
  `test_capacity_page.py::TestCapacityPageReportPath`. El rol `Employee` lo gestiona ERPNext: solo persiste
  con un Employee vinculado (conceder DESPUÉS de vincular).

## Pendiente
1. **PR único** `feat/capacity-views` → `version-16` (base protegida). Versión objetivo **0.4.0**
   (MINOR desde `v0.3.0`; `0.4.0` es el primer y único release de este bloque — no hubo `v0.4.0` previo).
2. Tras merge: `/ship release` (tag + GitHub Release `v0.4.0`).

**Nota de versionado (gate estricto):** la rama había hecho doble bump (0.3.0→0.4.0→0.5.0) sin mergear;
como todo entra en **un** PR de alcance MINOR desde `v0.3.0`, el release correcto es **0.4.0** (se
normalizó; `0.5.0` era artificial). `v0.4.0` nunca existió como tag/release previo.

## Decisiones vigentes
- **`Actual` fuera de las 5 vistas** (backend lo sigue derivando y enmascarando con P4). Reservado a futura
  vista separada **`Planificado vs Real`** / **Cumplimiento de planificación** (variación + % de
  cumplimiento; fórmula a definir al implementar; no tocará motor/P4/vistas). Ver ADR-0003 D9.
- **ADR-0003 = Aceptado** (D6 matiz Actual, D7 modo temporal, D8 Page+Insights, D9 Actual/vista futura).
- Confidencialidad ≠ exclusión: Total = Visible + Confidencial en todos los reportes/KPIs.
- `is_task_visible` canónico; `planned_hours` por Task = parte del asignado dentro del rango.

## No repetir / cuidados
- Tests: aislamiento en `setUp`, helpers idempotentes; Employee necesita `holiday_list` para que Planned
  se distribuya (si falta → `issues: no_holiday_list`, Planned 0). `_employee` concede rol `Employee`
  tras vincular `user_id`.
- Consola (`bench console`) rompe multilínea/`def`; usar one-off **plano** con `exec(open(...).read())`.
  `execute()` de Capacity Planning devuelve 5 valores; `json.dumps` no serializa datetime → `frappe.as_json`.
- Ambiguous chars en docstrings → ASCII (ruff RUF001/002). `frappe.db.sql` sin f-string (semgrep).
- one_offs/ ignorado (DEMO + validate_*). Git solo vía `/ship`. No trabajar en `version-16`. Desk v16 = `/desk/...`.
