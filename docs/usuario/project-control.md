# Project Control (gestión de un proyecto)

Responde: **"¿cómo va este proyecto y qué necesito revisar?"** para **un Project** concreto, reuniendo en
una sola pantalla lo que antes estaba disperso en varios reportes. Se abre desde: **workspace PMO → atajo
"Project Control"**; el **drill de `PMO Portfolio`** (clic en un proyecto); o el botón **PMO → PMO Project
Control** en el formulario nativo del Project (ya posicionado en ese Project).

Es una **vista de consumo**: no calcula nada nuevo. Cada pestaña consume el motor server-side del reporte
correspondiente (respetando privacidad P4); el detalle tabular exportable sigue disponible en **Reports**.

## Contexto (arriba)

- **Project** — selector; solo muestra proyectos que puedes ver (P4).
- **Status Date (fecha de corte)** — se prellena con la del Project (ADR-0006) o **hoy** por defecto; puedes
  cambiarla. La pantalla indica siempre qué fecha de corte se está usando. Aplica a *Reporte Ejecutivo*,
  *Status / Schedule* y *Planned vs Actual*.
- **Abrir Project** — abre el documento nativo del Project.

## Pestañas

1. **Reporte Ejecutivo** — vista integral del proyecto a la fecha de corte, pensada para dirección/cliente,
   en una sola página: encabezado con salud (semáforo), avance real, línea base y desvío, forecast y fecha
   comprometida con su desvío, **tareas previstas al corte** (cuántas tareas del plan debían estar
   terminadas — no es "avance"), cumplimiento, tareas vencidas, esfuerzo (horas reales a la fecha de corte
   vs planificadas y % consumido), **cronograma Gantt**, hitos, tabla de tareas con desviación y el
   **historial de solicitudes de cambio** (todas las formalizadas). Incluye además **Calidad de
   Planeación**: un indicador de **Madurez de planeación** (promedio de 5 componentes — % de tareas hoja
   con responsable / con fecha inicio / con fecha fin / con estimación / incorporadas a la línea base
   vigente) con su desglose siempre visible, y el listado de **tareas activas sin responsable** (una tarea
   completada no cuenta como problema de asignación). Cuando un componente no es evaluable (p. ej. sin
   línea base) se muestra "No evaluable", nunca cero. Es exactamente el mismo contenido del reporte
   imprimible **PMO Project Status** (misma fuente), embebido aquí para revisarlo sin cambiar de pantalla.
   No recalcula nada: el servidor compone el contexto y lo renderiza (respeta P4).
2. **Status / Schedule** — control a la fecha de corte (`PMO Status Report`): resumen (línea base vigente,
   forecast, fechas comprometidas, desvíos, vencidas, horas) y tabla por Task (fin baseline vs forecast,
   slip, compromiso, vencida al corte). Si el proyecto **no tiene línea base vigente** a la fecha, la tabla
   aparece vacía con una nota explicativa; el resumen sigue aplicando.
3. **Planned vs Actual** — esfuerzo por Task (`PMO Planned vs Actual`): planificado, real, variación y
   % consumido (con barra). La **variación** es `Real − Planificado`: positiva (sobreconsumo) se resalta;
   negativa (bajo lo planificado) es neutra.
4. **Baseline Comparison** — comparación entre **dos líneas base emitidas** del proyecto
   (`PMO Baseline Comparison`): tareas añadidas/eliminadas/modificadas, cambios de asignación y de Proyecto.
   Si el proyecto no tiene dos líneas base, se indica claramente.
5. **Change Control** — solicitudes de cambio del proyecto (`PMO Change Request`), con estado, fecha,
   prioridad e impacto; cada una abre su documento. Respeta la visibilidad del proyecto (P4). Si no hay
   solicitudes, se indica.

> El **Reporte Ejecutivo** y el reporte imprimible **PMO Project Status** comparten un **único contexto y
> un único template** (ADR-0011): el mismo Gantt/resumen se ve en la pestaña, en HTML y en PDF, sin
> duplicar cálculos.

## Privacidad

Solo ves los datos que ya te autoriza el servidor: proyectos, tareas, líneas base y solicitudes de cambio
dentro de tu alcance. La pantalla no hace consultas adicionales que reconstruyan información oculta.
