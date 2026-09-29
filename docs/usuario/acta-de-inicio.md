# Acta de Inicio (PMO Project Handoff)

El **Acta de Inicio** (DocType `PMO Project Handoff`) formaliza el arranque de un proyecto: deja evidencia de
la **transferencia a ejecución**, del **compromiso inicial**, de la **readiness contractual/legal** y de la
**autorización explícita para iniciar**. Es el primer control del Ciclo de Gobernanza
(Acta → Línea base → Riesgos → Cambios → Cierre → Revisión posterior).

No es un formulario de planeación completo: captura objetivo y alcance **de alto nivel**, no el WBS ni el
detalle que ya viven en la Propuesta / Project / Línea base.

## Dónde se crea

Desde el **Project → pestaña PMO → Ciclo de Gobernanza → Acta → Crear**.

> **Requisito previo:** el Project debe tener definido el **Project Manager** (campo *Project Manager /
> Responsable del proyecto* en la pestaña PMO). Si falta, el sistema no deja crear el Acta y avisa:
> *"Define el Project Manager antes de crear el Acta de inicio"*. Además, el Project debe tener un **Customer**
> asignado (necesario para elegir el Contacto principal del cliente).

## Qué se captura

**Encabezado**
- **Proyecto** y **Fecha de handoff** (obligatoria).
- **Project Manager**: se toma del Project (`pmo_project_manager`) y es **de solo lectura** aquí — la fuente
  única es el Project. Se congela como evidencia; no se modifica desde el Acta.
- **Fin comprometido** (obligatorio): la fecha comprometida de terminación **autorizada**. Es la **fuente
  formal del compromiso inicial**: al emitir se copia al Project.

**Responsables**
- **Responsable operativo interno** (Employee) y **Contacto principal del cliente** (Contact): se **capturan
  aquí, en el Acta**. El selector de contacto muestra **solo contactos del Customer del Project** (relación
  nativa Contacto↔Customer). Al emitir, ambos se copian al Project.

**Objetivo y alcance**
- **Objetivo del proyecto** y **Alcance de alto nivel** (ambos obligatorios; texto breve, no WBS).

**Transferencia a ejecución** (todos obligatorios para emitir)
- **Resumen de handoff**: qué se transfiere (contexto, acuerdos de arranque, pendientes, dependencias).
- ☐ **PM informado y transferencia coordinada**
- ☐ **Equipo interno necesario informado**
- ☐ **Condiciones de arranque y pendientes revisados**
- ☐ **Readiness contractual/legal verificada** (no es aprobación jurídica ni captura de contratos)

**Autorización** (obligatorio)
- **Autorizado por**: nombre y cargo/rol de la persona que autorizó el inicio. Puede ser interna o externa
  (cliente, sponsor, dirección u otra autoridad). Es texto libre; no crea un registro de stakeholders.
- ☐ **Autorización explícita para iniciar obtenida**: confirma que esa persona otorgó explícitamente su
  autorización y que se comunicó al Project Manager.

## Al emitir (Submit)

El Acta es **submittable**: al emitirla queda como **evidencia histórica inmutable** (snapshot canónico +
hash). El sistema valida server-side que estén completos objetivo, alcance, fin comprometido, los cuatro
checks de coordinación/readiness, quién autorizó y la confirmación de autorización; y que el contacto siga
relacionado con el Customer del Project. Si falta algo, **no deja emitir** con un mensaje claro.

Al emitir con éxito, el Acta **sincroniza al Project**:
- `Fin comprometido` → `Project.pmo_committed_end_date`
- `Responsable operativo interno` → `Project.pmo_operational_owner`
- `Contacto principal del cliente` → `Project.pmo_customer_contact`

El Acta conserva su **copia congelada** de todos estos datos: cambios posteriores en el Project no alteran un
Acta ya emitida. Solo hay **un Acta emitida por Project**.

## Qué NO hace

- No recaptura entregables, supuestos, restricciones ni el WBS (viven en Propuesta/Project/Línea base).
- No aprueba jurídicamente nada ni captura contratos; la readiness es una confirmación, no un flujo legal.
- No crea un modelo de stakeholders ni un workflow de aprobación/firma.
- No guarda economía autorizada (política de confidencialidad económica).

## Relación con los demás documentos

| Documento | Rol |
|---|---|
| **Acta de Inicio (Handoff)** | Formaliza arranque, compromiso inicial y autorización de inicio. |
| **Project** | Recibe el compromiso, el responsable operativo y el contacto (sincronizados al emitir). |
| **PMO Project Baseline** | Congela el plan comprometido de referencia (siguiente control tras el Acta). |
| **Fin comprometido** | Se establece con el Acta; después solo cambia por la acción gobernada (ver `fechas-comprometidas.md`). |
