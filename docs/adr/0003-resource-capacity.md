# ADR-0003: Resource Capacity and Planned Load

**Estado:** Propuesto (revisado 2026-09-03 — ver "Revisión")
**Fecha:** 2026-09-02 · **Revisión:** 2026-09-03
**App:** pmo · Depende de **ADR-0002** (privacidad Project/Task).

## Revisión (2026-09-03)

La versión inicial modelaba un DocType de captura `PMO Resource Allocation` (+ child `PMO Allocation
Day`) donde el usuario **volvía a declarar** employee/project/task/horas/fechas que ya existen en
`Task` + Assignment. Se descartó por **duplicación de captura** y riesgo de inconsistencia: ERPNext ya
tiene el flujo natural `Project → Task (WBS) → Assignment (ToDo) → persona`. Capacity Planning pasa a ser
**derivación/reporte** sobre Task + Assignment, no un segundo sistema de asignaciones. El único dato que
el nativo no tiene —**horas por asignado cuando una Task tiene varios**— se resuelve con reparto uniforme
por defecto + un Custom Field **opcional** en el Assignment (`ToDo.pmo_planned_hours`).

## Contexto

Cliente pide capacity planning (disponibilidad, carga, sobreasignación, utilización). En v16:
`Task` tiene `project`, `expected_time` (esfuerzo planificado), `actual_time` (derivado de Timesheet),
`exp_start_date`/`exp_end_date` y **WBS nativo** (nested set). El Assignment nativo (`ToDo`,
`allocated_to`=User, `status`) dice **quién** tiene la Task; admite varios asignados. `Timesheet Detail`
da el tiempo real. **No existe** en el nativo: capacidad diaria por persona, ni **horas por asignado**
cuando una Task tiene varios.

## Problema

Responder capacidad/carga/utilización **derivando** de Task + Assignment (sin segunda captura), sin hacer
HRMS obligatorio, respetando la privacidad (ADR-0002/P4), y sin perder silenciosamente parte del
`expected_time`.

## Modelo conceptual (4 conceptos separados, no mezclar)

```
Capacity     = cuánto podría trabajar el recurso (efectivo-datada: global u override)   [PERSISTIDO]
Availability = Capacity − no-laborables (Holiday List) − ausencias aprobadas (Leave si HRMS)  [DERIVADO/día]
PlannedLoad  = esfuerzo planificado por persona, DERIVADO de Task.expected_time + Assignment  [DERIVADO/día]
Actual       = tiempo real trabajado (Timesheet)                                        [DERIVADO, estado vigente]
Libre = Availability − PlannedLoad ; Utilización = PlannedLoad/Availability y Actual/Availability (separadas)
```

- **Availability, PlannedLoad y Actual son derivados** y reflejan el **estado vigente** de sus fuentes
  (Capacity, Holiday List, Leave, Task, Assignment, Timesheet). **No** se persisten ni se congelan.

## Reproducibilidad (MVP: plan vigente, sin congelamiento)

- **Capacity histórico:** sí, por **vigencias** (`PMO Capacity` efectivo-datado).
- **PlannedLoad / Availability / Actual:** **NO** se congelan. Si cambian `Task.expected_time`, fechas,
  asignados, Holiday List, Leave o Timesheet, el plan se **recalcula**. Es comportamiento esperado del MVP.
  **Snapshots/baselines** (plan histórico congelado) quedan para una fase posterior si hay necesidad real.

## Modelo de datos

### `PMO Capacity` — capacidad efectivo-datada (un solo modelo: global + override) — SIN CAMBIOS
- `employee` (Link Employee, **opcional**): vacío = **baseline global**; con valor = **override por persona**.
- `from_date` (Date, req); `capacity_hours_per_day` (Float, req).
- Resolución `capacity(employee, date)` = fila del employee con `from_date ≤ date` más reciente; si no,
  fila global. **Sin default global mutable, sin 8h implícitas** (ausencia → None). Unicidad scope+from_date
  (vacío/NULL = scope GLOBAL único).

### Custom Field `ToDo.pmo_planned_hours` (Float, **opcional**) — dato faltante, sobre el Assignment nativo
- Horas planificadas de **ese asignado** en **esa Task**. Vive en el registro de asignación nativo (ToDo),
  **no** en un DocType paralelo. Vacío = participa del reparto uniforme.

### Nativo reutilizado (fuente de verdad, no se persiste en pmo)
`Task` (project, `expected_time`, `exp_start_date`/`exp_end_date`, WBS), Assignment `ToDo` (persona
activa = `status="Open"`), Holiday List, Timesheet (Actual), Employee (`user_id` para el bridge), y Leave
Application **solo si HRMS**.

## Decisiones

### D1 — Capacidad
Un solo DocType `PMO Capacity` efectivo-datado (global + override); resolución más-específico-luego-global
por `from_date`. Sin default mutable ni 8h implícitas.

### D2 — Carga planificada DERIVADA de Task + Assignment (no DocType paralelo)
La fuente de "quién tiene qué trabajo" es **Task** (`expected_time`, fechas, project) + **Assignment**
(`ToDo` activo por persona). **No** se crea un DocType de asignación en `pmo`; **no** hay segunda captura.
Capacity Planning **deriva** la carga. Asignado activo = `ToDo.status="Open"`, `reference_type="Task"`.
**Bridge** Assignment(User) ↔ Capacity(Employee) por `Employee.user_id`; asignaciones sin Employee
vinculado se reportan como "sin capacidad asociada" (no se inventan).

### D3 — Horas por asignado (resolución determinista del hueco real)
Para una Task con asignados activos y `expected_time = E`:
- **1 asignado** → `E`.
- **N sin overrides** → `E / N` (uniforme).
- **N con algunos overrides** → respetar `pmo_planned_hours` explícitos; repartir el **remanente**
  `E − Σ(overrides)` uniformemente entre los que **no** tienen override.
- **`Σ(overrides) > E`** → **inconsistencia** (sobreasignación del esfuerzo; se reporta, no se calcula).
- **Todos con override** → `Σ(overrides)` debe ser **exactamente** `E`: menor → inconsistencia (esfuerzo
  no distribuido); mayor → inconsistencia (sobreasignado). **No** se pierde parte de `expected_time` en
  silencio.

### D4 — Granularidad diaria derivada (reutiliza lógica pura; plan vigente)
Día canónico. Las horas de cada asignado se distribuyen sobre `Task.exp_start_date..exp_end_date` con la
función pura `build_allocation_days` (reparto uniforme sobre días laborables según Holiday List). Semana/
mes = agregación. **Sin ciclo Draft/Submit/Amend ni congelamiento**: el plan es siempre vigente (se
recalcula). Task sin fechas → "carga sin fechas" (no se inventa el rango).

### D5 — HRMS opcional
Mínimo = ERPNext (Employee, Holiday List, Timesheet). `pmo` **no** declara `hrms` en `required_apps`; si
está instalado, Availability descuenta Leave aprobada (detección en runtime).

### D6 — Privacidad (P4) a nivel de reporte
La visibilidad de Task se rige por **ADR-0002/P0**. Los **reportes** de Capacity Planning aplican el
enmascarado P4: agregación server-side; identidad de Project/Task **enmascarada** por boundary del
observador; **bucket único "Comprometido (confidencial)"**; mismo enmascarado en Actual dentro de los
reportes PMO; `PMO Executive Access` ve desglose completo; usuario normal ve lo suyo + proyectos
permitidos. `PMO Capacity` no referencia Project → permisos estándar (config PMO).

## Consecuencias

- Nuevos objetos mínimos en `pmo`: **`PMO Capacity`** (persistido) + **un Custom Field opcional en ToDo**.
  Todo lo demás (Availability, PlannedLoad, Actual, reportes) es **derivado**.
- Task + Assignment = **única** fuente de asignación; sin duplicación ni segunda pantalla de captura.
- Reproducibilidad **parcial**: solo Capacity es histórico; el resto se recalcula (plan vigente).
- Separación estricta: PlannedLoad (planificado) y Actual (real) nunca se suman.

## Riesgos

- Cambios retroactivos en Task/Assignment/Holiday List/Leave/Timesheet alteran los cálculos (esperado; sin
  snapshots en MVP).
- Asignaciones sin `Employee.user_id` mapeado → quedan fuera del cálculo (se reportan explícitamente).
- Inconsistencias de horas por asignado (D3) → se **reportan** como error, no se calcula carga inválida.
- `pmo_planned_hours` no se captura en el diálogo rápido "Assign To" (hardcodeado); el override se edita en
  el formulario del ToDo. El camino común (reparto uniforme) no requiere captura.
- Reparto uniforme puede no reflejar jornadas irregulares → override por asignado; calendarios finos fuera de MVP.

## Alternativas descartadas

- **`PMO Resource Allocation` + `PMO Allocation Day` (DocType de captura paralelo):** duplica Task +
  Assignment (employee/project/task/horas/fechas ya existen); doble verdad, UX peor que ERPNext. **Descartado.**
- Child de esfuerzo por asignado **en la Task**: re-lista los asignados (`_assign`) → duplicación. Descartado
  a favor de un Custom Field en el ToDo (el objeto de asignación).
- `default_capacity_hours_per_day` global mutable; HRMS como dependencia dura; `expected_time`/`_assign` como
  capacidad; persistir el plan y congelarlo en el MVP (snapshots → fase posterior).

## Impacto en nativo / hooks

- **Nativo:** sin cambios de core; se **lee** Task, ToDo, Employee, Holiday List, Timesheet (y Leave si HRMS);
  se **añade** un Custom Field a `ToDo` (fixture).
- **Nuevos (pmo):** `PMO Capacity`; funciones derivadas server-side (Availability, Actual, PlannedLoad) y el
  reporte de capacidad con enmascarado P4. Sin `pqc`/`has_permission` propios de un DocType de asignación
  (ya no existe).

## Estrategia de pruebas (datos ficticios)

- Capacidad: override 8h→4h a mitad de año → periodos previos conservan 8h; global aplica a quien no tiene override.
- Horas por asignado (D3): 1 asignado, N uniforme, overrides parciales con remanente, `Σ>E` error,
  todos-override `Σ≠E` error.
- Distribución diaria: reparto uniforme respeta Holiday List; Task sin fechas → carga sin fechas.
- Availability/Actual: cambiar Holiday List/Timesheet retroactivamente **sí** cambia el recálculo (esperado).
- Separación: PlannedLoad y Actual nunca sumados.
- Privacidad P4 (reporte): sin acceso a un Project → "confidencial" agregado, sin identidad; miembro →
  desglose; Executive → todo; usuario normal → lo suyo.
- Sin HRMS: no falla; con HRMS: Leave aprobada reduce Availability.

## Criterios de aceptación

- Capacity/Availability/PlannedLoad/Actual separados y verificables, **derivados de Task + Assignment** (salvo Capacity, persistida).
- Ninguna segunda captura de asignaciones; Task + Assignment como única fuente.
- Horas por asignado nunca pierden parte de `expected_time` en silencio (D3).
- ERPNext suficiente; HRMS solo enriquece. Ningún cálculo asume 8h fijas ni ignora festivos/ausencias.
- Reportes de capacidad respetan ADR-0002/P4 sin fugas de identidad.
