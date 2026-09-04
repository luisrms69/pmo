# CONTINUITY.md — pmo

**Fecha:** 2026-09-04
**Rama activa:** `feat/capacity-views` (base `version-16`) — bloque **Vistas de Capacity Planning**.
**Tarea actual:** **Cierre del bloque de vistas**: docs + bump 0.4.0 hechos; pendiente migrar
`pmo-v16.dev`, suite completa y **PR único** a `version-16`.

---

## Recuperación rápida

Vistas estilo MS Project por incrementos en una sola rama; **un solo PR** al cerrar el bloque (como P0 y
Capacity). Sobre el motor v0.3.0 (no recalcula). P4 dentro de cada Script Report.

---

## Estado del bloque (commits locales, sin push)

- `a1e4622` **Inc. 1** — Capacity Planning report extendido (Total, designation/department, chart,
  report_summary, formatter).
- `263ee11` **Inc. 2** — `PMO Resource Usage by Project` (árbol Employee→Project, P4).
- `0dc0af7` **Inc. 3** — `PMO Work by Resource` (doble boundary Task≠Project; `is_task_visible`;
  `get_planned_load_by_task`).
- `fc82934` **Inc. 4** — Workspace `PMO Capacity` (shortcuts-only).
- *(pendiente de commit)* **cierre documental**: ADR-0003 (D7 Vistas + reglas P4), `docs/tecnico`,
  `docs/usuario`, `docs/CHANGELOG.md` [0.4.0], `pmo/__init__.py` → **0.4.0**, este CONTINUITY.

**Suite:** 113/113 OK en `test-pmo.localhost`.

## Regla de seguridad fijada (P4 presentación)
- KPIs/gráficas **dentro** del Script Report (`report_summary`/`chart`), per-usuario, sin caché.
- **Prohibido** Dashboard Chart / Number Card `type=Report` sobre reports enmascarados: `@cache_source`
  (clave `chart-data:{name}`, sin usuario) filtraría datos enmascarados entre usuarios.
- Componentes `Document Type` sobre Project/Task prohibidos (bypassean `execute()`).
- Workspace `public=1` = **compartido**, restringido por `roles`; **no** es acceso universal.

## Pendiente para cerrar el bloque
1. **Commit del cierre documental + bump 0.4.0** (requiere autorización).
2. **Migrar `pmo-v16.dev`** (3 reports nuevos + Workspace + Custom Field ya existente) — escritura de BD,
   requiere autorización. Objetos nuevos en dev: Reports `PMO Resource Usage by Project`,
   `PMO Work by Resource`; Workspace `PMO Capacity`. (Capacity Planning ya existe; solo cambia su código.)
3. **Suite completa** + **PR único** a `version-16` (push + PR, autorizaciones separadas).

## Decisiones vigentes
- Vistas derivadas del motor v0.3.0; sin recalcular; Task+Assignment como fuente.
- `is_task_visible` canónico (`frappe.has_permission("Task","read")`): capacidad + `has_permission_task`
  + DocShare + Administrator; System Manager sin alcance por rol.
- `planned_hours` por Task = parte del asignado **dentro del rango** (`get_planned_load_by_task`).
- Confidencialidad ≠ exclusión: Total = Visible + Confidencial en todos los reportes/KPIs.

## No repetir / cuidados
- Tests: aislamiento en `setUp` (`frappe.db.delete`), helpers idempotentes, Employee `user_id` por
  `set_value`, Timesheet `docstatus=1` por `set_value`, `frappe.share.add` para DocShare (mute_emails).
- Ambiguous chars en docstrings → ASCII (ruff RUF001/002). `frappe.db.sql` sin f-string (semgrep).
- Workspace: `shortcuts` es lo que cuenta en migrate; `content` referencia por `label` (gotcha).
- Git solo vía `/ship`. No trabajar en `version-16`. Rutas Desk v16 = `/desk/...`.
