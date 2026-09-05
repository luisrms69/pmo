# ADR-0004: Schedule Governance & Baselines

**Estado:** Proposed
**Fecha:** 2026-09-05 · **App:** `pmo` · **Objetivo de versión:** v0.5.0
**Depende de:** ADR-0002 (Privacidad Project/Task, P4), ADR-0003 (Resource Capacity). **No reabre** ninguno.

## Contexto

ERPNext v16 modela solo el **plan vigente** (`Task.exp_start_date`/`exp_end_date`, `expected_time`) y el
**real** (`Task.act_*` derivado de Timesheet). **No existe baseline, ni constraint tipado, ni critical
path/float nativos** (verificado: sin `baseline`/`critical_path`/`float` en `erpnext/projects/doctype`).

El controlador `Task` (`task.py:84-137`) impone dos reglas de fecha que tratan el WBS y el plan como
restricciones duras:

- `validate_parent_expected_end_date` (`:105-119`): `child.exp_end_date <= parent.exp_end_date`.
- `validate_parent_project_dates` (`:121-137`): `exp_start_date`/`exp_end_date`/`act_start_date`/
  `act_end_date` `<= Project.expected_end_date`.

**Drift local vs upstream.** El bench (ERPNext 16.32.1, `HEAD 21d1873`) valida solo contra
`expected_end_date` (cota superior). El commit upstream **`7b0df4b` (14-ago-2026)** amplia la regla a
`expected_start_date` + `expected_end_date` (cotas inferior y superior sobre los cuatro campos). Ese
commit **no esta** en el bench local; el diseno debe ser correcto para el upstream.

**Impacto funcional confirmado.** El flujo de Timesheet (`timesheet.py:169-183`) hace `Task.save()` tras
fijar `act_*` desde el parte de horas (`task.py:224-243`); `validate_parent_project_dates` **bloquea
registrar realidad** mas alla del fin planificado (`InvalidDates`). Ademas `validate_parent_project_dates`
hace `return if frappe.in_test` (`:122`), por lo que un test ordinario no ejerce la ruta de produccion.

## Problema

Aportar gobierno de cronograma sobre ERPNext, sin fork ni convertirlo en Primavera: (a) que el WBS y el
plan de alto nivel **no bloqueen** el forecast ni el registro del Actual; (b) disponer de una **baseline
aprobada, fija y trazable** contra la cual medir; preservando P4 (ADR-0002) y sin tocar el motor de
Capacity (ADR-0003).

## Modelo conceptual (cuatro planos; no mezclar)

- **Baseline** — plan formalmente aprobado y congelado (referencia de medicion).
- **Current Plan / Forecast** — plan vigente y mutable (`Task.exp_*`).
- **Actual** — lo realmente ocurrido (Timesheet -> `Task.act_*`; motor ADR-0003).
- **Constraint / Deadline** — obligacion explicita, **separada** del WBS y del forecast (objeto
  **diferido**; ver gaps).

El WBS (`Task.is_group=1`) **no** se convierte automaticamente en constraint.

## Decisiones

### D1 — Semantica de Task group / WBS (summary, no constraint)

`Task.is_group=1` representa fase / summary / nodo WBS. Sus fechas son **summary dates no vinculantes**:
**no** bloquean a las hijas y **pueden quedar desactualizadas** respecto del min inicio / max fin de las
hijas en v0.5.0 (no hay rollup dinamico). El **envelope automatico permanente** es capacidad **futura**
(gap). El preflight (D6) **avisa** cuando las summary dates difieren del envelope de las hijas. No
afirmamos tener rollup vivo. Se descarta implementar rollup solo por pureza metodologica (scope creep;
interaccion con `reschedule_dependent_tasks`; `erpnext_proposals` ya hace rollup inicial).

### D2 — `Project.expected_start_date`/`expected_end_date` = plan/forecast

Se tratan como fechas de plan de alto nivel; **no** como restriccion dura por Task ni como tope del Actual.

### D3 — Intervencion sobre ERPNext (minima invasion, upgrade-safe)

`extend_doctype_class = {"Task": "pmo.overrides.task.PMOTaskScheduleMixin"}` (mixin por MRO). El mixin
**redefine unicamente** `validate_parent_expected_end_date` y `validate_parent_project_dates`, con nuestra
semantica (no bloquear; `Project.expected_*`/`parent.exp_end_date` = forecast/envelope; **el Actual nunca
se bloquea**). **No** reimplementa `validate_dates()`.

- **Por que:** `validate_dates()` llama a los submetodos via `self.<m>()` (`task.py:98-99`); el override
  por MRO aplica manteniendo `validate_dates()` **nativo** (hereda validaciones que upstream agregue). No
  copiamos el cuerpo upstream -> **independiente de version**, reconcilia el drift `7b0df4b`.
- **Guard de drift:** test que verifica que el `Task` nativo sigue definiendo ambos submetodos; si
  upstream los renombra/inlinea, falla y se re-evalua.
- **Descartados:** modificar core/fork; monkey-patch; `override_doctype_class` (reemplazo total
  innecesario, monopoliza Task); `doc_events` (no puede suprimir una validacion nativa); reimplementar
  `validate_dates()` (duplicaria logica y sombrearia cambios upstream).
- Convencion de la casa: `erpnext_proposals` ya usa `extend_doctype_class` para `Quotation`.

### D4 — DocType `PMO Project Baseline` (submittable): lineage, vigencia, aprobacion y permisos

Un unico DocType submittable. **Es una Schedule / Operational Planning Baseline** (no una PMI Scope
Baseline completa; ver D5 y gaps).

- **Lineage / configuration control:** `baseline_type` (Select: *Original / Approved Change / Replan*) +
  `supersedes_baseline` (Link `PMO Project Baseline`). Invariantes: *Original* -> `supersedes_baseline`
  vacio; toda posterior -> sustituye la **cabeza vigente** de la cadena del **mismo Project**, que debe
  estar **Submitted** y **no Cancelled**; no self-supersede; **sin ciclos**; **cadena lineal** (sin
  bifurcaciones); **max. una `Original` valida por Project**. **Sin `is_current`** (se deriva).
  `revision` (Data) = **etiqueta humana unica por Project** (p. ej. `BL-001`); la identidad interna la da
  el `name` (naming series, p. ej. `PMO-BL-.#####`); sin campo de secuencia numerica extra.
- **Vigencia (Opcion B — sin future-effective en v0.5.0):** `effective_date <= approved_at`. Baseline
  **vigente = cabeza de la cadena** (ultima Submitted/no-Cancelled del Project); la consulta historica
  "efectiva as-of una fecha" se resuelve por `effective_date` + lineage, sin sucesores pendientes.
  Programacion de baselines a futuro = **gap diferido**.
- **Aprobacion (cuatro campos distintos):** `approved_by = frappe.session.user` y `approved_at = now()`
  **fijados en Submit** (no editables); `effective_date` (Date, `<= approved_at`); `snapshot_at`
  (Datetime, captura tecnica, read-only). **Se elimina `submitted_by`** (redundante; `docstatus` es la
  evidencia tecnica). El **Submit es el acto formal de aprobacion** dentro de PMO.
- **Permisos (coherentes con ADR-0002, sin alterarlo):**
  - **Read**: refleja `is_project_visible` del Project de la baseline (owner / PMO Project Member /
    **PMO Executive Access** global / Administrator), via `has_permission` que reusa
    `permissions.is_project_visible`.
  - **Crear/editar Draft**: **Project Owner**.
  - **Submit (aprobar/congelar) y Cancel**: **Project Owner**.
  - **PMO Executive Access**: **read-only** (sin submit/cancel) — no se altera ADR-0002.
  - **PMO Manager**: **sin cambios** (sin acceso a contenido por rol); **no** es aprobador (no puede ver
    el snapshot sin romper P4).
  - **Separacion de funciones (proponente != aprobador) / Sponsor / CCB / Workflow -> v0.6.0**, con
    visibilidad+autoridad otorgadas explicitamente.
- Otros campos: `project` (Link), `reason`. **Sin `change_request`** en v0.5.0 (el Link se anade en
  v0.6.0).

### D5 — Snapshot canonico + ciclo de captura

- **Snapshot JSON canonico obligatorio**, inmutable tras Submit; `snapshot_schema_version` (=1) y
  `snapshot_hash` **determinista** (claves ordenadas, fechas ISO, listas ordenadas por `name`).
- **WBS por identidad estable:** `task_id` + `parent_task` + `wbs_order` (ordinal por grupo de hermanos
  derivado del orden nativo al congelar). **`lft`/`rgt` NO** son identidad semantica (solo metadata
  opcional).
- **Por Task:** `name`, `subject`, `description` (contenido de alcance operacional), `parent_task`,
  `wbs_order`, `is_group`, `is_milestone`, `exp_start_date`, `exp_end_date`, `expected_time`, `duration`
  (opcional), `status`, `depends_on: [task_id]`, `assignments`.
- **Assignments (resource plan congelado):** `[{ user, employee, override_hours, effective_hours }]`;
  `override_hours` = `ToDo.pmo_planned_hours` (o null); `effective_hours` = regla PMO
  `get_planned_hours_per_assignee` **al congelar**. Si el `User` no resuelve a `Employee`:
  `employee = null`, se conserva `user`, y se emite **warning de preflight**.
- **Sin Actual** en la baseline. **Evidencia legible:** Data Export nativo **opcional/manual** por
  Attachments; v0.5.0 **no** construye pipeline de exportacion automatica.
- **Ciclo de captura (Frappe):** el snapshot autoritativo se construye en **`before_submit`** (secuencia
  nativa `validate -> before_submit -> on_submit`): preflight definitivo -> construir snapshot ->
  `snapshot_hash` -> `snapshot_at` -> `approved_by`/`approved_at`. Cualquier accion
  **"Congelar/Previsualizar"** en Draft es **previsualizacion efimera no autoritativa**: la unica version
  canonica es la de `before_submit` (lo aprobado == lo capturado).

### D6 — Preflight ligero (mayormente warning)

Al congelar, reutilizando senales existentes (`planned_load` `issues`/`unscheduled`/`unmapped`, etc.):

- **Warnings (no bloqueantes):** leaf Task sin fechas; `is_group=1` con `expected_time>0`; `is_group=1`
  con asignaciones; **summary dates desactualizadas vs envelope de hijas**; Assignment sin `Employee`;
  inconsistencias conocidas de Planned Load. Un **grupo sin fechas NO** es error automatico.
- **Bloquea solo** si no puede producirse un snapshot coherente (p. ej. reparto de horas
  **matematicamente inconsistente** que impida determinar `effective_hours`).
- **No** se construye validador schedule-health/DCMA.

### D7 — P4 del Baseline (ADR-0002)

El snapshot contiene identidad de Project/Task. La **lectura** del `PMO Project Baseline` refleja la
visibilidad del Project (owner / member / `PMO Executive Access` / Administrator) reutilizando
`is_project_visible`; no world-readable. No se filtra identidad a quien no puede ver el Project.

### D8 — Capacity Planning sin cambios

No se toca `planned_load.py`. Las fases (`is_group=1, expected_time=0`, sin ToDo) no aportan carga (motor
*assignment-first*). El guard `is_group=0` solo se revisitara ante un caso real.

### D9 — Frontera con Change Control / `erpnext_proposals` (no decidida aqui)

Inclinacion de roadmap (v0.6.0): `Project -> Change Request -> Proposal/Quotation addendum -> aprobacion
-> adendar contenido al Project -> actualizar Current Plan -> nueva Baseline`. ADR-0004 **solo** establece
que el modelo de Baseline/Schedule **no cierra** ese camino (por eso existen `baseline_type=Approved
Change` y `supersedes_baseline`; el Link a Change Request se anade en v0.6.0). La arquitectura de Change
Control se decide y documenta por separado (posible **ADR-0005**). No se implementa nada de
`erpnext_proposals` en v0.5.0.

## Invariantes de configuration control

1. Maximo una `Original` valida por Project (Submitted, no Cancelled).
2. `revision` unica por Project.
3. Cadena de supersession **lineal**: una nueva baseline sustituye la **cabeza vigente**.
4. `supersedes_baseline`: mismo Project, Submitted, no Cancelled, no self, sin ciclos.
5. `effective_date <= approved_at` (sin future-effective en v0.5.0).

## Contraste con estandares y gaps deliberados

Referencias: PMI *Practice Standard for Scheduling* / PMBOK (baseline como referencia aprobada y control
formal de cambios); APM (*Change Control* sobre baseline aprobada; baseline como referencia de
monitoreo/control); ISO 21502 (guia **adaptable/proporcional**). Clasificacion: **Covered / Partially
Covered / Deferred — Cost/Benefit / Not Applicable**.

| Practica | Clasificacion | Relevancia | Costo | Beneficio | Nota |
|---|---|---|---|---|---|
| Baseline aprobada, fija y trazable | **Covered** | Alta | Bajo | Alto | D4 (lineage + aprobacion en Submit) |
| Control formal de cambios de baseline | **Partially Covered** | Alta | — | — | Lineage si; CCB/Workflow -> v0.6.0 |
| Separacion de funciones (proponente!=aprobador) | **Deferred** | Media | Medio | Medio | v0.6.0 (owner aprueba en v0.5.0) |
| Congelado de plan de cronograma/recursos | **Covered** | Alta | Bajo | Alto | D5 (snapshot + `effective_hours`) |
| Deteccion de variacion de alcance operacional | **Covered** | Media | Bajo | Alto | D5 (`description` + estructura) |
| PMI Scope Baseline completa (scope statement, WBS dictionary, deliverables, acceptance criteria, SOW) | **Deferred — Cost/Benefit** | Media | Alto | Medio | v0.6.0 + `erpnext_proposals`; **no** afirmada |
| Revision previa a baselinar (schedule usable) | **Covered (ligero)** | Media | Bajo | Medio | D6 preflight, no DCMA |
| Rollup/envelope dinamico de summary | **Deferred** | Media | Medio | Medio | D1 (warning, no rollup) |
| Baselines programadas a futuro (future-effective) | **Deferred** | Baja-Media | Medio | Bajo | Opcion B (invariante 5) |
| Status/Data Date formal | **Deferred** | Media | Bajo-Medio | Medio | Roadmap **v0.7** (Planificado vs Real) |
| Constraints tipados (SNET/FNLT/MSO...) | **Deferred** | Media | Medio | Medio | Evaluar en **v0.6** (sin compromiso) |
| Critical path / float (CPM) | **Deferred — Cost/Benefit** | Media | Alto | Medio | Futuro |
| Leads/lags en dependencias | **Deferred — Cost/Benefit** | Media | Medio | Bajo-Medio | `depends_on` nativo sin lag |
| Calendarios avanzados por recurso | **Deferred — Cost/Benefit** | Media | Medio-Alto | Bajo-Medio | Holiday List basta hoy |
| Resource leveling automatico | **Not Applicable (ahora)** | Baja-Media | Alto | Bajo | Damos visibilidad de sobreasignacion, no leveling |
| Schedule risk analysis (Monte Carlo) | **Not Applicable** | Baja | Alto | Bajo | Fuera de alcance |
| GAO/DCMA schedule quality completo | **Not Applicable (ahora)** | Baja-Media | Alto | Bajo | Preflight ligero es el minimo |
| Cost Baseline / EVM / PMB | **Deferred (lejano)** | Media | Alto | Medio | Futuro independiente, solo si aporta valor |

## Consecuencias

- Se desbloquea el registro de Actual fuera del plan y el forecast por encima del envelope, sin fork y sin
  alterar otras validaciones nativas.
- Aparece una baseline aprobada, trazable (lineage lineal) y comparable en el futuro (issue #5),
  respetando P4.
- Objetos nuevos: DocType `PMO Project Baseline` + mixin `Task`. Sin cambios en Capacity, Project ni
  `erpnext_proposals`.

## Riesgos

- Dependencia de los nombres de los submetodos nativos de Task (mitigado por guard de drift, D3).
- `frappe.in_test` en `validate_parent_project_dates` exige tests que fuercen la ruta de produccion
  (`frappe.flags.in_test=False` en `try/finally`) y/o llamada directa al metodo nativo/override.
- Snapshot de `description` (HTML) puede crecer; hash determinista + normalizacion mitigan.
- Owner-como-aprobador reduce la separacion de funciones; aceptado para v0.5.0 y evolucionable en v0.6.0.

## Alternativas descartadas

Override total de `validate_dates`; `override_doctype_class`; `doc_events`; fork/monkey-patch; exportador
CSV/XLSX propio como fuente canonica; `is_current` persistido; `submitted_by` separado de `approved_by`;
`PMO Executive Access` o `PMO Manager` como aprobador (romperia P4/ADR-0002); Amend para nuevas baselines
(cada baseline es documento nuevo; Cancel solo para anular una erronea); future-effective baselines en
v0.5.0; rollup dinamico en v0.5.0.

## Criterios de aceptacion

- `Task.save()` y submit de Timesheet **no** bloquean por `Project.expected_end_date`/`parent.exp_end_date`;
  el resto del comportamiento nativo queda intacto; guard de drift presente.
- `PMO Project Baseline` submittable con invariantes de lineage (seccion Invariantes), `approved_by`/
  `approved_at` fijados en `before_submit`, snapshot canonico (`snapshot_schema_version` + `snapshot_hash`)
  con `description` y assignments `{user, employee, override_hours, effective_hours}`.
- Baseline vigente = cabeza de la cadena; consulta "efectiva as-of" por `effective_date` + lineage.
- Read del Baseline respeta P4 (`is_project_visible`); Submit/Cancel restringidos a Project Owner;
  Executive read-only; Manager sin cambios.
- Preflight emite warnings y solo bloquea ante snapshot incoherente.
- Tests con datos ficticios que sortean `frappe.in_test`.
