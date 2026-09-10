# Portafolio (salud multi-proyecto)

Responde: **"¿cómo va cada proyecto y cuáles debo vigilar?"** en una sola vista, sin abrir proyecto por
proyecto. Menú **Reportes → PMO Portfolio**.

Es una **vista de consumo**: no calcula nada nuevo, resume por proyecto los indicadores que ya producen
`PMO Status Report` (control a fecha) y la comparación de esfuerzo (Planificado vs Real). Para el detalle de
un proyecto, abre `PMO Status Report` o `PMO Planned vs Actual`.

## Qué muestra (una fila por proyecto)

- **Project / Nombre / Estado.**
- **Salud** — semáforo derivado de las señales de control:
  - **Desviado** — el forecast supera el compromiso, o hay tareas vencidas, o tareas cuyo forecast excede su
    fecha comprometida.
  - **En riesgo** — el forecast se corrió respecto de la línea base (pero aún sin incumplir compromiso).
  - **En plan** — sin desviaciones positivas. (Adelantarse respecto de la línea base **no** penaliza.)
- **Fin (forecast)** — la fecha de fin que el plan proyecta hoy (`expected_end_date`), no una fecha calculada
  aparte.
- **Slip vs Baseline (d)** y **Slip vs compromiso (d)** — días de desviación (positivo = peor).
- **Vencidas** y **Forecast > compromiso** — conteos de tareas.
- **Planned (h) / Actual (h) / % Consumido** — esfuerzo agregado del proyecto (horas planificadas vs reales).

**Resumen (tarjetas):** total de **Proyectos**, **Desviados**, **En riesgo** y **Sin línea base**.

## Filtros

- **Company** (opcional) y **Incluir completados** (por defecto se ocultan los proyectos Completados;
  los Cancelados nunca aparecen).

## Privacidad

Solo ves los **proyectos que puedes ver** (los que posees, los que te compartieron, o todos si tienes acceso
ejecutivo). Un proyecto sin fecha de corte propia se evalúa **a hoy**. No se muestra ningún proyecto fuera de
tu alcance.
