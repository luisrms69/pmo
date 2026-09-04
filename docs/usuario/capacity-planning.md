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
| **Libre** | Availability − Planned total (negativo = sobreasignado). |
| **Sobreasignación** | Cuánto excede el plan a la disponibilidad. |
| **Util. planificada / real** | Planned/Availability y Actual/Availability (nunca se suman entre sí). |
| **Estado** | Avisos de planificación (inconsistencias, tareas sin fechas, capacidad faltante, mapeo). |

## Privacidad (qué ve cada quien)

El reporte respeta la privacidad de proyectos (ver *Privacidad de proyectos y tareas*):

- **Dirección (PMO Executive Access)** → todas las personas y el desglose completo por proyecto.
- **PMO Manager** → todas las personas con sus **métricas** (capacidad, carga, libre, sobreasignación…),
  pero de los proyectos que no puede ver solo el bloque agregado **Comprometido (confidencial)** — sin
  nombre de proyecto, cliente, ni número de proyectos/tareas.
- **Usuario normal** → **solo su propia fila**. Ver su carga total no le da acceso a los proyectos: las
  horas de proyectos que no puede consultar siguen apareciendo como **Comprometido (confidencial)**.

## Notas

- Solo cuentan como carga las Tasks **en curso** (Open, Working, Pending Review, Overdue). Las
  **Completadas** ya no son plan pendiente (su tiempo real se ve en *Actual*).
- Una Task **sin fechas** no puede ubicarse en el calendario: sus horas se reportan como *sin fechas*.
- Si una persona no tiene capacidad configurada, se marca **capacidad faltante** (no se asume un valor).
- **HRMS es opcional**: si está instalado, las ausencias aprobadas reducen la disponibilidad.
