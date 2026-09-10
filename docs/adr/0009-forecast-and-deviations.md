# ADR-0009: Forecast vigente y desviaciones

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Ciclo:** v0.10.0

## Contexto

Con Status Date (ADR-0006), fechas comprometidas (ADR-0007), Baseline (ADR-0004) y Planificado vs Real
(ADR-0008) ya existen las piezas para responder *"¿hacia dónde va el proyecto y qué desviaciones vigilar?"*
**sin** construir un motor predictivo nuevo. El plan vivo de ERPNext (`Project.expected_end_date` /
`Task.exp_end_date`) **ya es el forecast vigente**: se desplaza con dependencias y reprogramación. Lo que
falta no es "predecir", sino **contrastar** ese forecast contra la Baseline y el compromiso, y **mostrar**
desviaciones que hoy solo existen como avisos (ADR-0007) o no se ven por Task.

## Problema

`PMO Status Report` hoy computa el slip de fecha final (Baseline vs Current), las tareas vencidas al corte y
las horas reales; **no** muestra: (a) desviación vs fecha comprometida a nivel Project, (b) cuántas Tasks
tienen un forecast que excede su `pmo_deadline`, (c) el slip por Task (Baseline vs Current) en una vista
única. Y falta declarar explícitamente que el `expected_end_date` actual **es** el forecast, para no inducir
una segunda fecha calculada.

## Decisiones

### D1 — El forecast vigente es el plan vivo de ERPNext (no un segundo motor)
PMO **no calcula** una fecha final predictiva propia. Reconoce `Project.expected_end_date` (y
`Task.exp_end_date`) como el forecast vigente y lo **muestra y contrasta** contra Baseline y compromiso. No
hay velocity/run-rate, ni EVM, ni CPM.

### D2 — Ampliación de `PMO Status Report` (no reporte nuevo)
Se amplía `build_status_report` + el reporte, reutilizando los planos que ya compone:
- **Se mantiene** el slip Baseline vs Current existente (`final_date_slip_days`) y el indicador de vencidas.
- **Nuevo (Project):** desviación **Current End vs `pmo_committed_end_date`** = `expected_end_date -
  pmo_committed_end_date` en días (positivo = el forecast supera el compromiso; `None` si falta el
  compromiso).
- **Nuevo (conteo):** número de Tasks (no `is_group`) cuyo **forecast excede la fecha comprometida**
  (`exp_end_date > pmo_deadline`, ambos presentes). **No** es "vencidas": puede ser una fecha futura cuyo
  plan ya proyecta incumplimiento.
- **Nuevo (por Task, una sola tabla ampliada):** el detalle muestra **todas las Tasks con baseline
  disponible** con: `baseline_exp_end_date`, `current/forecast exp_end_date`, `slip_days`
  (`current - baseline`), `pmo_deadline`, y **si estaba vencida al Status Date**. Las vencidas quedan como
  una **columna/marca** dentro de esta tabla, no como una segunda tabla.
- **Presentación:** tarjeta que muestra `expected_end_date` **rotulada como "Forecast vigente (plan)"**, con
  sus dos desviaciones (vs Baseline, vs Compromiso).

### D3 — "Vencidas al Status Date" se mantiene diferenciado
El indicador existente **tareas realmente vencidas al corte** (baseline `exp_end_date <= status_date` y sin
completar) es un concepto distinto de "forecast excede compromiso" y **se conserva separado**
(`tasks_overdue_at_cutoff`). En la tabla ampliada aparece como marca por Task; como indicador de resumen
sigue existiendo por su cuenta.

### D4 — `PMO Planned vs Actual` sin cambios de forecast
Se mantiene Planned / Actual / Variance / % Consumed. **No** se agrega ETC/EAC ni forecast basado en
`progress`. Motivo registrado: `actual + max(planned - actual, 0)` es esencialmente `max(planned, actual)` —
no es un forecast; y `progress` es dato manual no fiable para sustentar predicción. En este ciclo el reporte
solo se **referencia** en la documentación, no se toca su código.

### D5 — Permisos, datos y semántica de signos
P4 ya impuesto en `build_status_report` (READ sobre Project). Todos los datos ya existen: Baseline snapshot
(`exp_end_date` por Task y Project), Custom Fields `pmo_committed_end_date`/`pmo_deadline` (ADR-0007),
`Task.exp_end_date` nativo. **Sin** DocTypes, Custom Fields ni cambios de esquema -> sin patch;
`snapshot_schema_version` sigue en 1.
**Signos:** positivo = peor (más tarde / excede el límite). `slip_vs_baseline > 0` = el plan termina después
que la baseline; `slip_vs_committed > 0` = el forecast supera el compromiso; `task_slip > 0` = la tarea se
corrió respecto de su baseline. Fecha faltante -> indicador `None` con nota, nunca 0 implícito.

## Fuera de alcance (diferido)
EAC/ETC, forecast basado en `progress`, EVM completo (EV/PV/AC/BCWS), CPI/SPI, CPM/ruta crítica (#9),
reservas de capacidad (#10), constraints tipados, y cualquier motor de planificación paralelo o segunda
fecha final calculada.

## Consecuencias
- `PMO Status Report` responde "estado y desviaciones a la fecha" de forma completa: fecha (Baseline y
  Compromiso), vencidas, forecast que excede compromiso y slip por Task — con el forecast del plan explícito.
- Cambios solo en `pmo/status_date.py` + el reporte `PMO Status Report` (fixture `is_standard` ->
  `bench migrate`). Sin esquema, sin patch.
- Se evita etiquetar como "forecast/EAC" métricas que no lo son.

## Riesgos
- La tabla por Task amplía su alcance (de "vencidas" a "con baseline"); podría crecer en proyectos grandes —
  mitigable ordenando por slip descendente y marcando lo relevante.
- La desviación vs compromiso depende de que se capture `pmo_committed_end_date`/`pmo_deadline`; sin ellos,
  `None`/exclusión (comportamiento honesto, no cero).

## Alternativas descartadas
- **ETC/EAC con `expected_time - actual_time`** -> colapsa a `max(planned, actual)`; falsa precisión.
- **Forecast por `progress`** -> dato manual poco fiable.
- **Reporte nuevo `PMO Forecast & Deviations`** -> solape con Status Report; se prefiere ampliar el existente.
- **Segunda fecha final calculada** -> duplicaría el forecast que ya da ERPNext.
- **Dos tablas separadas (vencidas / slip)** -> se prefiere una sola tabla ampliada con marca de vencida.

## Criterios de aceptación
- `build_status_report` devuelve, además de lo actual: `slip_vs_committed_days` (Project), conteo de Tasks
  cuyo forecast excede `pmo_deadline`, y por Task en el detalle `baseline_exp_end_date` /
  `current_exp_end_date` / `slip_days` / `pmo_deadline` / marca de vencida al corte.
- El indicador `tasks_overdue_at_cutoff` (vencidas al Status Date) se mantiene diferenciado.
- El reporte muestra el `expected_end_date` rotulado como forecast vigente + sus dos desviaciones; Planned vs
  Actual queda intacto.
- Sin DocTypes/Custom Fields nuevos; `snapshot_schema_version` = 1; ADR-0004/0006/0007/0008 sin modificar
  (solo referenciados).
- Tests de la composición pura: signos, `None` por fechas faltantes, conteo por deadline (forecast excede
  compromiso, incl. fecha futura), slip por Task, y diferenciación vencida-al-corte vs excede-compromiso.
