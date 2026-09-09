# ADR-0006: Control a fecha de corte / Status Date

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted · **Ciclo:** v0.7.0

## Aceptación (2026-09-08)

Implementado en v0.7.0 sin desviaciones respecto de D1–D8. Custom Field `Project.pmo_status_date` (fixture)
+ validación `<= today` (D1/D2); motor `pmo/status_date.py` (`build_status_report`, P4) que compone Baseline
as-of (`get_effective_baseline`, D3), Current (`build_snapshot`, D4) y Actual (Timesheet fechado + proxy
`completed_on`, D4) y los indicadores D5; reporte P4-safe `PMO Status Report` (D7). Sin DocType nuevo, sin
data/migration patch, ADR-0003/0004/0005 sin cambios (D8). Validado end-to-end en `proposals-acti.dev`
(Project + Tasks + Baseline Submitted + Timesheet Submitted): D5.1 = 11 días, D5.2 = 1 vencida, D5.3 = 12 h,
D5.4 = 1/2; Status Date futura → error; caso sin baseline → `note`; P4 outsider → `PermissionError`.

## Contexto

pmo ya gobierna el cronograma sobre `Project`/`Task` nativos (ADR-0004), congela planes aprobados en
`PMO Project Baseline` (snapshot inmutable, lineage con `effective_date` monótona, selección as-of vía
`get_effective_baseline(project, as_of)`), deriva el **Actual** de `Timesheet` (ADR-0003) e integra
control de cambios (ADR-0005). ADR-0004 dejó **Status/Data Date formal** explícitamente **diferido a v0.7**
("Planificado vs Real").

## Problema

No se puede responder de forma formal: **"¿Cómo estaba este proyecto a una fecha determinada respecto de lo
planeado, la línea base aprobada y lo realmente ejecutado?"** Falta (a) una **fecha de corte** (Data Date)
por proyecto, (b) la composición Baseline/Current/Actual a esa fecha y (c) indicadores simples de desviación.

## Modelo conceptual (tres planos a la fecha de corte)

- **Baseline** — el plan **aprobado** vigente a la Status Date: el snapshot inmutable de la baseline cuya
  `effective_date <= status_date` (cabeza de cadena; ADR-0004 Opción B).
- **Current** — el **plan vigente HOY** (`build_snapshot(project)` actual), **evaluado frente a** la Status
  Date. **No** reconstruye el plan que existía en esa fecha (Task no guarda historia); es el plan tal como
  está hoy, contrastado contra el corte.
- **Actual** — lo **realmente ejecutado hasta** la Status Date: horas de `Timesheet` fechadas
  (`date(from_time) <= status_date`, docstatus=1) como **fuente fiable**; y `Task.completed_on <= status_date`
  como **proxy** de tareas completadas/vencidas.

## Decisiones

### D1 — Status Date persistente en `Project`
Custom Field **`Project.pmo_status_date`** (Date), declarado por **fixture** (mismo patrón que
`ToDo-pmo_planned_hours`). Es la **Data Date vigente** del proyecto (un solo valor). **Sin DocType ni
historial** de fechas de corte (evita un modelo paralelo). El análisis a fechas anteriores se obtiene
eligiendo cualquier fecha en el reporte; el reporte usa `pmo_status_date` como valor por defecto.

> **Nota de despliegue:** es un Custom Field **por fixture** — **no** hay data patch ni migration patch,
> pero **sí** implica el **cambio de metadata normal** que sincroniza `bench migrate` (creación del campo en
> la DB al aplicar la fixture). No es "sin sincronización de DB": requiere `bench migrate` una vez.

### D2 — Rango temporal soportado en v0.7.0: `status_date <= today`
La Status Date **solo** puede ser hoy o pasada. **No** se soporta fecha futura en este ciclo (el Actual solo
existe hasta hoy; una fecha futura mezclaría planos). Se **valida** la entrada (validación del campo en
`Project` y del parámetro del reporte/motor) y se **rechaza** una Status Date futura con mensaje claro.

### D3 — Selección de la baseline válida a la fecha
Se reutiliza `get_effective_baseline(project, as_of=status_date)` (ADR-0004): baseline con mayor
`effective_date <= status_date`, Submitted, no cancelada. Si **no hay** baseline efectiva a la fecha → el
plano **Baseline se omite** y el reporte lo marca ("sin línea base vigente a la fecha"), mostrando Current +
Actual.

### D4 — Definición de Actual (fiable + proxy), sin reconstrucción histórica
- **Esfuerzo real a la fecha:** Σ `Timesheet Detail.hours` con `date(from_time) <= status_date`, docstatus=1
  (semántica oficial de ADR-0003), a nivel Project/Task.
- **Completadas/vencidas:** `Task.completed_on <= status_date` (proxy). Una tarea sin `completed_on` o con
  `completed_on > status_date` se considera **no** completada a la fecha.
- **NO** se reconstruye el **% de avance histórico** (Task no almacena historia): queda fuera por decisión
  explícita.

### D5 — Indicadores mínimos de v0.7.0
1. **Deslizamiento de fecha final Baseline vs Current (días):** `Project.expected_end_date` de la baseline
   vigente vs el Current (deriva de `compare_snapshots`).
2. **Tareas que debían estar terminadas a la Status Date y no lo estaban:** tareas con
   `baseline.exp_end_date <= status_date` **no** completadas (`completed_on` nulo o `> status_date`).
3. **Actual hours acumuladas hasta la Status Date** (Timesheet, D4).
4. **Conteos simples** de tareas previstas/completadas **cuando sean reconstruibles con datos fiables**
   (p. ej. nº de tareas con baseline due `<= status_date`, nº completadas por `completed_on <= status_date`).

### D6 — Fuera de alcance (deliberado)
- **EVM** (SPI/CPI/EAC/ETC) y cualquier **forecast**.
- **CPM / ruta crítica** (issue #9). **Reservas de capacidad** (issue #10).
- **Comparación completa "horas planeadas a la fecha vs horas reales a la fecha"** → se difiere al ciclo
  posterior *Planificado vs Real*. En v0.7.0 **no** se implementa esa métrica **ni** una regla todo-o-nada
  de horas planeadas.
- Fecha futura (D2). Cleanup de `pmo-v16.dev`.

### D7 — Permisos (P4)
El reporte de Status Date es **P4-safe** (mismo patrón que `PMO Baseline Comparison`: Script Report que
impone P4 por delegación, o Report Builder con `permission_query_conditions`): solo proyectos visibles para
el usuario (owner / DocShare / PMO Executive Access read-only). El campo `pmo_status_date` **hereda** el
`write` P4 del Project (lo edita el owner; no es acción especial).

### D8 — Reutilización, sin modelo paralelo ni patches
Se reutilizan `Project`, `Task`, `Timesheet` y `PMO Project Baseline` + los motores existentes
(`get_effective_baseline`, `build_snapshot`, `compare_snapshots`, `pmo/actual.py`). **Sin DocType nuevo, sin
data/migration patch** (regla del proyecto); el único cambio de esquema es el Custom Field por fixture (D1).
**ADR-0003/0004/0005 no se modifican**; ADR-0006 únicamente **referencia** ADR-0004 (que ya anticipó v0.7).

## Consecuencias

- Se responde la pregunta de control a fecha de corte con piezas nativas y una sola fecha persistente por
  Project.
- **Current ≠ plan histórico:** el reporte deja explícito que Current es el plan de hoy evaluado contra el
  corte, no una reconstrucción de la fecha.
- El Actual es fiable en esfuerzo (Timesheet fechado) y aproximado en completitud (`completed_on`); no hay %
  histórico.
- `bench migrate` requerido **una vez** por el Custom Field (sync de fixtures) — se ejecutará con
  autorización explícita cuando corresponda.

## Riesgos

- **Historia de Task ausente:** mitigado acotando Actual a datos fechados/fiables y declarando la limitación;
  sin reconstrucción de %.
- **`completed_on` como proxy:** una tarea reabierta o completada sin fecha puede sesgar los conteos; se
  documenta como aproximación, no como verdad contable.
- **Timesheets retroactivos:** el Actual a una fecha pasada puede cambiar si se registran Timesheets con
  fecha anterior después del corte (comportamiento aceptado: el corte es por `from_time`, no por fecha de
  captura).

## Alternativas descartadas

- **DocType con historial de Status Dates** (period-end): modelo paralelo, fuera de alcance.
- **Reconstrucción de % de avance histórico**: no soportable con el modelo nativo (Task sin historia).
- **Regla todo-o-nada de "horas planeadas a la fecha" + comparación Planned vs Actual de esfuerzo**: se
  difiere al ciclo *Planificado vs Real*.
- **Fecha de corte futura / forecast / EVM / CPM**: fuera de alcance de v0.7.0.

## Criterios de aceptación

- Existe `Project.pmo_status_date` (fixture) y el reporte lo toma por defecto, permitiendo override
  `<= today`.
- Status Date futura se rechaza con mensaje claro.
- El reporte P4-safe muestra los tres planos a la fecha (o Current+Actual si no hay baseline) y los
  indicadores D5.
- Baseline vigente a la fecha = `get_effective_baseline(project, status_date)`.
- Sin DocType nuevo, sin data/migration patch, sin cambios en ADR-0003/0004/0005; el único cambio de esquema
  es el Custom Field `pmo_status_date` por fixture.
