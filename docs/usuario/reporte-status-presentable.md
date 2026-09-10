# Reporte de estado presentable (para stakeholders)

Salida **imprimible / PDF** del estado de un proyecto, pensada para enviar al patrocinador o cliente. Es un
**Print Format** de `Project` llamado **PMO Project Status**: se ve como **HTML** en el navegador (Imprimir /
Vista de impresión) y se puede **descargar como PDF** con un clic.

## Cómo obtenerlo

1. Abre el **Project**.
2. Menú **Imprimir** (o `/app/project/<nombre>?print=1`).
3. Elige el formato **"PMO Project Status"**.
4. Míralo en HTML o descárgalo en **PDF**.

Solo puede verlo quien tiene permiso sobre el proyecto (misma privacidad P4 del resto de PMO).

## Qué incluye

**Encabezado ejecutivo:** proyecto, estado, empresa/cliente y **fecha de corte** (Status Date).

**Resumen ejecutivo** (lo que el stakeholder realmente evalúa):

- **Avance** (% completado) con barra.
- **Línea base** vigente y **slip vs Baseline**.
- **Forecast vigente** (fin que proyecta el plan) y **fecha comprometida** con **slip vs compromiso**.
- **Tareas vencidas al corte** y **forecast que excede el compromiso**.
- **Esfuerzo**: horas reales / planificadas y **% consumido**.
- **Salud** del proyecto: **En plan / En riesgo / Desviado**.

**Evaluación organizada de tareas** (no un volcado):

- Conteos compactos (total, completadas, activas, vencidas al corte).
- **Hitos** con fin baseline vs forecast y si están vencidos.
- **Tabla de tareas a evaluar** — solo las **relevantes**: vencidas al corte, con **slip ≠ 0**, cuyo forecast
  **excede su fecha comprometida**, o **hitos**. Ordenada por mayor desviación. Al pie indica **cuántas
  tareas** con línea base **no** se listan por no tener desviación relevante (no oculta información).

## Notas

- Las fechas se muestran en formato ISO (`AAAA-MM-DD`) para que el reporte sea estable en cualquier contexto
  (incluida la generación de PDF en segundo plano).
- El PDF lo genera el motor configurado en el site (por defecto wkhtmltopdf; puede usarse Gotenberg). El
  formato es el mismo en HTML y PDF.
