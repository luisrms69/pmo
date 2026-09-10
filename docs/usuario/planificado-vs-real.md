# Planificado vs Real (esfuerzo)

Responde: **"¿Cuánto esfuerzo habíamos planificado y cuánto hemos consumido realmente?"** por proyecto y
tarea (ADR-0008).

Es una capacidad de **reporte**: pone lado a lado datos que ya existen de forma nativa en ERPNext
(`Task.expected_time`, `Task.actual_time`, horas de `Timesheet`). No introduce una nueva forma de planificar
ni de capturar horas.

## Dónde encontrarlo

Desde el **Workspace `PMO Control`** (menú lateral), que reúne los reportes de control del proyecto:
Planificado vs Real, Status Report, Comparación de línea base y Registro de cambios. También desde el menú
**Reportes → PMO Planned vs Actual**.

## El reporte "PMO Planned vs Actual"

Menú **Reportes → PMO Planned vs Actual**. Parámetros:

- **Project** (obligatorio). Al elegirlo, se prellena la fecha de corte con la `PMO Status Date` del
  proyecto (si la tiene).
- **Status Date (corte, opcional)**: fecha `≤ hoy`. Cambia **cómo se calcula el Real** (ver abajo). Si la
  dejas vacía, se usa el acumulado nativo de cada tarea.

Solo verás proyectos que tienes permitido ver (owner, colaboradores con los que se compartió el proyecto o
acceso ejecutivo) — la misma regla de privacidad P4 del resto de PMO.

### Qué muestra

**Detalle (tabla), una fila por tarea hoja:**

- **Task** y **Subject**.
- **Planned Hours** — el esfuerzo esperado de la tarea (`expected_time`).
- **Actual Hours** — el esfuerzo real consumido (ver "Cómo se calcula el Real").
- **Variance Hours** — `Actual - Planned`. Positivo = te pasaste del plan; negativo = aún por debajo.
- **% Consumed** — `Actual / Planned`. Vacío si la tarea no tiene horas planificadas (no se divide por 0).

Las **tareas de grupo (resumen)** no aparecen como fila propia: sus horas ya están en las tareas hoja, así
que incluirlas duplicaría el total.

**Resumen (tarjetas):** fecha de corte usada, total **Planned**, total **Actual**, **Variance** (roja si te
pasaste, verde si no) y **% Consumed** del proyecto.

## Cómo se calcula el Real

- **Sin fecha de corte:** se usa `Task.actual_time`, el acumulado nativo que ERPNext alimenta desde los
  Timesheets.
- **Con fecha de corte (Status Date):** se suman las horas de **Timesheet** confirmados (submitted) hasta el
  **final de ese día** (incluye las horas registradas durante el propio día de corte). Es la misma semántica
  de "horas reales a la fecha" del **PMO Status Report**.

Solo cuentan los Timesheets **confirmados**; los borradores no suman.

## Cómo interpretarlo

- **Variance > 0**: la tarea/proyecto ya consumió más horas de las planificadas.
- **% Consumed cercano al 100 %** con la tarea aún abierta: probable riesgo de sobre-esfuerzo.
- **% Consumed vacío**: la tarea no tenía horas planificadas; compara solo el Real.
- El Real depende de que las horas se registren vía **Timesheet**. Trabajo no capturado en Timesheet no
  aparece como Actual (comportamiento nativo de ERPNext).

## Qué NO hace (en esta versión)

No calcula valor ganado (EVM), ni CPI/SPI, ni pronósticos (EAC/ETC), ni usa la **línea base** como fuente
del plan (el plan es el `expected_time` vigente, no un presupuesto congelado). Esos análisis quedan fuera de
alcance por ahora.
