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
- **Forecast vigente (plan): fin** — la fecha de fin **actual del plan** de ERPNext. Es *nuestro forecast*:
  no calculamos una segunda fecha, mostramos la que el plan ya proyecta.
- **Deslizamiento vs Baseline (días):** cuántos días se corrió el fin entre la **línea base** y el **plan
  actual (forecast)**.
- **Deslizamiento vs compromiso (días):** cuántos días el **forecast** supera la **fecha comprometida** del
  proyecto (ADR-0007). Vacío si no hay fecha comprometida.
- **Tareas: forecast excede compromiso** — cuántas tareas tienen un fin proyectado **posterior a su fecha
  comprometida** (`pmo_deadline`). Ojo: **no** significa "vencidas"; puede ser una fecha **futura** cuyo plan
  ya proyecta incumplimiento.
- **Tareas vencidas no terminadas:** cuántas debían estar terminadas a la fecha de corte y no lo estaban
  (indicador **distinto** del anterior).
- **Horas reales a la fecha:** horas de **Timesheet** registradas hasta la fecha de corte.
- **Completadas / previstas a la fecha:** cuántas de las tareas que vencían a la fecha están completadas.

**Detalle (tabla única por tarea):** todas las tareas con línea base disponible, con su **fin (Baseline)**,
**fin (Forecast)**, **slip (días)** = forecast − baseline, **fecha comprometida** y si estaba **vencida al
corte**. Ordenada por mayor desviación primero.

### Cómo interpretarlo (importante)

- **Baseline** = el plan **aprobado** vigente a la fecha de corte (línea base congelada).
- **Current** = el **plan tal como está hoy**, evaluado contra la fecha de corte. **No** reconstruye el plan
  que existía en esa fecha.
- **Actual** = lo realmente ejecutado: horas de Timesheet fechadas hasta el corte (fiable) y, para saber si
  una tarea estaba terminada, se usa su fecha de finalización (`completed_on`) como aproximación.
- **Forecast** = el fin que el plan de ERPNext proyecta hoy (`expected_end_date`). PMO lo **contrasta** con
  la línea base y con la fecha comprometida; **no** calcula una predicción propia ni una segunda fecha.
- **No** incluye avance porcentual histórico, EVM, CPI/SPI, EAC/ETC ni ruta crítica (fuera de alcance de
  esta versión).

Si el Project no tiene una línea base vigente a la fecha, el reporte lo indica y muestra solo Current y
Actual.
