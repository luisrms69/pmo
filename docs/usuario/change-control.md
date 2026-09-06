# Control de cambios (PMO Change Request)

Un **PMO Change Request (CR)** es el documento que **gobierna un cambio** de un proyecto en ejecución:
por qué se pide, qué impacto se prevé, quién lo decide y cómo se implementa. **No** define el alcance ni
su precio (eso vive en la Cotización/Proposal), **no** ejecuta el trabajo (eso son las Tasks del Project) y
**no** congela el plan (eso es la Baseline). El CR es la **capa de gobernanza** que conecta todo.

> **Estado (v0.6.0 en construcción):** disponibles el documento, sus permisos y el **flujo de aprobación
> (Workflow) con la acción "Aplicar Cotización al Project"**. La comparación de baselines y el registro de
> cambios se habilitan en las siguientes entregas del mismo release. La ruta comercial (aplicar una
> Cotización) requiere además la versión compatible de `erpnext_proposals` (ver nota al final).

## Qué captura

- **Solicitud:** Project, título, quién lo levanta, origen (Cliente/Interno/Regulatorio/Otro), fecha y
  **prioridad** (Baja/Media/Alta).
- **Motivo** y **descripción** del cambio.
- **Impacto (mínimo):** qué dimensiones toca — **Alcance / Cronograma / Esfuerzo-Recursos / Comercial /
  Riesgo** — más estimaciones **opcionales** de horas, días y monto, y notas de evaluación técnica. Las
  estimaciones son **orientativas**: la valuación formal la da la Cotización.
- **Cotización (Proposal):** el grupo de propuesta relacionado y, cuando se aplique, la versión Ganada.
- **Baselines:** la baseline vigente al formalizar (before) y la nueva baseline que incorpora el cambio
  (after).
- **Decisión e implementación:** quién aprobó y cuándo, y el estado de aplicación.

La **discusión** del cambio se hace con los **comentarios** nativos del documento (quedan con autor y
fecha); la evidencia adicional, con **adjuntos**.

## Quién puede hacer qué

El acceso se **hereda del Project** (misma regla de privacidad que el resto de PMO):

- **Ver:** quien pueda ver el Project (owner, miembros del Project y acceso ejecutivo).
- **Crear / editar (mientras es borrador):** el **owner** del Project y sus **miembros**. Los miembros
  pueden levantar, documentar y evaluar el cambio.
- **Aprobar / rechazar / cerrar:** **solo el Project Owner**. Ser miembro no otorga autoridad de
  aprobación.
- **Acceso ejecutivo:** solo lectura.

## Flujo (estados)

`Borrador → En revisión → Aprobado / Rechazado → Implementado → Cerrado`

1. **Borrador:** el owner o un miembro crea el CR, describe el cambio y su impacto.
2. **Enviar a revisión:** requiere que el Project tenga una **baseline vigente**; al formalizar se
   **congela** la baseline previa (*before*). Sin baseline vigente el sistema no deja avanzar (aún estás en
   planificación, no en control de cambios).
3. **Aprobar / Rechazar:** **solo el Project Owner**. Aprobar autoriza el cambio (no lo aplica todavía).
4. **Aplicar Cotización al Project** (si el cambio tiene alcance comercial): el owner usa el botón
   *"Aplicar Cotización al Project"*, elige la Cotización **Ganada** y el sistema **anexa** su alcance
   (Scope Items) como tareas al **Project existente** (nunca crea otro). Esto **materializa** el alcance,
   pero todavía no marca el cambio como implementado.
5. **Marcar implementado:** cuando el plan quedó completo (tareas, fechas, asignaciones ajustadas), el
   owner lo marca. Si el cambio tenía Cotización, exige haberla aplicado primero.
6. **Cerrar:** el owner liga la **nueva baseline** (*after*) que incorpora el cambio y cierra el CR.

Un CR **Rechazado** o **Cerrado** es terminal (no se cancela); un nuevo intento es otro CR.

## Relación con los demás documentos

| Documento | Rol en el cambio |
|---|---|
| **PMO Change Request** | Gobierna el cambio: motivo, impacto, decisión, implementación. |
| **Cotización / Proposal** | Define y valúa el alcance (Scope Items, horas, entregables, precio) y su propia aprobación. |
| **Project / Tasks** | Recibe el alcance aprobado (el Current Plan). |
| **PMO Project Baseline** | Congela la referencia antes/después del cambio. |
| **Timesheet** | Registra el trabajo real. |
