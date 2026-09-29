# Cierre y Revisión posterior

Dos controles finales del Ciclo de Gobernanza, con propósitos distintos:

- **Cierre** (`PMO Project Closure`) = **cómo terminó** el proyecto (factual, al cerrar).
- **Revisión posterior** (`PMO Post-Project Review`) = **qué aprendimos** (después del cierre).

Ambos son **submittable**: al emitir, toda su evidencia queda **congelada** (snapshot + hash) y no se
reconstruye después desde datos vivos.

---

## Cierre (PMO Project Closure)

Deja constancia formal de cómo cerró el proyecto. Se crea desde el **Project → pestaña PMO → Ciclo de
Gobernanza → Cierre**.

### Cuándo se puede emitir
- El Project debe estar en un estado **terminal**: **Completed** o **Cancelled**. Un proyecto aún en
  ejecución **no** puede cerrarse.
- Si el Project está **Completed**, exige **aceptación formal** (aceptado por / fecha de aceptación).
- **No** se puede cerrar si el proyecto tiene **Solicitudes de cambio abiertas** (Draft / In Review /
  Approved / Implemented). Se usa la misma fuente de gobierno; no hay un check manual que lo duplique.

### Qué se captura
- **Fecha de cierre** (obligatoria; no futura).
- **Resultado final** y, cuando aplica, **Aceptado por / Aceptado el** (la fecha de aceptación no puede ser
  posterior a la de cierre).
- **Pendientes transferidos** y **observaciones de cierre**.
- **Checklist de cierre (7 confirmaciones)**, todas obligatorias — cada una confirma *"revisado y sin acción
  de cierre pendiente"*:
  1. pendientes resueltos/transferidos
  2. entrega a operación/soporte
  3. obligaciones contractuales/legales revisadas
  4. cierre administrativo/financiero revisado
  5. documentación completa
  6. cierre comunicado a interesados
  7. recursos liberados/reasignados

### Qué congela al emitir
Al emitir, el Cierre **compone** desde el control del proyecto (a la fecha de cierre) la evidencia de
cronograma/esfuerzo/cambios y la congela; también congela el checklist, la aceptación, el resultado y las
observaciones. La **evidencia económica** se guarda en un campo restringido (solo visible para roles con
acceso económico) y refleja el estado **al momento de emitir** (la economía nativa no tiene histórico).

El **formato imprimible** del Cierre se reconstruye **solo** desde esos datos congelados: cambios posteriores
en el Project no alteran cómo "cerró".

---

## Revisión posterior (PMO Post-Project Review)

Registra el aprendizaje del proyecto, **después** del cierre. Se crea desde el **Project → pestaña PMO →
Ciclo de Gobernanza → Revisión posterior** (disponible una vez emitido el Cierre).

### Qué se captura
- **Objetivos logrados**, **qué funcionó**, **qué no funcionó**, **causas** y **recomendaciones**.
- **Lecciones aprendidas** (tabla): por cada lección, su **área** (planeación, ejecución, control de cambios,
  recursos, costo, gobernanza), la **lección** y la **acción recomendada**.
  - Si una lección tiene acción recomendada, exige **responsable** y **fecha objetivo**; al emitir la
    Revisión, se genera un **ToDo** nativo para darle seguimiento.

### Mejora continua (separada del ciclo)
Las acciones de las lecciones aprendidas pertenecen a **Mejora continua**, una capacidad **separada** de la
gobernanza del ciclo:
- **No** forman parte de las Acciones de Gobernanza pendientes ni re-marcan el proyecto como pendiente.
- Su estado vive en el ToDo (Open/Closed/Cancelled).
- Se siguen desde el Workspace (lista "Acciones de mejora continua") y el reporte **PMO Continuous
  Improvement**.

Al emitir la Revisión, el snapshot congela el responsable y la fecha objetivo de cada acción (no el estado
posterior del ToDo).

---

## Estado del ciclo (derivado)

El estado de ciclo de vida del Project (Initiation · Planning · Execution/Control · Closing · Closed ·
Post-project reviewed) se **deriva** de los hechos (estado del Project + existencia de Acta/Línea base/Cierre/
Revisión). **No** es un workflow ni un estado editable sobre el Project.
