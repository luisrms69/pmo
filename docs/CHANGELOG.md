# Changelog — pmo

## [0.5.0] — 2026-09-05

### Added
- **Schedule Governance sobre Task (ADR-0004 D1/D2/D3)** — mixin `pmo.overrides.PMOTaskScheduleMixin` vía
  `extend_doctype_class` que redefine **solo** `validate_parent_expected_end_date` y
  `validate_parent_project_dates`: las fechas de summary/`is_group` y `Project.expected_*` pasan a ser
  forecast/envelope **no vinculantes** y el **Actual** (Timesheet) **nunca se bloquea**. Upgrade-safe (no
  copia el cuerpo upstream `7b0df4b`) + guard de drift. `validate_dates()` y el resto de Task quedan nativos.
- **DocType `PMO Project Baseline` (ADR-0004 D4–D7)** — submittable (autoname `PMO-BL-.#####`) que congela
  el plan de un Project como referencia aprobada (**Schedule / Operational Planning Baseline**).
  - **Lineage lineal** (configuration control): `baseline_type` (Original/Approved Change/Replan) +
    `supersedes_baseline`; una sola Original válida por Project, `revision` única, sustituir la cabeza
    vigente Submitted/no-Cancelada, sin ciclos/bifurcación; **`effective_date` monótona en la cadena** y
    **cancelación solo de la cabeza** (no cancelar una baseline con sucesor no-cancelado). Sin `is_current`
    (derivado) ni `change_request`.
  - **Aprobación en Submit**: `approved_by`/`approved_at` (fijados en `before_submit`) + `snapshot_at`.
  - **Snapshot canónico** determinista (`pmo/baseline.py`): WBS por `task_id`+`parent_task`+`wbs_order`
    (no `lft/rgt`), `description`, fechas/horas/estado, `depends_on`, assignments
    `{user, employee, override_hours, effective_hours}` (override solo si `pmo_planned_hours>0`);
    `snapshot_schema_version`=1 + `snapshot_hash` sha256. **Preflight ligero** (warnings; bloquea solo ante
    reparto de horas inconsistente). `get_effective_baseline(project, as_of)` (Opción B, sin future-effective).
  - **P4 (ADR-0002/0004 D7)**: read = `is_project_visible`; write/submit/cancel = **owner** del Project;
    `PMO Executive Access` read-only; `PMO Manager` sin acceso; `permission_query_conditions` en listados.
- Tests: `test_schedule_governance.py` (6) y `test_project_baseline.py` (12). **Suite 149/149.**

### Changed
- **ADR-0004 aceptado** (`Proposed` → `Accepted`): la implementación confirma sus decisiones. Comparación de
  snapshots (Baseline vs Current / Baseline vs Baseline) queda diferida (issue #5).

## [0.4.0] — 2026-09-05

### Added
- **PMO Capacity Page** (`capacity_planning`, arquitectura D) — pantalla Desk dedicada, UX principal de
  Capacity Planning (estilo MS Project). Consume los Script Reports P4-safe vía
  `frappe.desk.query_report.run` (P4 per-usuario) + endpoint `pmo.capacity_page.get_resources`; el cliente
  no recalcula ni reconstruye P4. Gráficas con `frappe.Chart` (sin infraestructura frontend nueva).
  - **Selector de Empleados** (buscador, multiselección, Todos/Limpiar, selección persistente entre vistas).
  - Controles **Desde/Hasta** + escala **Día/Semana/Mes** (unidad fija Horas), visibles en el contenido.
  - **Cinco vistas:** **Mapa de calor de capacidad** (util. planificada por empleado×periodo),
    **Uso de recursos** (detalle Capacity/Availability/Planned/Free/Utilización), **Uso de recursos por
    proyecto** (un empleado; matriz Proyecto×periodo), **Disponibilidad restante** (Free; Availability=0 →
    estado propio), **Trabajo por recurso** (un empleado; jerarquía Proyecto→Tarea con fechas/estado).
- **Vistas de Capacity Planning — Script Reports** (base P4 que consume la Page) sobre el motor v0.3.0,
  sin recalcular; enmascarado P4 dentro de cada `execute()`:
  - **`PMO Capacity Planning`** (extendido): granularidad **Total** (Centro de recursos), columnas
    `designation`/`department`, **gráfica** (Availability vs Planned total; agregada por Employee sin
    filtro), **`report_summary`** (Recursos, Sobreasignados, Utilización) y **formatter** de
    sobreasignación (util <80 normal / 80–100 ámbar / >100 rojo; overallocation>0 y free<0 en rojo).
  - **`PMO Resource Usage by Project`**: árbol Employee→Project; visibles identificados, no-visibles en
    una fila `Comprometido (confidencial)`, bucket `Sin proyecto`; `Total = visibles + Sin proyecto +
    confidencial`. **Ampliación temporal P4-safe:** con `granularity = Day/Week/Month`, `execute()`
    expone Planned por proyecto y periodo (matriz Proyecto×periodo, solo Planned); la ruta previa **sin
    `granularity` permanece compatible** (totales).
  - **`PMO Work by Resource`**: tareas por recurso con **doble boundary Task≠Project**
    (`is_task_visible` canónico, incluye DocShare); `planned_hours` del periodo; Task no visible →
    agregado confidencial; sin Actual por Task.
  - **Workspace `PMO Capacity`** (navegación shortcuts-only): 3 shortcuts a los reports; sin
    `charts`/`number_cards`.
  - Helpers internos `get_planned_load_by_task`, `get_actual_by_project`, `permissions.is_task_visible`,
    `pmo.capacity_page.get_resources`.
- Tests: `test_capacity_page.py` (incluye el **camino real** de la Page `query_report.run` como Employee
  normal) y `TestResourceUsageTemporal` (Day/Week/Month, P4, totales) en `test_resource_usage.py`.
  Suite **131/131 OK**.

### Changed
- **ADR-0003 aceptado** (`Propuesto` → `Aceptado`): D6 (matiz `Actual`), D7 (modo temporal del report),
  **D8** (arquitectura de presentación Page + Script Reports; spike de Insights descartado para datos P4
  por-observador: caché de query no aislada por observador y sin embedding inline con sesión Desk) y
  **D9** (`Actual` y vista futura).

### Security
- **Regla P4 de presentación:** los KPIs/gráficas se materializan **dentro** del Script Report o
  per-usuario en la Page (sin caché compartida). Prohibido Dashboard Chart / Number Card `type=Report`
  sobre reports enmascarados (`@cache_source` con clave `chart-data:{name}` sin usuario → fuga entre
  usuarios); **Insights** tampoco (su caché de query es observer-agnóstica). Workspace `public=1` =
  **compartido**, restringido por `roles` (no acceso universal).

### Reservado (pendiente futuro, NO implementado)
- Las cinco vistas actuales **no muestran `Actual`** (el backend lo sigue derivando y enmascarando con P4).
  La comparación **Planned vs Actual** se reserva a una futura vista separada **`Planificado vs Real`**
  (*Cumplimiento de planificación*); su fórmula de cumplimiento se definirá al implementarla. No
  modificará motor/Planned/Actual/P4 ni las vistas actuales.

### Docs
- ADR-0003 (Vistas + reglas P4 de presentación + D8/D9), `docs/tecnico/arquitectura.md`,
  `docs/usuario/capacity-planning.md`.

## [0.3.0] — 2026-09-03

### Added
- **Capacity Planning (ADR-0003)** — planificación de capacidad **derivada** de Task + Assignment, sin
  sistema paralelo de asignaciones.
  - **`PMO Capacity`** — capacidad horas/día efectivo-datada (global + override por Employee), resolución
    única `get_capacity` (sin 8h implícitas), validación valor>0 y unicidad scope+`from_date`.
  - **Availability** (derivada) — Capacity − festivos (Holiday List) − Leave aprobada (**HRMS opcional**).
  - **Planned Load** (derivada) — reparte `Task.expected_time` entre asignados activos (`ToDo` Open);
    horas por asignado con override opcional **`ToDo.pmo_planned_hours`** (1/N/overrides + remanente;
    inconsistencias reportadas, sin pérdida silenciosa); distribución diaria respetando Holiday List;
    bridge `Employee.user_id` fail-closed. Retornos estructurados (`issues`/`unscheduled`/`unmapped`).
  - **Actual** (derivada) — horas de Timesheet con la semántica oficial de `daily_timesheet_summary`
    (docstatus=1, `hours`, bornes `from_time`/`to_time`). Planned y Actual nunca se suman.
  - **Reporte `PMO Capacity Planning`** (Script Report) — fila `Employee × periodo` con Capacity,
    Availability, Planned/Actual (visible + `Comprometido (confidencial)` agregado), Libre,
    Sobreasignación y utilizaciones; granularidad Day/Week/Month. **Enmascarado P4 server-side**: los
    proyectos fuera del boundary del observador nunca se enumeran ni se envían al cliente.
  - Se descartó el enfoque inicial (DocTypes `PMO Resource Allocation` + `PMO Allocation Day`) por
    duplicar Task + Assignment (ver ADR-0003, revisión 2026-09-03).

### Docs
- `docs/tecnico/arquitectura.md` (sección Capacity Planning) y `docs/usuario/capacity-planning.md`.

## [0.2.0] — 2026-09-02

### Added
- **Privacidad de Project/Task (P0)** — aislamiento fail-closed: Project y Task privados por defecto.
  - Visibilidad por **owner / `PMO Project Member` / `PMO Executive Access` / DocShare**; una Task
    hereda la frontera de su Project, y la asignación directa (ToDo) da acceso **solo a esa Task**.
  - Enforcement por hooks nativos **sin tocar DocPerms**: `permission_query_conditions` (listados,
    Gantt, calendario, búsquedas, API) + `has_permission` (documento único/URL). SHARE manual
    restringido a `PMO Executive Access`/`Administrator` por el mismo hook (`ptype="share"`), sin
    Custom DocPerm; `assign_to` sin auto-share.
  - Política de WRITE: owner (Project + Tasks), member (Tasks del Project), assignee (su Task);
    `PMO Executive Access` solo lectura; `PMO Manager` sin acceso por el rol.
  - **Cierre de vectores que ignoran `pqc`**: override de `create_duplicate_project` (check READ del
    origen) y `Custom Role` que restringe los reports `Project Summary`, `Delayed Tasks Summary` y
    `Project wise Stock Tracking` a `PMO Executive Access`/`Administrator`. Global Search verificado.
  - Nuevos objetos: child DocType `PMO Project Member` (+ Custom Field `Project-pmo_members`), roles
    `PMO Manager` y `PMO Executive Access`, fixtures (`custom_field`, `role`, `custom_role`).
  - Tests: `test_privacy_{read,write,share,reports}.py`. Decisiones en ADR-0002 (D1–D11).

### Docs
- `docs/tecnico/arquitectura.md` (sección Privacidad P0) y `docs/usuario/privacidad-proyectos.md`.

## [0.1.1] — 2026-09-02

### Added
- ADR-0002 (Project/Task Privacy y Security Boundary) y ADR-0003 (Resource Capacity and Planned
  Allocation) como decisiones arquitectónicas base (estado Propuesto). Solo documentación; sin cambios
  de código ni de esquema.

## [0.1.0] — 2026-08-16

### Added
- Gantt de `Task` ordenado automáticamente por jerarquía (`lft ASC`), no por fechas, vía
  `doctype_calendar_js` (sin tocar core; solo afecta Task > Gantt).
- Importador administrativo de Tags nativos desde CSV (Page `tag_import`): Dry Run sin escritura,
  Aplicar con validación global todo-o-nada, idempotente, con desglose por documento.
- ADR-0001 y documentación técnica/usuario.

## [0.0.1] — 2026-08-14

### Added
- Scaffold inicial del app
- Integración con frappe-infrastructure (symlink `.claude/commands`, CLAUDE.md referencial)
- CI + linter (`.github/workflows/ci.yml`, `linter.yml`)
- `required_apps = ["erpnext"]`
