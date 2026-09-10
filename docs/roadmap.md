# Roadmap / Backlog técnico — pmo

Índice **único y durable** del backlog de producto: qué se entregó y qué queda diferido, para priorizar en
la próxima revisión de producto. No es compromiso de fecha ni orden fijo. Los ADR/issues citados son la
fuente de cada decisión.

## Entregado

- **Ronda funcional v0.7.0–v0.11.0 (liberada):** Status Date (ADR-0006), fechas comprometidas (ADR-0007),
  Planificado vs Real (ADR-0008), Forecast y desviaciones (ADR-0009), Confiabilidad de Capacity (ADR-0010).

## En implementación — próxima v0.12.0 (ronda product-readiness, aún sin release)

> Estado: en desarrollo en la rama `feat/product-readiness-round`; **v0.12.0 aún no liberada**. Se marcará
> como *Entregado* tras completar la ronda y publicar el release.

- **UX de captura/mantenimiento de `PMO Capacity`** — reporte `PMO Resource Capacity` (cobertura: efectiva/
  origen/vigencia por recurso) + ergonomía del formulario. *(Cierra el pendiente técnico #6.)* — commiteado.
- **Dashboard / visión de portafolio multi-proyecto** — reporte `PMO Portfolio` (salud por proyecto, P4). — commiteado.
- **Salida presentable del Status Report** — Print Format `PMO Project Status` (HTML/PDF, stakeholder). — commiteado.
- **Corrección documental** de `capacity-planning.md`. — este commit.
- **Workspace PMO unificado / landing** — **pendiente (Commit #5)**, aún no implementado.

## Pendientes diferidos (revisión de producto posterior a v0.12.0)

### Posterior según demanda
| # | Pendiente | Registro | Origen / contexto |
|---|---|---|---|
| 1 | **Tentativo / Confirmado en asignaciones** — mayor hueco funcional de Capacity. Posible `ToDo.pmo_commitment` (Tentativo/Confirmado) o diseño equivalente. **No** asumir aún el Custom Field: la forma se decide al retomarlo. Esfuerzo Medio, riesgo Medio (cambia semántica de carga). | **Sin issue** — aquí | Auditoría v0.11.0; ADR-0010 (Fuera de alcance) |
| 8 | **Alertas proactivas** (desviación / sobrecarga / vencimientos) — hoy los avisos solo se ven al abrir el reporte. Depende del portafolio (ya entregado) como fuente. Esfuerzo Medio. | **Sin issue** — aquí | Revisión global post-v0.11.0 |
| 9 | **Onboarding / setup guiado** (roles, capacidad, Holiday List, mapeo Employee↔User). Reduce fricción de arranque. Esfuerzo Medio. | **Sin issue** — aquí | Revisión global post-v0.11.0 |
| 2 | **Reservas de capacidad** — reservar capacidad antes de asignación firme. Esfuerzo Alto, riesgo Medio-Alto (dato persistido nuevo vs derivación). | GitHub issue **#10** | ADR-0003 / auditoría capacity |
| 3 | **CPM / ruta crítica** — habilita forecast de fecha **real** (qué tareas empujan el fin). Esfuerzo Alto. | GitHub issue **#9** | ADR-0006/0009 |

### Diferido técnico (nicho / costo alto, sin demanda demostrada)
| # | Pendiente | Registro | Origen / contexto |
|---|---|---|---|
| 4 | **Constraints tipados de cronograma** — SNET, FNLT, MSO, MFO. Hasta que exista necesidad real. | **Sin issue** — aquí | ADR-0007 (Fuera de alcance) |
| 5 | **UX de `pmo_planned_hours` por asignado** — el **cálculo** ya es correcto (ADR-0003 D3); la **captura** es friccionada (exige editar el ToDo). **No** tocar el diálogo nativo "Assign To"; evaluar una UX segura. | **Sin issue** — aquí | ADR-0003; auditoría v0.11.0 |

## Notas

- Numeración estable heredada de la revisión global (10 puntos): la ronda v0.12.0 aborda los #6, #7 y #10
  (+ workspace landing, Commit #5 pendiente); aquí quedan los demás con su número original.
- Los ítems **sin issue** viven en este documento y en el "Fuera de alcance" de su ADR. Si se decide
  seguimiento formal en GitHub (paridad con #9/#10), crear el issue entonces — sin duplicar este registro.
- Este documento es el **índice único** del backlog; los ADR mantienen el detalle de *por qué* se difirió
  cada uno. **Ninguno de estos pendientes se implementa sin decisión explícita de producto.**
