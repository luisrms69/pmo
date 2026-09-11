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
5. **Schedule (Gantt)** — cronograma visual del proyecto usando el **Gantt nativo de Frappe**. Dibuja las
   Tasks del proyecto con sus fechas reales de **Inicio/Fin esperado** (`exp_start_date`/`exp_end_date`),
   progreso y dependencias; los hitos se marcan aparte. Vistas Día / Semana / Mes; al hacer clic en una
   barra se abre la Task. Es **solo lectura**: no reprograma ni calcula fechas (sin CPM ni
   auto-scheduling). Respeta P4 (solo se listan Tasks visibles). Si una Task no tiene ambas fechas, no se
   dibuja; si ninguna las tiene, se indica cómo completarlas.

## Privacidad

Solo ves los datos que ya te autoriza el servidor: proyectos, tareas, líneas base y solicitudes de cambio
dentro de tu alcance. La pantalla no hace consultas adicionales que reconstruyan información oculta.
