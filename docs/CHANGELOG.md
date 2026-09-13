# Changelog — pmo

## [0.16.0] — 2026-09-12

Arquitectura de reporting canónica de Project Control: una fuente, muchas vistas. Introduce el contexto
canónico `build_project_control` (ADR-0011), el Reporte Ejecutivo v1, Calidad de Planeación y el **bloque
económico** que consume el contrato de `erpnext_proposals` sin recalcular economía (ADR-0012).

### Added
- **ADR-0011** — contexto canónico único `build_project_control(project, cutoff, sections, audience)`:
  compone (no recalcula) los motores de dominio; Page/HTML/PDF/Portal son consumidores.
- **Reporte Ejecutivo v1** — vista integral en la Page `PMO Control de Proyecto`, con template único
  (`templates/project_control/executive.html`) compartido con el Print Format `PMO Project Status`.
- **Calidad de Planeación** — Madurez de planeación (5 componentes evaluables) + tareas activas sin
  responsable (responsable vigente = ToDo `Open`).
- **Bloque económico (ADR-0012)** — sección `costs`:
  - Frontera opcional `pmo/project_economics.py` (import lazy a `erpnext_proposals`; `required_apps` sigue
    `["erpnext"]`); 3 estados diferenciados (`app_absent`/`no_proposal`/`inconsistent`) + ok, sin degradar
    inconsistencia a ausencia.
  - Gate económico único server-side (`can_see_project_economics`): rol {PMO Manager, PMO Executive Access,
    System Manager} **AND** Project READ, evaluado antes de componer; sin él la sección no existe en el payload.
  - `comparable_cost` (costing+purchase, vs autorizado) separado de `gross_margin_cost_basis` (+material,
    base del margen bruto nativo); margen autorizado y bruto registrado lado a lado, sin recalcular.
  - Bloque compacto en el Reporte Ejecutivo (solo Page) + pestaña **Financiera** (`financial.html` vía
    `get_financial_html`). **Excluida del Print Format/PDF** (decisión estructural).
- Documentación: `docs/adr/0011-*`, `docs/adr/0012-*`, `docs/tecnico/arquitectura.md`,
  `docs/usuario/project-control.md`. Tests: `test_project_control.py` (ampliado), `test_project_economics.py`.

### Changed
- `pmo_project_status()` converge hacia el builder canónico (wrapper delgado); `pmo/health.py` confirmado
  como fuente única de salud.
- `impact_amount`/`impact_days` de `PMO Change Request`: descripción explícita de **estimación no
  vinculante** (la valuación autoritativa vive en la Quotation).

## [0.13.0] — 2026-09-10

Ronda i18n: la app pasa a **inglés como fuente canónica** y trae su **propio catálogo español**
(`pmo/pmo/locale/es.po`), quedando autónoma en `en`/`es` sin depender de `buzola_translations`.
Sin cambios de esquema ni de lógica (la lógica compara claves internas estables; `_()`/`__()` solo
en presentación). Detalle en `docs/tecnico/i18n.md`.

### Changed
- Todo el texto visible (Python/JS/Jinja/DocType JSON/reportes/workspaces/Print Format) normalizado a
  **inglés como fuente**; el español lo aporta el catálogo propio.
- **Workflow States/Actions** de `PMO Change Request` canónicos en inglés (Draft/In Review/Approved/
  Rejected/Implemented/Closed; Send for Review/Return to Draft/Approve/Reject/Mark Implemented/Close):
  masters ingleses creados vía fixtures **sin renombrar** los compartidos con `erpnext_proposals`.
- Valores de Select propios (`priority`, `origin`) canónicos en inglés.

### Added
- Catálogo propio: `pmo/pmo/locale/main.pot` + `pmo/pmo/locale/es.po`.
- `ignore_translatable_strings_from = ["frappe", "erpnext"]` (hereda base, no duplica; **no** `hrms`).
- Marcadores `N_()` para strings que gettext no extrae solo (Workflow, Print Format, labels de reportes).
- `docs/tecnico/i18n.md`.

## [0.12.0] — 2026-09-10

Ronda "product-readiness": preparar PMO para uso/venta cerrando huecos de consumo (visión de portafolio,
captura de capacidad, salida presentable) sin nueva capa de planificación. Solo capa de reporte/navegación;
sin DocTypes/Custom Fields/esquema. Backlog diferido preservado en `docs/roadmap.md`.

### Added
- **`PMO Resource Capacity`** (Script Report) — cobertura/mantenimiento de capacidad: por recurso, capacidad
  efectiva a una fecha, **origen** (Override/Global/**Faltante**) y vigencia; scope por observador. Nuevo
  resolver único `pmo.capacity.get_capacity_detail` (`get_capacity` queda como wrapper). Ergonomía del
  formulario `PMO Capacity` (default From Date + ayuda).
- **`PMO Portfolio`** (Script Report P4) — salud multi-proyecto: una fila por Project visible (En plan/En
  riesgo/Desviado, forecast, slip vs Baseline/compromiso, vencidas, forecast>compromiso, Planned/Actual/%).
  Reutiliza `build_status_report` + esfuerzo nativo; sin motor nuevo.
- **`PMO Project Status`** (Print Format estándar Jinja, doc_type Project) — salida presentable a stakeholder
  (HTML/PDF): resumen ejecutivo + evaluación organizada de tareas **relevantes** (vencidas/slip≠0/forecast>
  deadline/hitos) con conteo de omitidas. Método Jinja `pmo.print_status.pmo_project_status`. Fechas ISO;
  agnóstico al generador PDF (wkhtmltopdf por defecto; Gotenberg vía config del site).
- **Workspace `PMO`** (landing) — punto de entrada único: shortcuts hero + cards que agrupan los reportes de
  control y capacidad + configuración. No modifica `PMO Capacity`/`PMO Control`.

### Changed
- **`docs/usuario/capacity-planning.md`** — corrige nota stale: `PMO Capacity Planning` **sí** muestra Actual
  (columnas + Util. real %); Planned y Actual no se suman.
- **`docs/roadmap.md`** — índice consolidado del backlog (entregado vs diferido con tiers).

### Notes
- Sin DocTypes/Custom Fields/esquema; requiere `bench migrate` (sincroniza reportes, Print Format y
  workspace, fixtures `is_standard`). No toca el modelo derivado de ADR-0003 ni el Print Format del cliente.

## [0.11.0] — 2026-09-09

Confiabilidad de Capacity Planning (ADR-0010, Accepted): señal de sobreasignación honesta y visibilidad de
cobertura de capacidad. Solo capa de reporte; sin esquema. **Último ciclo funcional** de la ronda; después,
revisión global de producto (backlog en `docs/roadmap.md`).

### Changed
- **`PMO Capacity Planning` — señal honesta (A):** si un recurso no tiene `PMO Capacity` vigente en el
  periodo, `capacity`/`availability`/`free`/`overallocation`/`util_planned`/`util_actual` quedan en **`None`**
  (no 0); ya **no** se marca como sobreasignado por falta de capacidad (conserva `status="capacidad faltante"`).
- **KPI *Sobreasignados*** ahora cuenta solo sobreasignación **real** (con capacidad presente).

### Added
- **KPI "Recursos sin capacidad vigente" (B):** nº de recursos **con actividad** en el periodo sin capacidad
  configurada, para detectar y corregir el hueco.
- **`docs/roadmap.md`:** backlog técnico durable con los pendientes diferidos (Tentativo/Confirmado; reservas
  #10; CPM #9; constraints SNET/FNLT/MSO/MFO; UX `pmo_planned_hours`; UX captura `PMO Capacity`) y la regla de
  revisión global posterior a v0.11.0.

### Notes
- Sin DocTypes/Custom Fields/fixtures; sin cambios a `capacity.py`/`availability.py`/`planned_load.py`;
  ADR-0003 sin modificar. No requiere `bench migrate`.

## [0.10.0] — 2026-09-09

Forecast vigente y desviaciones (ADR-0009, Accepted): el forecast es el plan vivo de ERPNext
(`expected_end_date`); PMO **no** crea un segundo motor predictivo, agrega señales de desviación al
`PMO Status Report`.

### Added
- **`PMO Status Report` — desviaciones nuevas:** deslizamiento **vs fecha comprometida**
  (`expected_end_date - pmo_committed_end_date`), conteo de **Tasks cuyo forecast excede la fecha
  comprometida** (`exp_end_date > pmo_deadline`, distinto de "vencida"), y tarjeta **"Forecast vigente
  (plan)"** con el `expected_end_date` como forecast del plan (no una segunda fecha calculada).
- **Tabla única por Task** (con baseline): fin Baseline, fin Forecast, **slip (días)**, fecha comprometida y
  marca de **vencida al corte**, ordenada por slip descendente. Subsume la antigua tabla de solo vencidas.
- **Motor** (`pmo/status_date.py`): `compute_status`/`build_status_report` amplían de forma retrocompatible
  con `slip_vs_committed_days`, `forecast_exceeds_commitment`, `tasks_vs_baseline` y `committed_end_date`.

### Notes
- `tasks_overdue_at_cutoff` (vencidas al Status Date) se mantiene como indicador diferenciado.
- Sin DocTypes/Custom Fields/esquema (`snapshot_schema_version` = 1). `PMO Planned vs Actual` intacto.
- Fuera de alcance: EAC/ETC, forecast por `progress`, EVM/CPI/SPI, CPM (#9), reservas (#10), constraints
  tipados, segunda fecha final calculada.

## [0.9.0] — 2026-09-09

Planificado vs Real (ADR-0008, Proposed): reporte de esfuerzo que responde "¿cuánto planificamos vs cuánto
hemos consumido?" por Project/Task. Es un **hueco de reporting** — los datos ya son nativos —, no una nueva
capa de planificación.

### Added
- **Report `PMO Planned vs Actual`** (Script Report `is_standard`, `ref_doctype` Project) — Planned =
  `Task.expected_time`; Actual = `Task.actual_time` (nativo) o Σ Timesheet submitted **as-of** `status_date`;
  indicadores **Variance Hours** (`Actual - Planned`) y **% Consumed** (`Actual / Planned`, guarda /0). Detalle
  por Task hoja + total de Project excluyendo `is_group` del rollup. P4 impuesto en `execute()`. Filtro
  `status_date` (default `Project.pmo_status_date`). Requiere `bench migrate` (fixture `is_standard`).
- **Helpers `as-of`** en `pmo/actual.py` (`get_actual_hours_asof`, `get_actual_hours_by_task_asof`) — corte
  inclusivo hasta el fin del día de `status_date` (`date(from_time) <= status_date`), `docstatus = 1`, SQL
  estática parametrizada. Único código nuevo de cálculo.
- **Workspace público `PMO Control`** (module PMO, `is_standard`) — punto de acceso a los reportes de
  control con shortcuts a `PMO Planned vs Actual`, `PMO Status Report`, `PMO Baseline Comparison` y
  `PMO Change Register`. Solo navegación (sin Number Cards ni charts). `PMO Capacity` queda intacto
  (dedicado a capacidad). Requiere `bench migrate`.

### Notes
- Sin motor nuevo, DocTypes, Custom Fields ni cambios a Baseline (`snapshot_schema_version` sigue en 1).
- Fuera de alcance (ADR-0008): EVM, CPI/SPI, forecast (EAC/ETC), planned time-phased/BCWS, Baseline como
  fuente del plan, Number Cards/charts.

## [0.8.0] — 2026-09-09

Gobierno avanzado del cronograma, fase 1 — **fecha comprometida** (ADR-0007, Accepted): distingue la fecha
planeada/calculada (nativa) de la fecha comprometida (compromiso de negocio/acordado).

### Added
- **`Task.pmo_deadline`** (Date, Custom Field por fixture) — fecha comprometida/límite de la tarea.
- **`Project.pmo_committed_end_date`** (Date, Custom Field por fixture) — fecha comprometida de fin del
  proyecto, distinta de `expected_end_date` (calculada).
- **Validaciones suaves** (`pmo/schedule_commit.py`, `doc_events` `Task.validate` + `Project.validate`):
  avisan si el fin planeado supera el compromiso. **No bloquean** el guardado ni el Actual/Timesheet; campos
  vacíos = sin aviso. La fecha comprometida no se desplaza automáticamente (sí puede editarse).

### Notes
- Fuera de alcance (ADR-0007): constraints tipados (SNET/FNLT/MSO/MFO), auto-reprogramación, scheduler.
  `snapshot_schema_version` sigue en 1; Baseline y Status Date sin cambios; ADR-0004/0006 sin modificar.

## [0.7.0] — 2026-09-08

Control a fecha de corte / Status Date (ADR-0006, Accepted): responde "¿cómo estaba el proyecto a una fecha
respecto de lo planeado, la línea base aprobada y lo realmente ejecutado?".

### Added
- **Status Date (Data Date)** — Custom Field `Project.pmo_status_date` (Date, fixture; requiere `bench
  migrate`). Solo `<= today` (validación en `Project.validate`, ADR-0006 D2). Lo edita el owner (P4).
- **Motor** `pmo/status_date.py` — `build_status_report(project, status_date)` (whitelisted, P4) compone a
  la fecha de corte: **Baseline** vigente (`get_effective_baseline` as-of), **Current** (`build_snapshot`,
  plan de hoy) y **Actual** (Timesheet fechado, ADR-0003, + `completed_on` como proxy). Sin reconstrucción
  de % histórico.
- **Indicadores D5** — (1) deslizamiento de fecha final Baseline vs Current (días); (2) tareas que debían
  estar terminadas a la fecha y no lo estaban; (3) Actual hours acumuladas a la fecha; (4) conteos simples
  (previstas/completadas).
- **Reporte** `PMO Status Report` — Script Report **P4-safe** (por delegación en `build_status_report`);
  filtros `project` + `status_date` (default desde `pmo_status_date`, tope `today`); resumen = indicadores
  D5, detalle = tareas vencidas no terminadas.

### Notes
- Fuera de alcance (ADR-0006 D6): EVM/forecast, CPM (#9), reservas de capacidad (#10), comparación completa
  Planificado vs Real de horas, avance % histórico y fecha futura. ADR-0004/0005 sin cambios.

## [0.6.1] — 2026-09-08

### Fixed
- **CHANGELOG** — corrige la sección `[0.6.0]`, que había quedado como "En preparación / Release no
  publicado" con un apartado "Planned (aún no realizada)", cuando `v0.6.0` ya fue implementada y
  publicada (tag `v0.6.0` + GitHub Release). Sin cambios funcionales.

## [0.6.0] — 2026-09-08

Integrated Change Control (ADR-0005): gestión de cambios sobre el `Project` nativo de ERPNext, integrada
con el contrato publicado de `erpnext_proposals v0.22.0`.

### Added
- **DocType `PMO Change Request`** (submittable, `PMO-CR-.#####`) + **Workflow nativo**
  (Borrador → En Revisión → Aprobado/Rechazado → Implementado → Cerrado) que **gobierna** el cambio, con
  permisos **P4** (owner-only en las decisiones de aprobación; acceso ejecutivo read-only). Impacto
  estructurado mínimo (prioridad, checks scope/schedule/effort/commercial/risk, deltas horas/días/monto).
- **Integración con `erpnext_proposals v0.22.0`** por delegación (`pmo/change_control.py`, feature-detection
  vía `frappe.get_attr`): crear addenda comercial (`create_addendum_quotation`) y aplicar la addenda al
  **Project existente** (`apply_addendum_to_project`) — nunca crea otro Project. Acción `crear_addenda` +
  botón "Crear addenda comercial". `Ganada ≠ Aplicada`; aplicación explícita; `applied_*` solo tras éxito.
  Precondición: `erpnext_proposals >= 0.22.0`.
- **Comparador Baseline↔Baseline** — `pmo/compare.py` (`compare_snapshots` puro + `compare_baselines`
  whitelisted P4) y **Script Report `PMO Baseline Comparison`** (una fila por diferencia atómica).
- **Change Register** — Report Builder **P4-safe** (`permission_query_conditions`).
- **Gate de baseline vigente** al formalizar (`baseline_before` congelada); `baseline_before`/
  `baseline_after` del lado del CR (muchos CR → una misma `baseline_after`). **Aprobado ≠ Aplicado ≠
  Implementado**; persistencia post-submit vía `allow_on_submit` (sin bypass).

### Changed
- **Membresía de Project derivada nativa** (`owner + DocShare(Project) + ToDo`) — ADR-0002 revisado.
  DocShare honra sus flags read/write; el owner comparte su propio Project.

### Removed
- **`PMO Project Member`** y el Custom Field `Project-pmo_members` — retirados del código y de las fixtures
  **sin migration patch** (regla del proyecto). Instalación nueva limpia por construcción; los sitios de
  desarrollo existentes se limpian con una operación one-off manual (no distribuida).

### Docs
- **ADR-0005 — Integrated Change Control (Accepted)**; **ADR-0002** revisado; `docs/tecnico/arquitectura.md`
  y `docs/usuario/change-control.md`.

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
