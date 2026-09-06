# Control de cambios (PMO Change Request)

Un **PMO Change Request (CR)** es el documento que **gobierna un cambio** de un proyecto en ejecución:
por qué se pide, qué impacto se prevé, quién lo decide y cómo se implementa. **No** define el alcance ni
su precio (eso vive en la Cotización/Proposal), **no** ejecuta el trabajo (eso son las Tasks del Project) y
**no** congela el plan (eso es la Baseline). El CR es la **capa de gobernanza** que conecta todo.

> **Estado (v0.6.0 en construcción):** por ahora está disponible el **documento y sus permisos**. El flujo
> completo (estados de aprobación, "Aplicar Cotización al Project", comparación de baselines y el registro
> de cambios) se habilita en las siguientes entregas del mismo release.

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

## Relación con los demás documentos

| Documento | Rol en el cambio |
|---|---|
| **PMO Change Request** | Gobierna el cambio: motivo, impacto, decisión, implementación. |
| **Cotización / Proposal** | Define y valúa el alcance (Scope Items, horas, entregables, precio) y su propia aprobación. |
| **Project / Tasks** | Recibe el alcance aprobado (el Current Plan). |
| **PMO Project Baseline** | Congela la referencia antes/después del cambio. |
| **Timesheet** | Registra el trabajo real. |
