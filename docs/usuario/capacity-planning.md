# Capacity Planning (planificación de capacidad)

Capacity Planning te muestra, **por persona**, cuánta capacidad tiene, cuánto trabajo tiene planificado,
cuánto tiempo real ha registrado, cuánta capacidad libre le queda y si está **sobreasignada**.

No hay que capturar el plan dos veces: la carga se **deriva** de lo que ya existe en ERPNext
(**Tasks** y sus **asignaciones**). Tú planificas con Tasks y las asignas a personas; el reporte lo lee.

## Procedimiento

1. **Crea el Project**.
2. **Construye el WBS** con **Tasks** (árbol de tareas).
3. En cada Task define **Expected Time** (esfuerzo en horas) y **Expected Start/End Date** (fechas).
4. **Asigna** la Task a una o varias personas con el botón **Assign** (asignación nativa).
5. Abre el reporte **PMO Capacity Planning**.
6. Elige el rango de fechas y la granularidad (**Day / Week / Month**).
7. Revisa por persona: capacidad, disponibilidad, planificado, actual, libre y sobreasignación.
8. Para ajustar, cambia la Task (fechas, esfuerzo o asignados) desde el flujo normal — el reporte se
   recalcula solo. **No** hay una pantalla aparte donde volver a capturar el plan.

## Cómo se reparten las horas entre asignados

- **Una sola persona** asignada → toda la `Expected Time` de la Task es su carga.
- **Varias personas** sin más datos → la `Expected Time` se reparte **en partes iguales**.
- ¿Alguien lleva una parte distinta? Abre **su asignación** (el registro *ToDo* de esa Task) y pon las
  horas en **PMO Planned Hours**. El resto de `Expected Time` se reparte entre los demás.
- Reglas que evitan errores silenciosos:
  - si las horas explícitas **superan** la `Expected Time` → se marca **inconsistencia**;
  - si **todos** tienen horas explícitas, su suma debe ser **exactamente** la `Expected Time` (ni de más
    ni de menos), o se marca inconsistencia.

> El campo **PMO Planned Hours** vive en el registro de asignación (ToDo), no en un formulario nuevo. En
> el diálogo rápido de *Assign* no aparece; para fijarlo, abre la asignación.

## Qué significa cada columna

| Columna | Qué es |
|---|---|
| **Capacity** | Horas/día que la persona podría trabajar (según su configuración de capacidad). |
| **Availability** | Capacity menos festivos y ausencias aprobadas. |
| **Planned visible** | Horas planificadas en proyectos que **tú** puedes ver. |
| **Comprometido (confidencial)** | Horas planificadas en proyectos que no puedes ver — **agregado, sin identidad**. |
| **Planned total** | Suma de planificado (visible + confidencial). |
| **Actual visible / confidencial / total** | Tiempo real (Timesheet), con el mismo criterio de privacidad. |
| **Libre** | Availability − Planned total (negativo = sobreasignado). **N/D** si no hay capacidad configurada. |
| **Sobreasignación** | Cuánto excede el plan a la disponibilidad. **N/D** si no hay capacidad configurada (no se reporta como sobreasignación). |
| **Util. planificada / real** | Planned/Availability y Actual/Availability (nunca se suman entre sí). **N/D** si no hay capacidad. |
| **Estado** | Avisos de planificación (inconsistencias, tareas sin fechas, capacidad faltante, mapeo). |

> **Capacidad faltante (importante):** si una persona **no tiene capacidad configurada** para el periodo,
> las columnas derivadas (Availability, Libre, Sobreasignación, Utilización) aparecen **vacías / N/D**, **no
> como 0**. Así **no** se marca como "sobreasignada" solo por faltar su capacidad. Esas personas se cuentan en
> el KPI **"Recursos sin capacidad vigente"** del resumen y quedan señaladas con estado *capacidad faltante*.

## Privacidad (qué ve cada quien)

El reporte respeta la privacidad de proyectos (ver *Privacidad de proyectos y tareas*):

- **Dirección (PMO Executive Access)** → todas las personas y el desglose completo por proyecto.
- **PMO Manager** → todas las personas con sus **métricas** (capacidad, carga, libre, sobreasignación…),
  pero de los proyectos que no puede ver solo el bloque agregado **Comprometido (confidencial)** — sin
  nombre de proyecto, cliente, ni número de proyectos/tareas.
- **Usuario normal** → **solo su propia fila**. Ver su carga total no le da acceso a los proyectos: las
  horas de proyectos que no puede consultar siguen apareciendo como **Comprometido (confidencial)**.

## Vistas disponibles (Workspace **PMO Capacity**)

Desde el Desk, en el workspace **PMO Capacity**, tienes tres vistas (se abren con un clic):

1. **Centro de recursos / Capacity Planning** — por persona: capacidad, disponibilidad, planificado,
   real, libre, sobreasignación y utilización. Con el filtro **Granularity** eliges **Day / Week /
   Month / Total** (usa **Total** para el resumen general, o Day/Week/Month para la línea de tiempo).
   Trae una **gráfica** (Disponibilidad vs Planificado) y **tarjetas** (Recursos, Sobreasignados,
   Utilización). Las celdas de utilización/sobreasignación se colorean (ámbar 80–100 %, rojo >100 %).
2. **Uso de recursos por proyecto** — árbol **Persona → Proyecto** con las horas por proyecto.
3. **Trabajo por recurso** — las **Tareas** de cada persona: proyecto, fechas, esfuerzo, horas
   planificadas del periodo y estado.

Todas respetan la privacidad (ver arriba): lo que no puedes ver aparece como **Comprometido
(confidencial)** o **Confidencial**, nunca con su nombre real. El workspace **PMO Capacity** solo es
visible para los roles autorizados (no es visible para todo el mundo pese a ser un workspace de app).

## Página Capacity Planning (pantalla dedicada)

Además de los reportes del workspace, hay una **página** dedicada (Desk → `capacity_planning`) con una
experiencia tipo MS Project. Arriba eliges **Desde / Hasta** y la escala **Día / Semana / Mes** (la
unidad siempre es **Horas**); a la izquierda, el panel **Empleados** (buscador, selección múltiple,
Todos/Limpiar) mantiene tu selección al cambiar de vista. Cinco vistas:

1. **Mapa de calor de capacidad** — colores por % de utilización planificada (verde <80, ámbar 80–100,
   rojo >100); pasa el cursor por una celda para ver Capacity/Availability/Planned/Free/Utilización.
2. **Uso de recursos** — el detalle por empleado y periodo (Capacity, Availability, Planned, Free,
   Utilización planificada).
3. **Uso de recursos por proyecto** — para **un empleado**: en qué proyectos tiene horas planificadas en
   cada periodo (los proyectos que puedes abrir son enlaces).
4. **Disponibilidad restante** — horas **libres** por empleado y periodo. `—` significa **sin
   disponibilidad** (festivo/ausencia): no es lo mismo que 0 horas libres.
5. **Trabajo por recurso** — para **un empleado**: sus tareas agrupadas por proyecto, con fechas (o
   *Sin fechas*), horas planificadas y estado.

Toda la privacidad se mantiene igual que en los reportes: nunca verás el nombre de un proyecto o tarea
que no te corresponde. Estas vistas muestran **solo lo planificado** (no el tiempo real).

## Cobertura de capacidad — reporte **PMO Resource Capacity**

Para **configurar y mantener** la capacidad de los recursos. Menú **Reportes → PMO Resource Capacity**.
Responde: *¿qué capacidad efectiva tiene hoy cada recurso y quién no la tiene configurada?*

- Filtros: **A la fecha** (por defecto hoy), **Employee** y **Departamento** (opcionales).
- Columnas: recurso, nombre, departamento, **Capacidad h/día**, **Origen** y **Vigente desde**.
- **Origen:** `Override` (fila propia del Employee), `Global` (baseline sin Employee) o **`Faltante`** (no hay
  capacidad vigente a la fecha → se debe configurar en `PMO Capacity`).
- Resumen: **Recursos**, **Sin capacidad configurada** (naranja si hay) y **Con override individual**.
- Alcance: tú ves **tu** recurso; PMO Manager / acceso ejecutivo ven todos. No muestra Project/Task.

Complementa el KPI *"Recursos sin capacidad vigente"* del reporte de planificación: aquí lo ves a nivel de
**configuración** (aunque el recurso aún no tenga carga), para no dejar recursos sin capacidad en silencio.

## Notas

- **`Actual` (tiempo real) no se muestra en estas vistas.** Se reserva para una vista futura de análisis
  histórico (*Planificado vs Real* / *Cumplimiento de planificación*), aún no disponible.

- Solo cuentan como carga las Tasks **en curso** (Open, Working, Pending Review, Overdue). Las
  **Completadas** ya no son plan pendiente (su tiempo real se ve en *Actual*).
- Una Task **sin fechas** no puede ubicarse en el calendario: sus horas se reportan como *sin fechas*.
- Si una persona no tiene capacidad configurada, se marca **capacidad faltante**: sus métricas derivadas
  quedan **N/D** (no 0) y **no** cuenta como sobreasignada. El resumen indica cuántos **recursos sin
  capacidad vigente** hay para que se configure su capacidad.
- **HRMS es opcional**: si está instalado, las ausencias aprobadas reducen la disponibilidad.
