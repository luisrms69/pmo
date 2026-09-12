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
  cambiarla. La pantalla indica siempre qué fecha de corte se está usando. Aplica a *Status / Schedule* y
  *Planned vs Actual*.
- **Abrir Project** — abre el documento nativo del Project.

## Pestañas

1. **Status / Schedule** — control a la fecha de corte (`PMO Status Report`): resumen (línea base vigente,
   forecast, fechas comprometidas, desvíos, vencidas, horas) y tabla por Task (fin baseline vs forecast,
   slip, compromiso, vencida al corte). Si el proyecto **no tiene línea base vigente** a la fecha, la tabla
   aparece vacía con una nota explicativa; el resumen sigue aplicando.
2. **Planned vs Actual** — esfuerzo por Task (`PMO Planned vs Actual`): planificado, real, variación y
   % consumido (con barra). La **variación** es `Real − Planificado`: positiva (sobreconsumo) se resalta;
   negativa (bajo lo planificado) es neutra.
3. **Baseline Comparison** — comparación entre **dos líneas base emitidas** del proyecto
   (`PMO Baseline Comparison`): tareas añadidas/eliminadas/modificadas, cambios de asignación y de Proyecto.
   Si el proyecto no tiene dos líneas base, se indica claramente.
4. **Change Control** — solicitudes de cambio del proyecto (`PMO Change Request`), con estado, fecha,
   prioridad e impacto; cada una abre su documento. Respeta la visibilidad del proyecto (P4). Si no hay
   solicitudes, se indica.

> El cronograma **Gantt** del proyecto se presenta en el **reporte imprimible** *PMO Project Status*
> (resumen ejecutivo + avance + Gantt en un solo documento), no como pestaña interactiva aquí.

## Privacidad

Solo ves los datos que ya te autoriza el servidor: proyectos, tareas, líneas base y solicitudes de cambio
dentro de tu alcance. La pantalla no hace consultas adicionales que reconstruyan información oculta.
