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

> **Membresía derivada (revisado v0.6.0):** no hay lista custom de miembros. El equipo del Project se
> deriva de `owner + DocShare(Project) + ToDo activo(Task)`.

```
Project visible si:  owner  OR  DocShare(Project, read)  OR  PMO Executive Access
Task visible si:     project vacío (reglas estándar ERPNext)
                     OR Project(Task) visible   (Task hereda la frontera; un DocShare de Project alcanza
                                                 sus Tasks por decisión del hook)
                     OR ToDo activo (asignación directa: SOLO esa Task)
                     OR PMO Executive Access
```

- **Asignar una Task ≠ ser miembro del Project**: no concede el Project ni otras Tasks.
- **WRITE (D6, honra flags de DocShare)** — owner: Project + todas sus Tasks · `DocShare(Project, write)`:
  Project + sus Tasks · `DocShare(Project, read)`: solo lectura · assignee (ToDo): solo su Task ·
  `PMO Executive Access`: solo lectura · `PMO Manager`: nada por el rol.

### Capa de enforcement (dos mecanismos nativos, sin tocar DocPerms de read/write)

- **Rol nativo = capacidad** (`read`/`write`/…). No se modifican los DocPerm de Project/Task.
- **`permission_query_conditions` (pqc) = alcance en listados**: List / Report Builder / Tree / Gantt /
  Calendar / link / API-list. Funciones `get_permission_query_conditions_project|task` en
  `pmo/permissions.py`.
- **`has_permission` = alcance en documento único / URL / `get_doc`**. Funciones
  `has_permission_project|task`. Semántica v16 verificada: el controlador **solo restringe** — `True`
  concede dentro de la capacidad de rol (AND con el DocPerm), `False`/`None` deniegan → devolvemos
  siempre `True`/`False`.
- **SHARE manual** (`ptype == "share"`): el mismo `has_permission` permite compartir el **Project** al
  **owner** (así incorpora colaboradores) + `PMO Executive Access`/`Administrator`; el share de **Task**
  queda a Executive/Admin (excepcional). No se usa Custom DocPerm (ver ADR-0002 D7). `assign_to` **no**
  crea auto-share: el asignado ya está permitido por el ToDo, así que `assign_to` omite `share.add`.

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

- **Membresía derivada (v0.6.0)** — sin child DocType. Fuentes nativas: `owner`, `DocShare(Project)`
  (helper `_has_project_share` / subquery en `tabDocShare`), `ToDo` activo (`_has_active_todo`). El child
  `PMO Project Member` y el Custom Field `Project-pmo_members` se **retiran del código y de las fixtures**
  (una instalación nueva nunca los crea). En pmo **no se distribuyen migration patches**: la limpieza de
  un sitio de desarrollo que aún los tenga es una operación **manual, puntual y fuera de banda** (no
  shippeada, no `after_migrate`, no hook), que aborta si hubiera filas para no perder membresía silenciosa.
- **Roles** — `PMO Manager` (funcional, sin acceso por el rol), `PMO Executive Access` (read global +
  share; necesita además un rol con capacidad read, p. ej. `Projects User`).
- **`hooks.py`** — `permission_query_conditions`, `has_permission`, `override_whitelisted_methods`.
- **Fixtures** (`pmo/fixtures/`) — `custom_field.json` (`ToDo-pmo_planned_hours`), `role.json`
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
> **Actualización (ADR-0008):** el reporte de esfuerzo Planificado vs Real por Project/Task ya se entregó
> como Script Report independiente `PMO Planned vs Actual` (ver sección "Planificado vs Real — reporte de
> esfuerzo (ADR-0008)"). Lo que sigue pendiente aquí es la **vista integrada en la Page de Capacity** con el
> rango temporal Desde/Hasta; esa integración no se abordó y las restricciones de abajo siguen vigentes.

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

## PMO Project Baseline (ADR-0004)

DocType **submittable** (`is_submittable`, autoname `PMO-BL-.#####`) que congela el plan de un Project
como referencia aprobada. **Schedule / Operational Planning Baseline** (no una PMI Scope Baseline
completa). Engine sin persistencia en `pmo/baseline.py`.

- **Lineage (configuration control lineal):** `baseline_type` (Original/Approved Change/Replan) +
  `supersedes_baseline`. Invariantes en `validate()`: una sola Original válida (no cancelada) por Project;
  `revision` única por Project; una baseline no-Original debe sustituir la **cabeza vigente** (Submitted y
  no Cancelada, del mismo Project); sin self-supersede, sin ciclos, sin bifurcación. `effective_date` no
  futura (Opción B: sin future-effective). **Sin `is_current`** (se deriva) ni `change_request` (v0.6.0).
- **Aprobación:** `approved_by`/`approved_at` se fijan **en `before_submit`** (el Submit es el acto formal
  de aprobación); `snapshot_at` = captura técnica. No hay `submitted_by` (redundante con `approved_by`).
- **Snapshot canónico (`before_submit`):** `build_snapshot(project)` → Project + Tasks con identidad WBS
  estable (`name` + `parent_task` + `wbs_order` derivado del orden `lft` al congelar, **no** `lft/rgt`),
  `description`, fechas/horas/estado, `depends_on`, y `assignments` `{user, employee, override_hours,
  effective_hours}` (override solo si `pmo_planned_hours>0`, coherente con el motor; `effective_hours` de
  `get_planned_hours_per_assignee`). Se persiste la forma **canónica** (claves ordenadas) y su
  `snapshot_hash` sha256 determinista + `snapshot_schema_version`.
- **Preflight ligero (`run_preflight`):** `warnings` (leaf sin fechas, `is_group` con esfuerzo/asignaciones,
  summary dates stale vs envelope, assignment sin Employee, issues de Planned Load) y `blocking` (reparto
  de horas inconsistente → impide `effective_hours`). Se **bloquea** el Submit solo ante `blocking`.
- **P4 (ADR-0002/0004 D7):** `has_permission_baseline` (read = `is_project_visible`; write/submit/cancel =
  solo owner del Project; Executive read-only; share denegado) + `get_permission_query_conditions_baseline`
  (listados solo de projects visibles). **PMO Manager sin acceso** por rol.
- **Baseline vigente as-of:** `get_effective_baseline(project, as_of)` = cabeza de la cadena (mayor
  `effective_date <= as_of`, Submitted/no-Cancelada).
- **Comparación de snapshots:** diferida (issue #5); el esquema canónico ya la habilita.

## PMO Change Request (ADR-0005)

DocType **submittable** (`is_submittable`, autoname `PMO-CR-.#####`) que **gobierna** un cambio del Project
(por qué, impacto previsto, decisión, implementación). El **alcance** y su valuación viven en la
`Quotation`/`erpnext_proposals` (no se recapturan Scope Items); `Project`/`Task` recibe el alcance
aprobado; `PMO Project Baseline` congela el before/after; `Timesheet` registra el Actual.

> **Estado (v0.6.0 en construcción):** entregados el DocType + P4 + invariantes base, el **Workflow +
> acción "Aplicar Quotation al Project" + semántica Aplicado/Implementado**, el **comparator
> Baseline↔Baseline** y el **Change Register**. Pendiente: cierre + bump 0.6.0 y la validación comercial
> end-to-end (dependencia de `erpnext_proposals`).

- **Campos:** solicitud (`project`, `title`, `raised_by`, `origin`, `request_date`, `priority`
  Baja/Media/Alta, `reason`, `description`); impacto mínimo estructurado (5 Checks
  `impacts_scope|schedule|effort|commercial|risk` → `impact_summary` computado; deltas `impact_hours`/
  `impact_days`/`impact_amount` con `currency`; `impact_notes`, `evaluation_notes`); proposal
  (`proposal_group`, `applied_quotation`); baselines (`baseline_before`, `baseline_after`); decisión
  (`approved_by`, `approved_at`, `decision_notes`); implementación (`applied_to_project`, `applied_at`,
  `implementation_notes`). **Sin** severidad por dimensión, fechas propias, dimensión de calidad ni
  business case (viven en Quotation/Tasks/Baseline o son gaps reconocidos).
- **Persistencia post-submit:** los campos que cambian tras aprobar son **`allow_on_submit`**
  (`applied_to_project`, `applied_at`, `applied_quotation`, `baseline_after`, `implementation_notes`); el
  contenido de la solicitud queda **inmutable** por el core (`_validate_update_after_submit`), sin
  `frappe.db.set_value` de rescate.
- **Invariantes base (`pmo_change_request.py`):** defaults (`raised_by`, `request_date`, `priority`);
  `impact_summary` (orden estable de los 5 tipos); `currency` = moneda de la company del Project;
  integridad de baselines (mismo Project; `baseline_after` ≠ `baseline_before`; `effective_date` de
  after ≥ before). `before_submit` fija `approved_by`/`approved_at` (aprobar = Submit). `before_cancel`
  bloquea si `applied_to_project` o `baseline_after` (la realidad/baseline ya cambió → revertir = CR nuevo).
- **P4 (ADR-0002/0005 D13):** `has_permission_change_request` (read = `is_project_visible`; create/write =
  project writer owner o member, con write de **member solo en `docstatus 0`**; submit/cancel/amend =
  **owner** → sella owner-only para aprobar/rechazar; Executive read-only; share denegado) +
  `get_permission_query_conditions_change_request` (listados solo de projects visibles). **PMO Manager sin
  acceso** por rol. Helper `_is_project_writer` (owner o member) reutilizado del boundary P0.

### Workflow `PMO Change Request` (fixture) y gates

`Borrador(0) → En Revision(0) → Aprobado(1) / Rechazado(1) → Implementado(1) → Cerrado(1)`. Fixtures:
`workflow.json` (+ `workflow_state.json` con los 6 estados en español; el Custom Field `workflow_state`
lo crea el propio Workflow). El framework auto-selecciona el primer estado con `doc_status=1` en un submit
directo, por lo que el gate de baseline se ancla también en `before_submit` (red de seguridad).

- **Autoridad owner-only** en `Aprobar`/`Rechazar`/`Marcar Implementado`/`Cerrar`: **doble capa** —
  `condition` de transición `frappe.db.get_value("Project", doc.project, "owner") == frappe.session.user`
  (la UI no ofrece la acción a quien no es owner) **y** el gate P4 sobre `submit`/`write`. `Enviar a
  Revision` y `Devolver a Borrador` no llevan condición (los miembros participan). `allow_self_approval=1`
  (se acepta autoaprobación del owner).
- **Gates por transición** (`_apply_workflow_gates`): al entrar a `En Revision`, exige baseline vigente
  (`get_effective_baseline`) y **congela `baseline_before`**; a `Implementado`, si hay `proposal_group`
  exige `applied_to_project`; a `Cerrado`, exige `baseline_after`. Como Frappe ejecuta **solo**
  `before_update_after_submit` (no `validate`) en transiciones submitted→submitted, los gates y la
  integridad de baselines se re-aplican también en ese hook.
- **`before_cancel`** añade el bloqueo de estados terminales (`Rechazado`/`Cerrado`) además de
  `applied_to_project`/`baseline_after`.

### Integración con `erpnext_proposals` — contrato publicado (>= 0.22.0)

PMO **delega** en el contrato publicado de `erpnext_proposals` vía `pmo/change_control.py` (dos delegadores
resueltos por `frappe.get_attr` = feature-detection; error claro si el app no está o es `< 0.22.0`). PMO no
interpreta `<ROOT>-ADD-<NN>`, no calcula secuencia, no crea `proposal_group`, no resuelve el Project desde
`project_name`, no escribe `proposal_project` ni crea Tasks del addendum.

- **Crear addenda** — `crear_addenda(change_request)` (botón "Crear addenda comercial", visible sobre un CR
  **editable** `docstatus 0` sin `proposal_group`). Localiza la Quotation del contrato por la relación
  persistente `Quotation.proposal_project == CR.project` y delega en
  `change_control.create_addendum_quotation` → `erpnext_proposals.utils.addendum.create_addendum_quotation`
  (crea la addenda `ROOT-ADD-NN`, delta comercial, atómica). Persiste la identidad en el campo existente
  `proposal_group`. **Autoridad (sin elevación):** exige `write` P4 sobre el CR **y** autoría comercial
  (`assert_can_manage_proposals` la impone `erpnext_proposals`; si falta → `PermissionError`).
- **Aplicar** — `aplicar_quotation_al_project(change_request, quotation)` (botón, owner sobre CR `Aprobado`
  no aplicado). Delega en `change_control.apply_addendum_to_project` →
  `erpnext_proposals.utils.project.apply_addendum_to_project`; si completa, fija
  `applied_to_project`/`applied_at`/`applied_quotation` (`allow_on_submit`). **`Ganada` ≠ `Aplicada`**: la
  aplicación es explícita. **Frontera dura:** PMO no escribe `proposal_project` ni reproduce guards
  comerciales.
- **Atomicidad:** ambas acciones son atómicas con su request (sin commit manual en el contrato); un fallo
  externo revierte también la addenda / no deja `applied_*` parciales.
- **Precondición de entrega:** `erpnext_proposals >= 0.22.0` instalado en el sitio (feature-detection por
  `get_attr`). Ver ADR-0005.

### Comparator Baseline ↔ Baseline (D11)

`pmo/compare.py`: `compare_snapshots(before, after)` es una **función pura** que opera **solo sobre los
snapshots v1 ya almacenados** (no reconstruye ni lee el Current Plan). Detecta: Tasks añadidas/eliminadas
(identidad = `name`), y por Task cambios en `exp_start_date`/`exp_end_date`/`expected_time`/`status`/
`parent_task`/`wbs_order` y en assignments (usuarios añadidos/eliminados, `override_hours`,
`effective_hours`); más cambios de Project (`expected_start_date`/`expected_end_date`/`status`). Orden
determinista (todo ordenado por `name`/`user`). Devuelve `project_changes`/`tasks_added`/`tasks_removed`/
`tasks_changed`/`has_changes`.

`compare_baselines(baseline_before, baseline_after)` (whitelisted): **P4** = `check_permission("read")` sobre
**ambas** baselines (= `is_project_visible`) + exige **mismo Project** (sin fuga cross-project); carga los
snapshots persistidos y delega en `compare_snapshots`. El orden de argumentos define la dirección
(from→to); no reordena. Es una **diferencia entre baselines**, no una atribución por CR (varios CR pueden
consolidarse en una misma `baseline_after`).

**UI — Script Report `PMO Baseline Comparison` (patrón `Compare Projects` de MS Project):** reporte a
**pantalla completa** (`report_type = "Script Report"`, `ref_doctype = PMO Project Baseline`) que reemplaza
al modal (retirado). Filtros: `project`, `baseline_before`, `baseline_after` (+ `change_request` como
**contexto de apertura**, no atribución). `execute(filters)` **reutiliza `compare_baselines()`** (no otro
engine): esa función impone la **P4** (read en ambas + mismo Project); como los Script Report **no** aplican
`pqc`, la P4 se valida ahí dentro por delegación (patrón de los reports P4 de la app). Aplana el diff a
**solo diferencias**, una **fila por diferencia atómica** — columnas *Tipo de cambio / WBS-Tarea / Campo /
Antes / Después / Variación* (variación en `±días` para fechas y `±h` para horas) — con cabecera
(`message`) y tarjetas de resumen (`report_summary`: añadidas/eliminadas/modificadas/asignaciones/cambios
de Project). **Exportación/impresión nativas** del Report (Excel/CSV/Print), secundarias. No persiste el
diff. Accesos: botones en el Change Request (*"Comparar líneas base"*, con `baseline_before`+`baseline_after`,
pasa el CR como contexto) y en el Baseline (*"Comparar con línea base anterior"*, usa `supersedes_baseline`)
que hacen `set_route` al reporte ya parametrizado. Sin overlay Gantt, timeline, gráficos ni edición.

**`baseline_after` — selección explícita guiada (D5):** la relación es de negocio (qué baseline incorpora
el cambio), **no** "la vigente al instante", así que **no** se automatiza. Se mantiene editable pero el
picker se filtra con `baseline_after_query` (baselines Submitted del mismo Project, distintas de
`baseline_before` y con `effective_date >= baseline_before.effective_date`), y un botón *"Usar línea base
vigente"* (`get_current_baseline`, P4) la **prellena** como conveniencia sin impedir escoger otra. El gate
de Cerrar sigue exigiendo `baseline_after`.

**i18n:** las etiquetas visibles de `PMO Change Request` y `PMO Project Baseline` están en **español** en el
JSON (convención del ecosistema; el sitio corre en `en`). Se mantienen en inglés los identificadores
técnicos: fieldnames, valores de Select usados por el código (p. ej. `baseline_type`
Original/Approved Change/Replan), y nombres de DocType/Report.

### Change Register (D12)

Reporte estándar **`PMO Change Register`** (`report_type = "Report Builder"`, `is_standard = Yes`,
`ref_doctype = PMO Change Request`, módulo PMO) en `pmo/pmo/report/pmo_change_register/`. Al ser un Report
Builder consulta la **lista del DocType**, por lo que aplica **`permission_query_conditions` automáticamente
(P4-safe)** — se evita deliberadamente Query/Script Report (que ignoran `pqc`). Columnas: `name`, `project`,
`title`, `workflow_state`, `request_date`, `priority`, `impact_summary`, `impact_hours`, `impact_days`,
`currency`, `impact_amount`, `proposal_group`, `applied_quotation`, `baseline_before`, `baseline_after`.
Orden por defecto `request_date` desc, luego `priority` desc. Roles: `Projects User`, `PMO Executive
Access`, `System Manager` (abren el reporte; las filas las restringe `pqc`). **PMO Manager** no accede.

## Control a fecha de corte / Status Date (ADR-0006)

- **Status Date** — Custom Field **`Project.pmo_status_date`** (Date, por **fixture**; requiere `bench
  migrate` para sincronizar la metadata, sin data/migration patch). Es la Data Date vigente del Project.
  Validación en `Project.validate` (`doc_events` → `pmo.status_date.validate_project_status_date`): **solo
  `<= today`** (D2; vacío válido). Lo edita el owner (P4 write del Project).
- **Motor** `pmo/status_date.py`: `build_status_report(project, status_date)` (**whitelisted, P4** vía
  `has_permission("Project", "read", throw)`) compone tres planos a la fecha de corte:
  - **Baseline** = snapshot de `get_effective_baseline(project, as_of=status_date)` (ADR-0004, sin
    modificar 0004); None + `note` si no hay baseline vigente a la fecha.
  - **Current** = `build_snapshot(project)` (plan de hoy; **no** reconstruye el plan histórico).
  - **Actual** = `_actual_hours_to_date` (Timesheet, ADR-0003, docstatus=1; **SQL estática parametrizada**,
    semgrep-safe) + `completed_on` como proxy de completitud.
  - **Indicadores D5** (`compute_status`, pura): (1) deslizamiento de fecha final Baseline vs Current en
    días; (2) tareas que debían estar terminadas a la fecha y no lo estaban; (3) Actual hours acumuladas;
    (4) conteos simples (due/completadas). `is_group` excluidas.
- **Reporte** `PMO Status Report` (`report_type = Script Report`, `is_standard = Yes`, `ref_doctype =
  Project`, módulo PMO) en `pmo/pmo/report/pmo_status_report/`. **P4-safe por delegación**: `execute` llama a
  `build_status_report` (que impone P4), ya que los Script Report no aplican `pqc`. Resumen = indicadores
  D5; detalle = tareas vencidas no terminadas. Filtros `project` + `status_date` (default desde
  `pmo_status_date`, tope `today`). Roles `Projects User` / `PMO Executive Access` / `System Manager`.
- **Fuera (ADR-0006 D6):** EVM/forecast, CPM (#9), reservas de capacidad (#10), Planned-vs-Actual completo
  de horas, avance % histórico y fecha futura.

### Forecast vigente y desviaciones (ADR-0009, amplía el Status Report)
El **forecast vigente es el plan vivo de ERPNext** (`expected_end_date`/`exp_end_date`); PMO **no** crea un
segundo motor predictivo, solo agrega señales de desviación. `compute_status`/`build_status_report` se amplían
de forma **retrocompatible** (la firma de 5 args sigue válida):
- `slip_vs_committed_days` — Project: `expected_end_date - pmo_committed_end_date` (positivo = el forecast
  excede el compromiso; `None` sin compromiso).
- `forecast_exceeds_commitment.count` — Tasks (no `is_group`) con `exp_end_date > pmo_deadline`. **Distinto de
  "vencida"**: puede ser fecha futura con incumplimiento ya proyectado. Se mantiene separado de
  `tasks_overdue_at_cutoff` (vencidas al corte).
- `tasks_vs_baseline` — **tabla única por Task** (con baseline): `baseline_exp_end_date`,
  `current_exp_end_date`, `slip_days`, `pmo_deadline`, `overdue_at_status_date`, `completed_at_status_date`.
  Helper `_current_task_map` lee el plan vigente + deadline por Task.
- `committed_end_date` en el retorno para la tarjeta "Forecast vigente (plan)".
- **Presentación** (`PMO Status Report`): detalle = tabla única ordenada por slip desc; resumen = forecast
  vigente + deslizamiento vs Baseline + deslizamiento vs compromiso + conteo forecast-excede-compromiso, junto
  a los indicadores previos. **`PMO Planned vs Actual` intacto** (sin ETC/EAC ni forecast por `progress`).
- **Sin** DocTypes/Custom Fields/esquema (`snapshot_schema_version` = 1). Tests: `test_forecast_deviations.py`
  (motor) + `test_status_report.py` (presentación).

## Fecha comprometida de cronograma (ADR-0007)

Distingue la fecha **planeada/calculada** (nativa: `Task.exp_end_date`, `Project.expected_end_date`, que se
desplazan con dependencias/reprogramación; forecast no vinculante, ADR-0004) de la fecha **comprometida**
(compromiso de negocio/acordado, no necesariamente contractual; no se desplaza automáticamente con el
cronograma, pero **sí** puede cambiarse por edición autorizada).

- **Campos (Custom Field por fixture):** `Task.pmo_deadline` (Date) y `Project.pmo_committed_end_date`
  (Date). Requieren `bench migrate` para sincronizar metadata; sin data/migration patch.
- **Validaciones suaves** (`pmo/schedule_commit.py`, `doc_events` `Task.validate` + `Project.validate`):
  avisan (`msgprint`, indicador naranja) si `exp_end_date` > `pmo_deadline` o `expected_end_date` >
  `pmo_committed_end_date`. **No bloquean** el guardado ni el Actual/Timesheet (coherente con ADR-0004);
  campos vacíos = sin aviso. Las fechas del aviso se formatean en ISO directo (no `format_date`) para no
  depender del locale (evita que el aviso se vuelva excepción en sesiones sin idioma).
- **Fuera de alcance (ADR-0007):** constraints tipados (SNET/FNLT/MSO/MFO), auto-reprogramación, scheduler
  propio. **No** cambia el snapshot de Baseline (`snapshot_schema_version` sigue en 1) ni el reporte Status
  Date.

## Planificado vs Real — reporte de esfuerzo (ADR-0008)

Capacidad de **reporting** (no una capa de planificación): pone lado a lado datos ya nativos, que ERPNext no
entrega armados por Project/Task. **Sin** motor nuevo, DocType, Custom Field ni cambios a Baseline
(`snapshot_schema_version` sigue en 1); toda la lógica vive en el `execute()` del reporte + dos helpers
`as-of` en `pmo/actual.py`.

- **Report** `PMO Planned vs Actual` (Script Report `is_standard`, `ref_doctype` Project; roles Projects
  User / PMO Executive Access / System Manager). Sincroniza por `bench migrate` (fixture `is_standard`).
- **Planned** = `Task.expected_time`. **Actual**: sin `status_date` → `Task.actual_time` (acumulado nativo);
  con `status_date` → Σ `Timesheet Detail.hours` submitted hasta el **fin del día** de corte.
- **Indicadores por Task hoja:** Planned, Actual, **Variance** = `Actual - Planned`, **% Consumed** =
  `Actual / Planned` (guarda de división por 0 → vacío). **Rollup** excluye `is_group` (envelope, evita doble
  conteo). Total de Project en las tarjetas de `report_summary`.
- **Helpers `as-of`** (`pmo/actual.py`, internos): `get_actual_hours_asof(project, status_date)` y
  `get_actual_hours_by_task_asof(...)`. Corte inclusivo `from_time <= timestamp(status_date, '24:00:00')`
  (= medianoche del día siguiente ≡ `date(from_time) <= status_date`); solo `docstatus = 1`; SQL estática
  parametrizada (semgrep `frappe-sql-format-injection`). Misma semántica de horas de ADR-0003.
- **P4:** los Script Report no aplican `permission_query_conditions`, así que `execute()` **exige**
  `pmo.permissions.is_project_visible(project, user)` (owner / DocShare / PMO Executive Access), como el
  resto de reportes P4 de la app; si no, `frappe.PermissionError`.
- **Cliente** (`.js`): al elegir Project prellena `status_date` desde `Project.pmo_status_date`; `status_date`
  admite solo `≤ today`.
- **Workspace `PMO Control`** (public, module PMO, `is_standard`; roles Projects User / PMO Executive
  Access / System Manager) — mismo patrón de shortcuts que `PMO Capacity` (header + bloques `shortcut` tipo
  Report): enruta a `PMO Planned vs Actual`, `PMO Status Report`, `PMO Baseline Comparison` y
  `PMO Change Register`. **Solo navega** (sin `charts`/`number_cards`; no duplica lógica ni caché). **No
  toca `PMO Capacity`**. Sincroniza por `bench migrate`.
- **Tests** — `test_planned_vs_actual.py`: puros (`_rows`/`_pct`/`_columns`, exclusión de `is_group`) +
  integración (corte `as-of` cuenta las horas del propio día de corte y excluye el día siguiente; `execute()`
  end-to-end; P4 bloquea a no-miembros). `test_control_workspace.py`: existencia, 4 shortcuts, roles, sin
  métricas cacheadas, y `PMO Capacity` intacto.

## Fuera de alcance
Planificado vs Real (ADR-0008): sin EVM (EV/PV/AC), CPI/SPI, forecast (EAC/ETC), planned time-phased/BCWS,
ni Baseline como fuente del plan; el Workspace de control no añade Number Cards ni charts.
Gantt/Tag: sin DocTypes, Custom Fields, fixtures ni patches. Privacidad P0: sin cambios de core ERPNext
ni de DocPerm de read/write; solo hooks, un child DocType propio, roles y `Custom Role` por fixture.
Capacity Planning: derivado de Task+Assignment (sin captura paralela); snapshots/baselines, captura de
horas en el diálogo Assign To y KPIs adicionales quedan fuera del MVP.
