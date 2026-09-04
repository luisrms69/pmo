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

### Objetos nuevos / wiring
- **DocType** `PMO Capacity`. **Custom Field** `ToDo-pmo_planned_hours` (Float, opcional; fixture).
- **Report** `PMO Capacity Planning`. **DocPerm** `report` en PMO Capacity para Employee/Executive.
- Sin cambios de core; se **lee** Task/ToDo/Employee/Holiday List/Timesheet (y Leave si HRMS).
- **Tests** — `test_{capacity,availability,actual,allocation,planned_load,capacity_report}.py`.

## Fuera de alcance
Gantt/Tag: sin DocTypes, Custom Fields, fixtures ni patches. Privacidad P0: sin cambios de core ERPNext
ni de DocPerm de read/write; solo hooks, un child DocType propio, roles y `Custom Role` por fixture.
Capacity Planning: derivado de Task+Assignment (sin captura paralela); snapshots/baselines, captura de
horas en el diálogo Assign To y KPIs adicionales quedan fuera del MVP.
