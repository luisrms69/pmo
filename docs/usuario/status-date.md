# Control a fecha de corte (Status Date)

Responde: **"¿Cómo estaba este proyecto a una fecha determinada respecto de lo planeado, la línea base
aprobada y lo realmente ejecutado?"** (ADR-0006).

## La fecha de corte (Status Date / Data Date)

Cada Project tiene el campo **PMO Status Date** (`Project.pmo_status_date`): la **fecha de corte vigente**
del control. Reglas:

- Solo puede ser **hoy o una fecha pasada** (no admite fecha futura en esta versión).
- Es opcional: si está vacía, se elige la fecha directamente en el reporte.
- La edita el **owner** del Project (misma regla de privacidad P4 del resto de PMO).

## El reporte "PMO Status Report"

Menú **Reportes → PMO Status Report**. Parámetros:

- **Project** (obligatorio).
- **Status Date**: por defecto toma la `PMO Status Date` del Project (o hoy); puedes elegir cualquier fecha
  **≤ hoy**.

Solo verás proyectos que tienes permitido ver (owner, colaboradores compartidos o acceso ejecutivo).

### Qué muestra

**Resumen (tarjetas):**

- **Fecha de corte** usada.
- **Línea base vigente** a esa fecha (o "— sin baseline a la fecha").
- **Deslizamiento de fecha final (días):** cuántos días se corrió la fecha de fin del proyecto entre la
  **línea base** y el **plan actual**.
- **Tareas vencidas no terminadas:** cuántas debían estar terminadas a la fecha de corte y no lo estaban.
- **Horas reales a la fecha:** horas de **Timesheet** registradas hasta la fecha de corte.
- **Completadas / previstas a la fecha:** cuántas de las tareas que vencían a la fecha están completadas.

**Detalle (tabla):** la lista de **tareas que debían estar terminadas a la fecha y no lo estaban**, con su
fecha de fin según la línea base.

### Cómo interpretarlo (importante)

- **Baseline** = el plan **aprobado** vigente a la fecha de corte (línea base congelada).
- **Current** = el **plan tal como está hoy**, evaluado contra la fecha de corte. **No** reconstruye el plan
  que existía en esa fecha.
- **Actual** = lo realmente ejecutado: horas de Timesheet fechadas hasta el corte (fiable) y, para saber si
  una tarea estaba terminada, se usa su fecha de finalización (`completed_on`) como aproximación.
- **No** incluye avance porcentual histórico, EVM, forecast ni ruta crítica (fuera de alcance de esta
  versión).

Si el Project no tiene una línea base vigente a la fecha, el reporte lo indica y muestra solo Current y
Actual.
