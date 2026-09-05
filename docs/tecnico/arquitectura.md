# Arquitectura técnica — pmo

Estado real implementado. Ver decisiones en `docs/adr/`.

## Gantt de Task ordenado por `lft`

- **Hook:** `doctype_calendar_js = {"Task": "public/js/task_calendar_pmo.js"}` en `hooks.py`.
- **Asset:** `pmo/public/js/task_calendar_pmo.js` — se carga **después** del `task_calendar.js` de
  ERPNext y extiende `frappe.views.calendar["Task"]` añadiendo `gantt.order_by = "lft"`.
- **Efecto:** `GanttView.setup_defaults()` aplica `sort_by="lft"`, `sort_order="asc"` **solo** en el
  Gantt de Task. No afecta List, Tree ni Calendar. No modifica core.
- **Nota:** las flechas del Gantt son dependencias nativas (`depends_on_tasks`), ajenas a este cambio.

## Importador de Tags nativos (`pmo/tag_import.py`)

Métodos whitelisted (consumidos por la Page `tag_import`):

| Método | Escribe | Descripción |
|---|---|---|
| `tag_import_dry_run(csv_content)` | No | Valida y devuelve resumen + `detalle` por documento |
| `tag_import_apply(csv_content)` | Sí (si válido) | Valida todo; si pasa, aplica con `add_tags` |

- **CSV:** encabezado `doctype,document,tags` (tags separados por comas por documento).
- **Validación global previa a escribir:** estructura, DocType, existencia del documento, permiso de
  escritura, tags. Cualquier error → **no escribe nada** (todo-o-nada).
- **API nativa:** `frappe.desk.doctype.tag.tag.add_tags` (crea `Tag`, escribe `Tag Link`/`_user_tags`,
  idempotente). No se escribe SQL directo ni tablas internas.
- **Resumen devuelto:** documentos leídos/válidos, asociaciones solicitadas/aplicadas (diff real),
  documentos inexistentes, errores y `detalle` (tipo, documento, tags, estado) para el guard visual.

## UI

- **Page:** `pmo/pmo/page/tag_import/` (rol System Manager). Sube CSV → Dry Run → Aplicar; muestra
  conteos, aviso de todo-o-nada ante errores y tabla de detalle por documento.

## Privacidad de Project/Task (P0)

Aislamiento **fail-closed**: `Project` y `Task` son privados por defecto. Decisiones en
`docs/adr/0002-project-task-privacy.md`; comportamiento visible en `docs/usuario/privacidad-proyectos.md`.

### Modelo de acceso (quién ve qué)

```
Project visible si:  owner  OR  PMO Project Member  OR  PMO Executive Access  OR  DocShare
Task visible si:     project vacío (reglas estándar ERPNext)
                     OR Project(Task) visible          (Task hereda la frontera del Project)
                     OR ToDo activo (asignación directa: SOLO esa Task)
                     OR PMO Executive Access  OR  DocShare
```

- **Asignar una Task ≠ ser miembro del Project**: no concede el Project ni otras Tasks.
- **WRITE** — owner: Project + todas sus Tasks · member: Tasks del Project (no el Project) · assignee:
  solo su Task · `PMO Executive Access`: solo lectura · `PMO Manager`: nada por el rol.

### Capa de enforcement (dos mecanismos nativos, sin tocar DocPerms de read/write)

- **Rol nativo = capacidad** (`read`/`write`/…). No se modifican los DocPerm de Project/Task.
- **`permission_query_conditions` (pqc) = alcance en listados**: List / Report Builder / Tree / Gantt /
  Calendar / link / API-list. Funciones `get_permission_query_conditions_project|task` en
  `pmo/permissions.py`.
- **`has_permission` = alcance en documento único / URL / `get_doc`**. Funciones
  `has_permission_project|task`. Semántica v16 verificada: el controlador **solo restringe** — `True`
  concede dentro de la capacidad de rol (AND con el DocPerm), `False`/`None` deniegan → devolvemos
  siempre `True`/`False`.
- **SHARE manual** (`ptype == "share"`): el mismo `has_permission` lo restringe a `PMO Executive Access`
  (+ `Administrator`). No se usa Custom DocPerm (ver ADR-0002 D7). `assign_to` **no** crea auto-share:
  el asignado ya está permitido por el ToDo, así que `assign_to` omite `share.add`.

### Cierre de vectores que ignoran `pqc` (ADR-0002 D11)

`get_all`/`db.sql` fuerzan `ignore_permissions=True` → no reciben `pqc`. Auditados y mitigados:

| Vector | Mecanismo |
|---|---|
| `create_duplicate_project` (whitelisted; `get_all(Task, project=…)`) | Override en `pmo/overrides.py` (`override_whitelisted_methods`) que exige `has_permission("Project","read", throw=True)` sobre el origen |
| Reports `Project Summary`, `Delayed Tasks Summary`, `Project wise Stock Tracking` | `Custom Role` (fixture) que override los roles del report → solo `PMO Executive Access`/`Administrator` |
| Global Search | Ya aplica `has_permission` (nativo) → cubierto |

**Drift a vigilar:** tras `migrate`/upgrade de ERPNext, verificar que los 3 reports mantienen nombre y
`ref_doctype` (un renombre deja huérfano el `Custom Role`) y que los `Custom Role` siguen presentes (el
fixture los re-crea). Reports sustitutos de `pmo` que respeten el boundary: diferidos.

### Objetos nuevos (pmo) y wiring

- **`PMO Project Member`** — child DocType (`istable`), campo `member: Link User`. Custom Field
  `Project-pmo_members` (Table) lo añade a `Project`.
- **Roles** — `PMO Manager` (funcional, sin acceso por el rol), `PMO Executive Access` (read global +
  share; necesita además un rol con capacidad read, p. ej. `Projects User`).
- **`hooks.py`** — `permission_query_conditions`, `has_permission`, `override_whitelisted_methods`.
- **Fixtures** (`pmo/fixtures/`) — `custom_field.json` (`Project-pmo_members`), `role.json`
  (roles PMO), `custom_role.json` (restricción de los 3 reports).
- **Tests** — `pmo/pmo/tests/test_privacy_{read,write,share,reports}.py`.

### Comportamiento de superusuarios / no protegible (documentado)

`Administrator`, `ignore_permissions`, `get_all` y jobs hacen bypass nativo (no protegible).
`System Manager` **sí** está sujeto a `pqc` → sin visibilidad global automática. DocShare es acceso
aditivo intencional (no se bloquea). Timesheet/Expense Claim/Sales Invoice tienen autorización propia y
no se ocultan por tener Project relacionado.

## Capacity Planning (ADR-0003)

Planificación de capacidad **derivada** de la fuente nativa (`Task` + Assignment), sin sistema paralelo
de asignaciones. Decisiones en `docs/adr/0003-resource-capacity.md`; uso en `docs/usuario/capacity-planning.md`.

### Cuatro conceptos (3 derivados, 1 persistido)
- **Capacity** (persistido) — `PMO Capacity`: capacidad horas/día efectivo-datada. `employee` vacío =
  baseline global; con valor = override. Resolución única `pmo.capacity.get_capacity(employee, date)`
  (override → global → `None`; **sin 8h implícitas**). Validación valor>0 y unicidad scope+`from_date`
  (vacío/NULL = scope GLOBAL único).
- **Availability** (derivado) — `pmo.availability.get_availability(employee, date)`: Capacity − festivos
  (Holiday List nativa) − Leave aprobada (**HRMS opcional**, `Leave Application` en runtime; medio día →
  Capacity/2). `Capacity None → None`.
- **PlannedLoad** (derivado) — `pmo.planned_load`: carga de `Task.expected_time` sobre asignados activos
  (`ToDo status="Open"`). Horas por asignado (`get_planned_hours_per_assignee`): 1→E, N→E/N, overrides
  parciales→remanente uniforme, `Σ>E` o todos-override `Σ≠E`→inconsistente. Override opcional
  `ToDo.pmo_planned_hours`. Distribución diaria con `allocation.build_allocation_days` sobre
  `exp_start_date..exp_end_date`. Estados de Task incluidos: Open/Working/Pending Review/Overdue
  (Completed/Cancelled/Template fuera). Bridge `Employee.user_id` fail-closed (ambiguo→excluido).
- **Actual** (derivado) — `pmo.actual`: horas de `Timesheet Detail` (docstatus=1, `hours`, bornes
  `from_time`/`to_time`) **con la semántica oficial de `daily_timesheet_summary`**. No se suma con Planned.

**Retornos estructurados** (integridad, sin pérdida silenciosa): las funciones de PlannedLoad devuelven
`issues` (Tasks inconsistentes), `unscheduled` (horas sin fechas) y `unmapped` (mapeo Employee↔User).

### Reporte `PMO Capacity Planning` (Script Report, P4)
- Fila `Employee × periodo`: Capacity, Availability, Planned visible/confidencial/total, Actual
  visible/confidencial/total, Libre, Sobreasignación, Utilización planificada y real, Estado.
- **Enmascarado P4 server-side** (`ADR-0002`): `Comprometido (confidencial) = total − Σ(visibles)`; los
  Projects/Tasks fuera del boundary del observador **nunca** se enumeran ni se envían al cliente.
  Observador: Executive → todos + desglose; PMO Manager → todos cuantitativos + P4; normal → solo su
  propio Employee + P4. `Estado` solo muestra flags de integridad (sin identidad).
- **Acceso:** `Report.roles` = `Employee`, `PMO Manager`, `PMO Executive Access`, `System Manager`, +
  permiso `report` sobre `ref_doctype = PMO Capacity` (a `Employee` **solo `report`, sin `read`** → no
  expone registros). El row-level real lo impone `execute()`, no el rol.
- Infra interna (no whitelisted): `get_planned_load_by_project`, `get_actual_by_project`,
  `permissions.is_project_visible`.

### Vistas (reportes + Workspace) — estilo MS Project
Todo sobre el motor derivado (no recalcula); enmascarado P4 dentro de `execute()`:
- **`PMO Capacity Planning`** (extendido): `Day/Week/Month/Total` (Total = Centro de recursos),
  `designation`/`department`, `chart` (Availability vs Planned total; sin filtro → agregado por
  Employee), `report_summary` (Recursos/Sobreasignados/Utilización), `formatter` de sobreasignación
  (util <80 normal / 80–100 ámbar / >100 rojo; overallocation>0 y free<0 en rojo).
- **`PMO Resource Usage by Project`**: árbol Employee→Project (`indent`); columna `project` = Data,
  `project_id` auxiliar **solo en visibles** (link vía `get_form_link`); buckets `Sin proyecto` y
  `Comprometido (confidencial)` (una fila, sin id). `get_planned_load_by_project`/`get_actual_by_project`.
  **Modo temporal** (para la Page): si llega `granularity` = `Day/Week/Month`, `execute()` devuelve una
  matriz Proyecto×periodo (columnas dinámicas `period_i` + `Total`), **solo Planned**, con el mismo
  bucketing/labels que `PMO Capacity Planning` y el **mismo P4** (`is_project_visible`); consolidado
  confidencial por periodo, sin id/nombre/conteo. La ruta por defecto (sin `granularity`) queda igual.
- **`PMO Work by Resource`**: tareas por recurso; **doble boundary Task≠Project** (`is_task_visible`
  canónico vía `frappe.has_permission("Task","read")`, incluye DocShare); `planned_hours` en el rango
  (`get_planned_load_by_task`); Task no visible → agregado confidencial; **sin Actual por Task**.
- **Workspace `PMO Capacity`**: solo navegación (3 shortcuts a los reports). **Sin `charts`/`number_cards`**.

**Regla P4 de presentación:** los KPIs/gráficas viven **dentro** del Script Report (per-usuario, sin
caché). **Prohibido** Dashboard Chart / Number Card (`type=Report`) sobre estos reports: `@cache_source`
(clave `chart-data:{name}`, sin usuario) filtraría datos enmascarados entre usuarios. `public=1` del
Workspace = **compartido**, restringido por `roles`; **no** es acceso universal.

### Page `capacity_planning` (arquitectura D) — UX definitiva
Frappe Page propia (Desk) que consume **exclusivamente** los Script Reports vía
`frappe.desk.query_report.run` (P4 en `execute()`, per-usuario, sin caché compartida) + el endpoint
`pmo.capacity_page.get_resources` (metadata segura de Employee, mismo alcance que los reportes; sin
Project/Task). El cliente **no** recalcula nada ni reconstruye P4/buckets. Se descartó Frappe Insights
(su caché de resultados es observer-agnóstica → fuga P4; sin embedding inline en v3.13.1).
- **Controles** (visibles en el contenido): `Desde`/`Hasta`, escala `Día/Semana/Mes`, unidad fija
  `Horas`. **Panel de Empleados** (buscador, multiselección, Todos/Limpiar; selección persistente).
- **Cinco vistas** (paridad MS Project):
  1. **Mapa de calor de capacidad** — matriz Empleado×periodo, celda = `util_planned` (<80/80–100/>100),
     columna Empleado sticky; tooltip Capacity/Availability/Planned/Free/Planned Utilization.
  2. **Uso de recursos** — detalle Empleado×periodo (Capacity/Availability/Planned/Free/Planned Utilization).
  3. **Uso de recursos por proyecto** — **un empleado**; matriz Proyecto×periodo (modo temporal del
     report); links solo con `project_id`.
  4. **Disponibilidad restante** — matriz Empleado×periodo, métrica `Free` (>0 disponible / 0
     comprometido / <0 sobreasignado / Availability=0 → `—`, estado distinto).
  5. **Trabajo por recurso** — **un empleado**; jerarquía Proyecto→Tarea (subject, fechas o `Sin fechas`,
     `planned_hours`, `expected_time`, status); links Task/Project solo con id; tareas ocultas → grupo
     único `Comprometido (confidencial)` solo con horas.
- **Gráficas** con `frappe.Chart` (frappe-charts; sin infraestructura frontend nueva, sin ECharts/CDN).
- **`Actual` no se muestra en ninguna de las cinco vistas** (decisión de etapa; ver *Pendiente futuro*).
- Objetos: `pmo/pmo/page/capacity_planning/` (`.json` standard=Yes, roles Employee/PMO Manager/PMO
  Executive Access/System Manager; `.js`) + `pmo/capacity_page.py` (`get_resources`, whitelisted).

### Pendiente futuro — vista `Planificado vs Real` (a.k.a. `Cumplimiento de planificación`)
Decisión de diseño tomada en el cierre de esta etapa (2026-09-05), **no implementada**:
- Las 5 vistas actuales **no muestran `Actual`**, aunque el rango `Desde/Hasta` pueda abarcar pasado y
  futuro. `Actual` se **reserva** para una vista futura de **análisis histórico**.
- Esa vista comparará **Planned vs Actual** (Actual desde Timesheet, ya derivado por el motor) y podrá
  incluir **variación en horas** y **porcentaje de cumplimiento**. La **semántica exacta** de esos
  indicadores se definirá **al implementarla**.
- **Restricción dura:** no debe modificar el motor (Capacity/Planned Load/Actual), ni P4, ni las 5 vistas
  actuales; se construirá igual que las demás (Script Report P4 + Page), sin caché compartida ni Insights.
- El motor ya expone `Actual` (`get_actual`, `get_actual_by_project`) y el reporte `PMO Capacity Planning`
  ya calcula `actual_*` server-side con P4 — la base existe; solo falta la vista y sus indicadores.

### Objetos nuevos / wiring
- **DocType** `PMO Capacity`. **Custom Field** `ToDo-pmo_planned_hours` (Float, opcional; fixture).
- **Reports** `PMO Capacity Planning`, `PMO Resource Usage by Project`, `PMO Work by Resource`;
  **Workspace** `PMO Capacity`. **DocPerm** `report` en PMO Capacity para Employee/Executive.
- Helpers internos: `get_planned_load_by_project|task`, `get_actual_by_project`,
  `permissions.is_project_visible`, `permissions.is_task_visible`.
- **Page** `capacity_planning` + endpoint `pmo.capacity_page.get_resources` (ver subsección Page).
- Sin cambios de core; se **lee** Task/ToDo/Employee/Holiday List/Timesheet (y Leave si HRMS).
- **Tests** — `test_{capacity,availability,actual,allocation,planned_load,capacity_report,resource_usage,work_by_resource,capacity_workspace,capacity_page}.py` (incluye el camino real de la Page `query_report.run` como Employee normal y el modo temporal de `resource_usage`). **Suite: 131/131.**

## Schedule Governance — intervención sobre Task (ADR-0004 D3)

Mixin `pmo.overrides.PMOTaskScheduleMixin` registrado por `extend_doctype_class = {"Task": ...}` en
`hooks.py`. Redefine **solo** dos validaciones de fecha nativas, dejando `validate_dates()` y el resto
del controlador `Task` intactos (se compone por MRO; `validate_dates()` invoca los submétodos vía
`self.<m>()`, por lo que hereda cualquier validación nueva de upstream):

- `validate_parent_expected_end_date` → **no bloquea**: las fechas de un summary/`is_group` son un
  envelope **no vinculante**; una hija puede extenderse más allá del padre (ADR-0004 D1).
- `validate_parent_project_dates` → **no bloquea**: `Project.expected_*` es **forecast**, no límite duro;
  en particular el **Actual** (`act_start_date`/`act_end_date` desde Timesheet) **nunca** se bloquea por el
  fin planificado del Project (ADR-0004 D2/D3). Esto desbloquea el flujo real de Timesheet
  (`timesheet.py:182` → `Task.save()`), que hoy lanzaría `InvalidDates`.

**Upgrade-safe:** no se copia el cuerpo nativo (que difiere entre 16.32.1 y upstream `7b0df4b`); se
sustituye por la semántica PMO → independiente de versión. **Guard de drift** en
`test_schedule_governance` (falla si `Task` deja de definir esos métodos). La validación nativa hace
`return if frappe.in_test`, por lo que los tests fuerzan `frappe.in_test = False` (context manager con
restauración) para ejercer la ruta de producción. No se toca Capacity/Planned Load.

## Fuera de alcance
Gantt/Tag: sin DocTypes, Custom Fields, fixtures ni patches. Privacidad P0: sin cambios de core ERPNext
ni de DocPerm de read/write; solo hooks, un child DocType propio, roles y `Custom Role` por fixture.
Capacity Planning: derivado de Task+Assignment (sin captura paralela); snapshots/baselines, captura de
horas en el diálogo Assign To y KPIs adicionales quedan fuera del MVP.
