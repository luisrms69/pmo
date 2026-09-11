# Portafolio (salud multi-proyecto)

Responde: **"¿cómo va cada proyecto y cuáles debo vigilar?"** en una sola vista, sin abrir proyecto por
proyecto. Acceso principal: **workspace PMO → atajo "Portfolio"**, que abre la **Page de gestión**
`PMO Portfolio` (Desk). El **Script Report** `PMO Portfolio` (misma información en tabla) sigue disponible en
la sección **Reports** para consulta tabular/exportación.

Es una **vista de consumo**: no calcula nada nuevo. La Page consume el mismo motor server-side del Script
Report (que resume por proyecto los indicadores que ya producen `PMO Status Report` y la comparación de
esfuerzo Planificado vs Real) y lo presenta en tres capas:

1. **Resumen** — tarjetas de KPIs (Proyectos, En plan, En riesgo, Desviado, con tareas vencidas, forecast que
   excede compromiso, sin línea base) y una barra de distribución de salud.
2. **Requiere atención** — excepciones: proyectos Desviados / En riesgo / con vencidas / con forecast sobre el
   compromiso, ordenados por severidad. Usa únicamente señales existentes (sin score nuevo).
3. **Portafolio** — la tabla completa con todo el detalle (una fila por proyecto).

Desde cualquier proyecto (en "Requiere atención" o en la tabla) se abre **`PMO Project Control`** de ese
proyecto (que a su vez ofrece "Abrir Project" al documento nativo); el detalle a fecha sigue en
`PMO Status Report` / `PMO Planned vs Actual`.

> **Punto de entrada:** el workspace **PMO** (menú lateral) es el centro de control: enlaza el Portafolio y
> todos los reportes de control y capacidad, más la configuración (`PMO Capacity`, baselines, change requests).

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
