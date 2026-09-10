# ADR-0008: Planificado vs Real — reporte de esfuerzo visible desde PMO

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Ciclo:** v0.9.0

## Contexto

Los datos para comparar esfuerzo planificado vs real ya existen de forma **nativa** (`Task.expected_time`,
`Task.actual_time`, `Timesheet Detail.hours`); ERPNext v16 **no** trae un reporte estándar que los ponga
lado a lado por Project/Task. Además, varios reportes de control PMO (`PMO Status Report`,
`PMO Baseline Comparison`, `PMO Change Register`) hoy **no** están en ningún Workspace —viven "enterrados" en
la lista de Reports—. El único Workspace PMO es `PMO Capacity` (shortcuts a los 3 reportes de capacidad).

## Problema

Falta (a) un reporte que responda "¿cuánto esfuerzo planificamos vs cuánto hemos consumido?" por
Project/Task, y (b) un punto de acceso claro en PMO para los reportes de control.

## Decisiones

### D1 — Es una capacidad de **reporting**, no una nueva capa de planificación
Se implementa **un Script Report estándar** `PMO Planned vs Actual`. **No** hay nuevo modelo, motor
(`planned_vs_actual.py`), DocType ni Custom Field. La lógica vive en el `execute()` del reporte.

### D2 — Fuentes e indicadores (campos nativos)
- **Planned** = `Task.expected_time` (esfuerzo esperado actual).
- **Actual:** sin fecha de corte → `Task.actual_time` (acumulado nativo alimentado por Timesheet); con
  `status_date` → Σ `Timesheet Detail.hours` **submitted** (docstatus=1) con `date(from_time) <= status_date`
  (semántica ADR-0003; único bit custom, SQL estática parametrizada; reutiliza el patrón de
  `_actual_hours_to_date` extendido a Task).
- **Indicadores:** `Planned Hours`, `Actual Hours`, `Variance Hours` (= Actual − Planned), `% Consumed`
  (= Actual / Planned, con guarda de división por 0).
- **Nivel:** detalle por **Task** + **total por Project** excluyendo `is_group` del rollup (evita doble
  conteo; los grupos son envelope).

### D3 — Permisos (P4) y fecha de corte
Script Report ⇒ **no** aplica `permission_query_conditions`, así que `execute()` **impone P4** restringiendo a
Projects visibles (owner / DocShare / PMO Executive Access), reutilizando `pmo.permissions` (mismo patrón que
`PMO Status Report`). Filtro `status_date` con default = `Project.pmo_status_date` (v0.7.0), overridable;
vacío = Actual total nativo.

### D4 — Visibilidad: nuevo Workspace de control PMO
Se crea **un Workspace público nuevo** (`PMO Control`, module PMO, `is_standard`) que **reutiliza exactamente
el patrón de shortcuts a Script Reports** del Workspace `PMO Capacity` (header + bloques `shortcut`). Da
acceso directo a:
- `PMO Planned vs Actual`
- `PMO Status Report`
- `PMO Baseline Comparison`
- `PMO Change Register`

Los shortcuts **solo enrutan** a cada reporte (cero duplicación de lógica). **`PMO Capacity` no se toca**
(queda dedicado a capacidad). **Sin** Number Cards ni charts en este ciclo.

### D5 — Sin backend nuevo ni cambios a otros ADRs
Sin DocTypes/Custom Fields nuevos; **no** cambia el snapshot de Baseline (`snapshot_schema_version` sigue en
1) ni el reporte Status Date; ADR-0003/0004/0006/0007 **no** se modifican (ADR-0008 solo los referencia). El
único código nuevo: `execute()` del reporte + un helper `as-of por Task` (en `pmo/actual.py`, su hogar
natural).

## Fuera de alcance (diferido)
EVM (EV/PV/AC), CPI/SPI, forecast (EAC/ETC), **planned time-phased/BCWS**, CPM (#9), reservas de capacidad
(#10), constraints/deadlines (ADR-0007), Baseline como fuente de Planned (presupuesto congelado), reparto por
asignado, y Number Cards/charts de resumen en el Workspace.

## Consecuencias
- Un reporte operativo Planned vs Real por Project/Task, con corte opcional a `status_date`, accesible desde
  un Workspace de control PMO junto con los demás reportes de control (resuelve el "enterrado").
- `bench migrate` requerido para sincronizar el Report y el Workspace (**fixtures `is_standard`**); sin
  cambios de esquema (no Custom Fields/DocTypes).

## Riesgos
- Script Report ignora `pqc` → la P4 debe imponerse en `execute()` (mitigado: patrón ya probado en la app).
- Dos rutas de Actual (nativo total vs Timesheet as-of): ambas triviales; se documenta que sin corte se usa
  `actual_time` y con corte la suma de Timesheet.
- `actual_time` nativo depende de que las horas se registren vía Timesheet (horas fuera de Timesheet no
  cuentan) — comportamiento nativo aceptado.

## Alternativas descartadas
- Motor/módulo `planned_vs_actual.py` o nuevo modelo de horas → innecesario; los datos son nativos.
- **Report Builder** → no puede calcular Variance/% ni el as-of.
- Meter el reporte en `PMO Capacity` → desajuste temático; mejor un Workspace de control.
- Number Cards de resumen → no soportan as-of y duplicarían lógica; diferido.

## Criterios de aceptación
- Existe el Script Report `PMO Planned vs Actual` (P4) con columnas Planned/Actual/Variance/% Consumed, por
  Task y total de Project (excluye `is_group`), con `status_date` opcional (default `pmo_status_date`).
- Existe el Workspace público `PMO Control` con shortcuts a los 4 reportes; `PMO Capacity` intacto.
- Sin DocTypes/Custom Fields nuevos; `snapshot_schema_version` sigue en 1; ADR-0003/0004/0006/0007 sin cambios.
