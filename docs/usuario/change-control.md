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
- **Crear la addenda comercial:** además de poder editar el CR, exige **autoría comercial** (rol
  *Proposals Manager*). Es una autoridad distinta de la de gobierno del CR: quien gobierna el cambio no
  necesariamente puede emitir la addenda, y viceversa.
- **Acceso ejecutivo:** solo lectura.

## Flujo (estados)

`Borrador → En revisión → Aprobado / Rechazado → Implementado → Cerrado`

1. **Borrador:** el owner o un miembro crea el CR, describe el cambio y su impacto.
2. **Crear addenda comercial** (opcional, si el cambio tiene alcance comercial): mientras el CR es
   **editable** (Borrador / En revisión) y aún no tiene addenda, el botón *"Crear addenda comercial"* genera
   una **Cotización/Addenda** del contrato original (una versión comercial nueva `…-ADD-01`, `…-ADD-02`, …)
   sin tocar el contrato base. La addenda nace **en borrador** para negociarse aparte. **Requiere autoría
   comercial** (rol *Proposals Manager*): un miembro sin ese rol no puede crearla, aunque pueda editar el CR.
   Crear la addenda **no** aplica nada todavía.
3. **Enviar a revisión:** requiere que el Project tenga una **baseline vigente**; al formalizar se
   **congela** la baseline previa (*before*). Sin baseline vigente el sistema no deja avanzar (aún estás en
   planificación, no en control de cambios).
4. **Aprobar / Rechazar:** **solo el Project Owner**. Aprobar autoriza el cambio (no lo aplica todavía).
5. **Aplicar Cotización al Project** (si el cambio tiene alcance comercial): el owner usa el botón
   *"Aplicar Cotización al Project"*, elige la Cotización **Ganada** y el sistema **anexa** su alcance
   (Scope Items) como tareas al **Project existente** (nunca crea otro). Esto **materializa** el alcance,
   pero todavía no marca el cambio como implementado. **Ganada ≠ Aplicada:** que la cotización se gane no
   la aplica sola; la aplicación es un acto explícito del owner desde el CR.
6. **Marcar implementado:** cuando el plan quedó completo (tareas, fechas, asignaciones ajustadas), el
   owner lo marca. Si el cambio tenía Cotización, exige haberla aplicado primero.
7. **Cerrar:** el owner liga la **nueva baseline** (*after*) que incorpora el cambio y cierra el CR.

Un CR **Rechazado** o **Cerrado** es terminal (no se cancela); un nuevo intento es otro CR.

## ¿Qué cambió entre líneas base?

Cuando el CR tiene ligadas la línea base previa y la resultante, el botón **"Comparar líneas base"** abre
el reporte **PMO Baseline Comparison** a **pantalla completa** (no un cuadro emergente): tareas
añadidas/eliminadas y cambios de fechas, horas, estructura, estado y asignaciones, más cambios de fechas
del Proyecto, con una columna de **Variación** (±días / ±horas) y un **resumen** arriba. Muestra **solo las
diferencias**.

Es una **comparación entre líneas base**: si varias solicitudes de cambio se consolidaron en la misma línea
base resultante, muestra **todo** lo que cambió entre esas dos fotos, no solo lo de un CR. Cuando lo abres
desde un CR, ese CR aparece como **contexto de apertura**, no como “origen” del diff.

Para cambios grandes es una tabla completa que puedes **filtrar, ordenar y exportar** (Excel/CSV) o
**imprimir/guardar como PDF** con las acciones nativas del reporte. No se guarda ni adjunta un artefacto
derivado: las líneas base ya son inmutables y la comparación es reproducible.

**Ligar la Línea base resultante:** el owner la elige explícitamente (no se pone sola). El selector ya
filtra a líneas base del mismo Proyecto, posteriores a la previa; y el botón **"Usar línea base vigente"**
la prellena como atajo, sin impedir escoger otra.

## Registro de cambios (Change Register)

El reporte **PMO Change Register** es la vista de operación de todos los Change Requests. Muestra, por cada
CR: Project, número, título, estado, fecha, prioridad, tipos de impacto, horas/días/monto estimados,
grupo de propuesta y Cotización aplicada, y las baselines *before/after*. Viene ordenado por fecha (más
reciente primero) y luego por prioridad; puedes filtrar y ordenar por cualquier columna, y guardar tus
propias vistas.

**Solo ves los cambios de proyectos que puedes ver** (misma regla de privacidad): el registro no expone
CRs de proyectos ajenos. El acceso ejecutivo ve todos; `PMO Manager` no accede.

## Relación con los demás documentos

| Documento | Rol en el cambio |
|---|---|
| **PMO Change Request** | Gobierna el cambio: motivo, impacto, decisión, implementación. |
| **Cotización / Proposal** | Define y valúa el alcance (Scope Items, horas, entregables, precio) y su propia aprobación. |
| **Project / Tasks** | Recibe el alcance aprobado (el Current Plan). |
| **PMO Project Baseline** | Congela la referencia antes/después del cambio. |
| **Timesheet** | Registra el trabajo real. |
