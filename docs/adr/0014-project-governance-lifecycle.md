# ADR-0014: Project Governance & Lifecycle Documentation

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Depende de:** ADR-0002 (P4),
ADR-0004 (Baseline), ADR-0005 (Change Control), ADR-0011 (Project Control canónico) · **No toca:** PHI
(ADR-0013, bloqueado).

> **Alcance:** **Risk Analysis queda FUERA del alcance de esta implementación** y se abordará
> **posteriormente**, como iniciativa adicional, una vez terminado Project Governance & Lifecycle
> Documentation (ver D6). Ningún artefacto de este ADR depende de Risk ni lo condiciona.

## Contexto
`pmo` cubre planeación, capacidad, baselines, control, cambios, economía y reporting, pero **falta el gobierno
documental del ciclo de vida**: transferencia formal del Project a ejecución (Handoff), cierre formal (Closure)
y evaluación posterior (Post-Project Review). La auditoría confirma que Baseline (`PMO Project Baseline`, submittable +
snapshot + hash + lineage) y Change Control (`PMO Change Request`, workflow + aprobación +
baseline_before/after) resuelven sus dominios. Objetivo: **completar el ciclo reutilizando lo existente**, sin
sistemas paralelos.

Ciclo objetivo: `Proposal ganada → Project + WBS inicial → Handoff → Baseline → Status/Control → Change
Control → Closure → Post-Project Review → Lessons Learned`.

## Problema
El arranque y el cierre no dejan evidencia congelada; el expediente del Project está disperso. El peligro es de
**implementación** (motores/aprobaciones/baselines/status paralelos, workflows nuevos), no de concepto.

## Decisiones

### D1 — Project nativo es el objeto central; no existe `PMO Project`
Todos los artefactos enlazan al `Project` de ERPNext. Prohibido duplicar customer/company/fechas/Tasks/WBS/
costos/ventas/horas/datos de Proposal: se **referencian** canónicamente.

### D2 — Tres artefactos persistentes principales; el resto se deriva/genera
Artefactos de gobierno (todos submittable, evidencia congelada al emitir): **Handoff**, **Closure**,
**Post-Project Review**. **No** se fija un conteo total de DocTypes: los **child DocTypes de soporte** (p. ej.
`PMO Lessons Learned`, o un child para el snapshot de un Handoff/Closure si no se guarda como JSON) son
**detalle de implementación, no una restricción arquitectónica**. Derivado/generado (sin artefacto propio):
estado de ciclo de vida, índice de expediente, cuerpo del Closure (Print Format), señales de dashboard.

### D3 — Handoff mínimo (transferencia formal a ejecución); **autosuficiente**
`PMO Project Handoff` (reemplaza al anterior Charter) existe **únicamente** para dejar evidencia formal de la
**transferencia del Project hacia ejecución** y marcar el hito de gobierno **"handoff completado"** (Handoff
submitted = arranque completado). Flujo: `Proposal ganada → Project + WBS inicial → Project Handoff →
Baseline`. **No** recaptura planeación: la Proposal ganada ya representa la autorización comercial, el Project
el trabajo operativo y el Baseline el plan autorizado. Es un **acta corta**, no otro formulario de planeación.
El Handoff **no contiene estructura de Risk Analysis** y no depende de ningún registro de riesgos.
- **Capturado (mínimo):** `handoff_date`, `project_manager` (única fuente hoy en el modelo) y `handoff_summary`
  (obligatorio: qué se transfiere al equipo de ejecución — contexto, acuerdos de arranque, pendientes,
  dependencias y consideraciones operativas).
- **Se toma del Project y se congela al submit:** `pmo_operational_owner` (responsable operativo interno, Link
  Employee) y `pmo_customer_contact` (contacto principal del cliente, Link Contact) — ambos custom fields del
  Project; cambios posteriores en el Project no alteran un Handoff ya emitido. **Ambos son obligatorios para
  emitir** (guard en `before_submit`): sin ellos no hay transferencia formal. La `handoff_date` también es
  obligatoria.
- **Derivado + snapshot al submit** (patrón `snapshot`+`snapshot_hash` del Baseline): customer/company,
  `pmo_committed_end_date`, referencia a Proposal/Quotation, hitos/equipo iniciales.
- **Sin economía en el snapshot (política P4):** el Handoff **no** guarda economía autorizada. La economía está
  sujeta a `can_see_project_economics` (permlevel 1, D4); persistirla en un snapshot legible por cualquiera con
  READ del Project/Handoff la filtraría. La economía vive en su frontera canónica y en el Closure (permlevel 1).
- **NO se reintroducen** objetivo, alcance, entregables, supuestos ni restricciones como captura del usuario.
- Submittable → evidencia histórica inmutable del arranque; snapshot/hash/timestamps quedan en sección técnica
  read-only, fuera de la captura normal.

### D4 — Closure: toda la evidencia se congela al submit (snapshot-only)
- **Capturado:** `final_result`, aceptación formal (`accepted_by`, `accepted_on`), `pending_items_transferred`,
  `closure_observations`.
- **Guard de cierre:** el Closure solo se emite (submit) para un Project en estado **terminal** (`Completed` o
  `Cancelled`); un Project no terminal rechaza el submit. Coherente con el estado de ciclo derivado (D7).
- **Congelación al submit:** el Closure **compone desde `build_project_control`** (cutoff = `closure_date`) la
  evidencia **no económica** (cronograma/esfuerzo/cambios) y la congela en `snapshot` con hash; **no recalcula
  ni reimplementa** esos dominios.
- **Semántica temporal (explícita):** cronograma y esfuerzo son **al corte `closure_date`** (vía
  `build_status_report`). La **economía nativa no tiene snapshot histórico** (la sección `costs` es
  `as_of:"current"`, ADR-0012), por lo que la evidencia económica se congela como **`current_at_issuance`**
  (estado al momento de emitir) y **nunca** se etiqueta como histórica a `closure_date`. La economía se toma de
  la **frontera canónica** (`get_authorized_economics` + totales nativos), no de una segunda implementación.
- **Aislamiento económico (P4):** la evidencia económica se guarda en un campo **`economics_snapshot` con
  `permlevel 1`**, legible solo por los roles económicos (los de `can_see_project_economics`). Un usuario con
  READ del Project pero **sin** permiso económico **no** puede leerla. No se debilita P4 ni se crea una segunda
  política.
- **El Print Format se reconstruye SOLO desde los snapshots congelados**, nunca desde datos vivos, y respeta
  el gate económico. Flujo: `build_project_control → snapshot al submit → Closure congelado → Print Format`.
  Cambios posteriores en el Project **no** alteran cómo "cerró". No inventa métricas.

### D5 — Post-Project Review mínimo (ISO 21513; proporcional)
Distinto del Closure (Closure = *cómo terminó*, factual; Review = *qué aprendimos*, posterior). Capturado:
`objectives_achieved`, `what_worked`, `what_didnt`, `causes`, `recommendations` + **child `PMO Lessons
Learned`** (`area` ∈ {planning, execution, change_control, resources, cost, governance}, `lesson`,
`recommended_action`). Solo la child se estructura (reporting futuro). Puede consultar información viva/
histórica **mientras se prepara**; **al submit queda congelado** (D11). Sin cuestionario extenso.

### D6 — Risk Analysis: diferido (fuera de alcance de esta implementación)
Risk Analysis queda **diferido hasta terminar esta iniciativa**. Su diseño e integración con Handoff,
Status/Control, Change Control, Closure y Post-Project Review se **decidirán posteriormente**. **No condiciona
ni forma parte** de los bloques actuales de Project Governance & Lifecycle Documentation. En esta
implementación **no se crea ningún artefacto de riesgo** (ni `PMO Project Risk`, ni child de riesgos iniciales
en el Handoff) ni se añaden referencias de riesgo a Closure/Review/Dashboard/Project Control.

### D7 — Estado de ciclo de vida derivado, no workflow
Función pura (`pmo/governance.py`, patrón `health.py`) que deriva un estado documental desde hechos
(Project.status + existencia/submit de Handoff/Baseline/Closure/Review): `Initiation · Planning ·
Execution/Control · Closing · Closed · Post-project reviewed`. **No** hay workflow ni estado paralelo sobre
Project.

### D8 — Integración en Project Control: índice de expediente
Sección en `build_project_control`: Handoff · Baseline vigente · Status/Control · Change Requests · Closure ·
Post-Project Review, con **enlaces + existencia + fechas**, sin duplicar contenido de otras vistas. (La entrada
de Risks se añadirá cuando se implemente la capacidad de Risk, D6.)

### D9 — Dashboard PMO (sin nuevo dashboard, sin maturity score)
Extender las filas de portafolio existentes (ya con `has_baseline`) con señales de gobierno; una sección
"Project Governance" reusando `_build`. Las señales se **centralizan en `pmo/governance.py`** (fuente única)
y Portfolio/Dashboard las **consumen** (no se duplican reglas por superficie). Semántica canónica, alineada
con D4/D7:
- `has_handoff` = existe Handoff **submitted** (hito de arranque completado);
- `needs_baseline` = `has_handoff` **y** no existe línea base vigente/submitted (siguiente acción del
  arranque: Proposal ganada → Project → Handoff → **Baseline**);
- `needs_closure` = `Project.status ∈ {Completed, Cancelled}` **y** no existe Closure submitted (mismos
  estados terminales de D4/D7 — no solo `Completed`);
- `needs_review` = existe Closure submitted **y** no existe Review submitted;
- `open_change_requests` = Change Requests en estados abiertos canónicos (`Draft`, `In Review`).

**Pending Governance Actions** (Custom HTML Block "PMO Governance") es una **lista de trabajo**: 6 indicadores
(Sin Handoff · Sin línea base · Solicitudes de cambio abiertas · Requieren cierre · Requieren revisión ·
Análisis de riesgo —reserva de UX, sin lógica—) y filas por Project con **acciones en lenguaje humano**
(*Crear Handoff · Crear línea base inicial · Atender N solicitud(es) de cambio · Emitir cierre · Realizar
revisión post-proyecto*), derivadas server-side de las señales. **No** se exponen claves internas de lifecycle
(`initiation/planning/execution_control`) al usuario. Las acciones se construyen en `_governance_actions`
(dashboard) consumiendo `governance_flags` (fuente única), sin duplicar reglas en JS.

(Señales de riesgo se añadirán con la capacidad de Risk, D6; hoy el indicador de riesgo es solo reserva de UX.)

### D10 — P4 reutilizado (sin segunda política)
Los artefactos heredan la visibilidad del Project vía `pmo.permissions` (`permission_query_conditions` +
`has_permission`), como Baseline/Change Request. Roles: creación/edición por rol PMO operativo;
emisión/aprobación (submit) por rol de gobierno; lectura según P4 + `PMO Executive Access`. El detalle de roles
por DocType se fija en su bloque.

### D11 — Evidencia e historial
Handoff/Closure/Review: **submittable** + `track_changes` + **snapshot con hash** (patrón Baseline) +
**referencias canónicas**. **Toda** su evidencia se congela al submit; ninguno se reconstruye desde datos
vivos posteriormente. No se copian bloques grandes de datos referenciables.

### D12 — Desacople del PHI
Governance expone señales **canónicas y consultables**, pero **no** se crean hooks del PHI ahora. El PHI sigue
**bloqueado** (ADR-0013); estas señales alimentarán su **auditoría final de señales** en su momento.

### D13 — Listo para reporting, sin KPIs ahora
El modelo debe **permitir** después (% con Handoff, sin baseline, Completed sin Closure, tiempo de cierre, sin
Review, categorías de lessons, causas recurrentes) **sin implementar** esos KPIs en esta capacidad; solo no
impedirlos.

## Fuera de alcance
**Risk Analysis (toda la capa: `PMO Project Risk`, riesgos iniciales del Handoff, señales de riesgo en
Closure/Review/Dashboard/Project Control) — diferido a una iniciativa posterior (D6).** `PMO Project`; segundo
change-control/baseline/status-reporting; workflow de ciclo de vida; masters de categorías; review-template
engine; KPIs de reporting; cualquier cambio al PHI.

## Consecuencias
- Ciclo de gobierno documental completo (Handoff → Closure → Review) reutilizando Baseline/Change Control/
  Project Control/economía/P4.
- Evidencia **congelada e íntegra** de arranque y cierre (Closure inmune a cambios posteriores del Project);
  expediente indexado.
- Tres artefactos persistentes + child de soporte + funciones derivadas: superficie proporcional, sin
  subsistemas. Risk se incorpora limpiamente después sin haber condicionado estos bloques.
- **Residuo de BD pendiente:** al reemplazar `PMO Project Charter` por `PMO Project Handoff`, `bench migrate`
  eliminó la **metadata** del DocType Charter (huérfano) pero **no** dropeó la tabla física vacía
  `tabPMO Project Charter` (Frappe no dropea tablas en migrate). Queda **registrada como residuo** para la
  **reconciliación final de BD al cerrar Governance**; sin impacto funcional (sin metadata ni referencias).

## Alternativas descartadas
- **Métricas propias/editables en Closure** → duplicación/drift; se rechaza (D4 snapshot-only).
- **Print Format del Closure desde datos vivos** → alteraría retrospectivamente el cierre; se rechaza (D4).
- **Implementar Risk primero / Handoff dependiente de un registro de riesgos** → invierte la prioridad de la
  iniciativa y obliga a construir un sistema de riesgos antes del arranque; se rechaza. Risk queda diferido
  (D6) y el Handoff es autosuficiente (D3).
- **Mantener el Charter como acta de planeación (objetivo/alcance/entregables/supuestos/restricciones)** → la
  prueba funcional demostró que genera recaptura administrativa y duplica Proposal/Project/Baseline; se rechaza
  en favor de un Handoff mínimo de transferencia (D3).
- **Workflow de ciclo de vida en Project** → status paralelo; se rechaza (D7 derivado).

## Criterios de aceptación
- Existen **3 artefactos persistentes principales** (Handoff/Closure/Review submittable); los child DocTypes de
  soporte no cuentan como restricción; el resto es derivado/snapshot/Print Format/sección.
- **Ningún artefacto ni referencia de riesgo** se implementa en esta capacidad (D6/Fuera de alcance).
- El Handoff es **autosuficiente** (no depende de riesgos ni de otro artefacto para emitirse) y **no** recaptura
  objetivo/alcance/entregables/supuestos/restricciones.
- Handoff, Closure y Review congelan **toda** su evidencia por snapshot+hash al submit; el Print Format del
  Closure se reconstruye **solo** desde su snapshot, nunca desde datos vivos.
- Estado de ciclo de vida es función derivada; no hay workflow nuevo en Project.
- P4 heredado vía `pmo.permissions`; sin segunda política.
- El PHI no se toca; las señales quedan consultables para su auditoría posterior.

## Secuencia de implementación (bloques posteriores)
BLOQUE 2 **Project Handoff** (autosuficiente) → BLOQUE 3 **estado de ciclo de vida derivado + índice de
expediente** → BLOQUE 4 **Closure** (snapshot-only + Print Format) → BLOQUE 5 **Post-Project Review** +
Lessons Learned → BLOQUE 6 **Dashboard Governance**. Cada bloque: diseño → implementar → validar → presentar →
esperar autorización de commit. **Risk Analysis** se aborda como iniciativa posterior (D6), fuera de esta
secuencia.
