# ADR-0003: Resource Capacity and Planned Allocation

**Estado:** Propuesto
**Fecha:** 2026-09-02
**App:** pmo · Depende de **ADR-0002** (privacidad Project/Task).

## Contexto

Cliente pide capacity planning (disponibilidad, carga, sobreasignación, utilización). En v16:
`Task.expected_time`/`actual_time`, `Timesheet Detail` (employee/project/task/hours), Employee,
Holiday List. **Employee no tiene** capacidad diaria; `_assign`/ToDo = responsable sin horas. No existe
asignación planificada por persona/periodo ni capacidad con vigencia.

## Problema

Responder capacidad/utilización sin hacer HRMS obligatorio, sin mezclar conceptos, respetando la
privacidad de Project/Task (ADR-0002/P4), y con las garantías de reproducibilidad correctas (ver más
abajo — **parcial y explícita**, no total).

## Modelo conceptual (4 conceptos separados, no mezclar)

```
Capacity     = cuánto podría trabajar el recurso (efectivo-datada: global u override)   [persistido, histórico]
Availability = Capacity − no-laborables (Holiday List) − ausencias aprobadas (Leave si HRMS)  [DERIVADO/día]
Allocation   = trabajo futuro comprometido (horas diarias materializadas al confirmar)  [persistido/día]
Actual       = tiempo real trabajado (Timesheet)                                        [DERIVADO, estado vigente]
Libre = Availability − Allocation ; Utilización = Allocation/Availability y Actual/Availability (separadas)
```

- **Availability** y **Actual** son **derivados** y reflejan el **estado vigente** de sus fuentes
  nativas (Holiday List, Leave, Timesheet). **No** se persisten ni se congelan.

## Garantía de reproducibilidad del MVP (explícita)

- **Capacity histórico:** sí, por **vigencias** (`PMO Capacity` efectivo-datado).
- **Allocation histórica:** sí, mediante **días materializados** (`PMO Allocation Day`) congelados al
  confirmar.
- **Availability y Actual:** **NO** se garantiza reproducibilidad histórica total: se **recalculan**
  desde sus fuentes nativas vigentes. Holiday List, Leave Application y Timesheet **pueden cambiar
  retroactivamente**, y eso se reflejará en Availability/Actual recalculados. Es comportamiento
  esperado, no un defecto.

## Modelo de datos mínimo

### `PMO Capacity` — capacidad efectivo-datada (un solo modelo: global + override)
- `employee` (Link Employee, **opcional**): vacío = **baseline global**; con valor = **override por persona**.
- `from_date` (Date, req): una fila rige **desde** su `from_date` **hasta** que otra del mismo scope la supersede.
- `capacity_hours_per_day` (Float, req).
- **Resolución** `capacity(employee, date)` = fila de ese employee con `from_date` ≤ date más reciente;
  si no hay → fila global (employee vacío) con `from_date` ≤ date más reciente. Sin default global mutable.
- Validación: no-solape de vigencias por scope.

### `PMO Resource Allocation` — plan de asignación (cabecera)
- `employee` (req), `project` (Link Project, **req**), `task` (Link Task, **opc**; validar que
  **pertenece al Project**), `from_date`, `to_date`, `planned_hours` (total), `status` (Draft/Confirmed),
  `distribution` (Even por defecto).
- **No** concede acceso al Project ni crea membresía/Assignment/ToDo.

### `PMO Allocation Day` — child table de `PMO Resource Allocation` (valores diarios canónicos)
- `date`, `hours`.
- Es **child table**: **hereda el boundary y los permisos** de `PMO Resource Allocation`. **No** lleva
  `permission_query_conditions` ni `has_permission` propios.

### Nativo reutilizado (no se persiste)
Holiday List, Timesheet (Actual), Employee, y Leave Application **solo si HRMS** está instalado.

## Decisiones

- **D1 — Capacidad:** un solo DocType `PMO Capacity` efectivo-datado; `employee` vacío = global, con
  valor = override; resolución más-específico-luego-global por `from_date`.
- **D2 — Allocation:** `PMO Resource Allocation` (Project req, Task opc que debe pertenecer al Project).
  No concede acceso al Project ni crea membresía/Assignment/ToDo. Identidad Project/Task se
  muestra/enmascara según ADR-0002/P4.
- **D3 — Granularidad y ciclo de vida:** **día** canónico.
  - **Draft:** la distribución diaria (`PMO Allocation Day`) puede **generarse y editarse**.
  - **Confirmed:** la distribución diaria queda **congelada**; Holiday List posterior **no** la altera.
  - Cambiar un plan confirmado es una **acción explícita de replanificación** (reabrir/replanificar,
    auditada), **no** una edición silenciosa.
  - Semana/mes = **agregación** de los días.
  - Materialización al confirmar: reparto uniforme en días hábiles del rango según Holiday List del
    momento; días editables manualmente **en Draft**.
- **D4 — HRMS opcional:** mínimo = ERPNext (Employee, Holiday List). `pmo` **no** declara `hrms` en
  `required_apps`; si está instalado, Availability descuenta Leave aprobada (detección en runtime).
- **D5 — Privacidad (P4):** `PMO Resource Allocation` (y por herencia su child `PMO Allocation Day`)
  **entran al boundary** (dimensión `project`) → `pqc`/`has_permission` en `PMO Resource Allocation`
  ligados a la visibilidad del Project. Reportes de capacidad: **agregación server-side**; identidad
  Project/Task **enmascarada** por boundary del observador; **bucket único "Comprometido
  (confidencial)"** sin nombre/cliente/conteo/atributos; mismo enmascarado en **Actual/Timesheet**
  dentro de los reportes PMO; `PMO Executive Access` ve desglose completo; usuario normal solo lo suyo
  + proyectos permitidos.

## Consecuencias

- Tres objetos nuevos pequeños (`PMO Capacity`, `PMO Resource Allocation`, `PMO Allocation Day` child);
  reportes de utilización.
- Reproducibilidad **parcial y explícita** (ver garantía arriba): Capacity y Allocation históricos;
  Availability y Actual recalculados desde fuentes vigentes.
- Separación estricta: Allocation (planificado) y Actual (real) nunca se suman.

## Riesgos

- **Availability/Actual reflejan el estado vigente** de Holiday List/Leave/Timesheet: cambios
  retroactivos alteran los cálculos históricos (esperado; documentado).
- **Re-materialización** al replanificar un plan confirmado cambia el plan de esas fechas (acción
  explícita, auditada). Holiday List **no** dispara re-materialización.
- **Reparto uniforme** puede no reflejar jornadas irregulares → edición manual por día en Draft;
  calendarios finos fuera de MVP.
- **De-anonimización** en reportes (P4) → bucket confidencial único, sin conteos/atributos; agregación
  server-side probada contra fugas.
- Solapes de vigencia en `PMO Capacity` → validación de no-solape por scope.

## Alternativas descartadas

- `default_capacity_hours_per_day` global mutable (rompe reproducibilidad de Capacity).
- Dos mecanismos separados (global vs Employee) para capacidad (un solo DocType con `employee` opcional lo resuelve).
- Persistir solo `planned_hours + rango` y redistribuir en cada cálculo (el pasado del plan cambiaría).
- Allocation solo a Task (no permite planificación temprana) o solo a Project (pierde precisión).
- `expected_time`/`_assign` como capacidad; HRMS como dependencia dura.
- `has_permission`/`pqc` propios en `PMO Allocation Day` (innecesario: hereda del padre).

## Impacto en nativo / hooks

- **Nativo:** sin cambios de core; se **lee** Employee, Holiday List, Timesheet (y Leave si HRMS).
- **Nuevos (pmo):** los 3 DocTypes; `permission_query_conditions`/`has_permission` para
  `PMO Resource Allocation` (dimensión project, según ADR-0002); función server-side de agregación de
  capacidad con enmascarado P4; lógica de materialización al confirmar.

## Estrategia de pruebas (datos ficticios)

- Capacidad: override 8h→4h a mitad de año → periodos previos conservan 8h (reproducible); global
  aplica a quien no tiene override.
- Allocation: en Draft se puede editar la distribución; al Confirmar se congela; cambiar Holiday List
  **no** altera días de un plan confirmado; replanificar es acción explícita.
- Sobreasignación: Σ Allocation/día > Availability se detecta.
- Availability/Actual: cambiar Holiday List/Timesheet retroactivamente **sí** cambia el recálculo
  (comportamiento esperado).
- Separación: Allocation y Actual nunca sumados; utilización calculada por separado.
- Privacidad P4: PMO Manager sin acceso a un Project → ve "confidencial" agregado, sin identidad,
  también en Actual; miembro → desglose; Executive → todo; usuario normal → solo lo suyo; agregación
  server-side no expone filas confidenciales.
- Sin HRMS: no falla; con HRMS: Leave aprobada reduce Availability.

## Criterios de aceptación

- Capacity/Availability/Allocation/Actual separados y verificables.
- **Capacity** (por vigencias) y **días de Allocation** (materializados) reproducibles; Availability y
  Actual se recalculan desde fuentes vigentes (garantía explícita, no total).
- ERPNext suficiente; HRMS solo enriquece.
- Ningún cálculo asume 8h fijas ni ignora festivos/ausencias.
- Reportes de capacidad respetan ADR-0002/P4 sin fugas de identidad.
