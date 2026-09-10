# Roadmap / Backlog técnico — pmo

Registro **durable** de pendientes funcionales diferidos, para priorizar en la **revisión global de
producto** (posterior a v0.11.0). No es compromiso de implementación ni orden fijo; es memoria del backlog
descubierto durante el desarrollo. Los ADR citados son la fuente de la decisión de diferir.

> **Regla de proceso:** v0.11.0 (ADR-0010) es el **último ciclo funcional** de la ronda actual. Tras
> liberarlo **no** se inicia automáticamente otro ciclo: primero se hace la **revisión global de producto**
> y se prioriza este backlog.

## Pendientes diferidos

| # | Pendiente | Estado del registro | Origen / contexto |
|---|---|---|---|
| 1 | **Tentativo / Confirmado en asignaciones** — principal hueco funcional de Capacity. Posible `ToDo.pmo_commitment` (Tentativo/Confirmado) o diseño equivalente. **No** asumir aún el Custom Field: la forma se decide en la revisión global. | **Nuevo — sin issue.** Registrado aquí (opción "C" de la auditoría v0.11.0) | Auditoría v0.11.0; excluido explícitamente en ADR-0010 (Fuera de alcance) |
| 2 | **Reservas de capacidad** | **Registrado:** GitHub issue **#10** (`feat: reservas de capacidad (diferido)`, open) | ADR-0003 / auditoría capacity |
| 3 | **CPM / ruta crítica** | **Registrado:** GitHub issue **#9** (`feat: CPM / ruta crítica (diferido)`, open) | ADR-0006/0009 (forecast de fecha real requiere CPM) |
| 4 | **Constraints tipados de cronograma** — SNET, FNLT, MSO, MFO. Diferidos hasta que exista necesidad real. | **Nuevo — sin issue.** Registrado aquí | ADR-0007 (Fuera de alcance) |
| 5 | **UX de `pmo_planned_hours` por asignado** — el **cálculo** actual es correcto (ADR-0003 D3); la **captura** es friccionada porque exige editar el ToDo. **No** modificar por ahora el diálogo nativo "Assign To"; queda pendiente evaluar una UX segura. | **Nuevo — sin issue.** Registrado aquí | ADR-0003 (limitación documentada); auditoría v0.11.0 |
| 6 | **UX de captura/mantenimiento de `PMO Capacity`** — el modelo efectivo-datado ya funciona; queda pendiente mejorar captura masiva/calendario o una alternativa equivalente. | **Nuevo — sin issue.** Registrado aquí | Auditoría v0.11.0 (hueco #3 → v0.11.0 solo da **visibilidad** de la carencia, no captura) |

## Revisión global de producto (posterior a v0.11.0)

- v0.11.0 (ADR-0010, A+B) es el **cierre** de la ronda funcional actual.
- Después de liberarlo: **revisar el producto completo** y **priorizar este backlog** antes de reanudar
  desarrollo. No arrancar otro ciclo funcional de forma automática.
- Entradas a considerar en esa revisión: los 6 pendientes de arriba (decidir forma de #1; evaluar #9/#10;
  necesidad real de #4; ROI de #5 y #6).

## Notas

- Los ítems **1, 4, 5 y 6** aún **no** tienen GitHub issue propio (viven aquí y en el "Fuera de alcance" de
  su ADR). Si en la revisión global se decide promoverlos a issues para seguimiento formal (paridad con
  #9/#10), hacerlo entonces — evitando duplicar este registro.
- Este documento es el **índice único** del backlog diferido; los ADR mantienen el detalle de *por qué* se
  difirió cada uno.
