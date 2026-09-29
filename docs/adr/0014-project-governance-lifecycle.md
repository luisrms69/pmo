# ADR-0014: Project Governance & Lifecycle Documentation

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted (implementado) · **Depende de:** ADR-0002 (P4),
ADR-0004 (Baseline), ADR-0005 (Change Control), ADR-0011 (Project Control canónico) · **No toca:** PHI
(ADR-0013, bloqueado).

> **Alcance:** Risk Analysis quedó FUERA del alcance de esta implementación (se difirió aquí). **Enmienda
> (2026-09-25):** Risk Analysis fue implementado —ligero— como iniciativa posterior en **ADR-0016**; ver D6
> enmendado. Ningún artefacto de este ADR depende de Risk ni lo condiciona.

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

### D3 — Handoff = Acta de Inicio / Charter (transferencia + autorización formal a ejecución); **autosuficiente**

> **Enmienda (Charter + Autorización, 2026-09).** El Handoff evolucionó de "acta corta de transferencia" a
> **Acta de Inicio / Charter** con **gate de autorización** y **propiedad de campos Handoff→Project** (snapshot
> schema v2). El texto de este D3 refleja el estado implementado; la redacción original ("acta corta, sin
> recaptura, campos tomados del Project") queda superada por esta enmienda.

`PMO Project Handoff` (reemplaza al anterior Charter) es la **Acta de Inicio / Charter** del proyecto: deja
evidencia formal de la **transferencia a ejecución**, del **compromiso inicial**, de la **readiness
contractual/legal** y de la **autorización explícita para iniciar**, y marca el hito de gobierno "handoff
completado" (Handoff submitted = arranque completado). Flujo: `Proposal ganada → Project + WBS inicial →
Project Handoff → Baseline`. Sigue siendo **autosuficiente** (no depende de riesgos ni de otro artefacto) y
**no** duplica el detalle de WBS/planeación de Proposal/Project: captura objetivo y alcance **de alto nivel**,
no un segundo plan. El Handoff **no contiene estructura de Risk Analysis**.

- **Capturado en el Acta (obligatorio, validado server-side en `before_submit`):**
  - `handoff_date` (obligatoria) y `handoff_summary` (qué se transfiere: contexto, acuerdos de arranque,
    pendientes, dependencias, consideraciones operativas).
  - `project_objective` (Small Text) y `scope_high_level` (Small Text) — **alto nivel, no WBS**.
  - `committed_end_date` ("Fin comprometido", obligatoria): **fuente formal del compromiso inicial**; al emitir
    se copia a `Project.pmo_committed_end_date` (ADR-0007 D6).
  - `operational_owner` (Link Employee) y `customer_contact` (Link Contact) — **capturados en el Acta** (ya no
    se toman del Project). El contacto se filtra por el `Customer` del Project vía la relación **nativa**
    `Contact.links → Dynamic Link` (client `set_query` con `contact_query`; validación server-side contra el
    Customer del Project). **Sin `Customer` en el Project no puede emitirse.**
  - Checks de coordinación de transferencia: `pm_informed_coordinated`, `internal_team_informed`,
    `startup_conditions_reviewed` (todos obligatorios).
  - `contractual_legal_ready` (readiness contractual/legal; obligatorio). No es aprobación jurídica ni captura
    contratos ni Links; no toca `erpnext_proposals`.
  - **Autorización formal:** `authorized_by` (**Data libre** — nombre y cargo/rol de quien autorizó el inicio,
    interno o externo: cliente, sponsor, dirección) + `start_authorization_confirmed` (Check de confirmación
    explícita). Ambos obligatorios. Evidencia de "quién autorizó + confirmación explícita + cuándo se
    formalizó" (`issued_at`).
- **Project Manager — fuente única = `Project.pmo_project_manager`:** `Handoff.project_manager` es **read-only
  `fetch_from project.pmo_project_manager`**, se **sella server-side** en `before_submit`, se congela como
  evidencia y **NO** se sincroniza de vuelta. Si el Project no tiene PM, el **Submit se bloquea**; la UX del
  form de Project impide crear el Acta sin PM (gate preventivo).
- **Sincronización Handoff → Project al emitir (`on_submit`):** `pmo_committed_end_date`, `pmo_operational_owner`
  y `pmo_customer_contact` se escriben al Project (única escritura del Handoff hacia el Project; los tres son
  **read-only** en el Project). El Handoff conserva su copia congelada como evidencia.
- **Derivado + snapshot al submit (schema v2; patrón `canonical_json`+`snapshot_hash` del Baseline):**
  customer/company, referencia a Proposal/Quotation ganada, hitos (`Task.is_milestone`) y equipo inicial
  derivado de las fuentes P4 (owner + DocShare + ToDo). **Toda la evidencia humana capturada entra al `captured`
  del snapshot** (cubierta por el hash): `handoff_date`, `project_manager` (sellado), `handoff_summary`,
  `project_objective`, `scope_high_level`, `committed_end_date`, `operational_owner`, `customer_contact`, los
  tres checks de coordinación, `contractual_legal_ready`, `authorized_by`, `start_authorization_confirmed` y la
  metadata de emisión (`issued_by`/`issued_at`, fijados **antes** de construir el snapshot).
- **Sin economía en el snapshot (política P4):** el Handoff **no** guarda economía autorizada (sujeta a
  `can_see_project_economics`, permlevel 1, D4). La economía vive en su frontera canónica y en el Closure.
- Captura **objetivo** y **alcance de alto nivel** (breves, no WBS); **NO** reintroduce entregables, supuestos
  ni restricciones como captura estructurada (eso vive en Proposal/Project/Baseline).
- Submittable → evidencia histórica inmutable del arranque; snapshot/hash/timestamps quedan en sección técnica
  read-only, fuera de la captura normal.

### D4 — Closure: toda la evidencia se congela al submit (snapshot-only)
- **Capturado:** `final_result`, aceptación formal (`accepted_by`, `accepted_on`), `pending_items_transferred`,
  `closure_observations`. Se elimina `title` (redundante con Project + `PMO-CLS-xxxxx`). `closure_date` es
  **obligatoria**.
- **Closure Checklist (confirmaciones de cierre; sin child DocType ni tabla configurable):** 7 checks canónicos
  —pendientes resueltos/transferidos · entrega a operación/soporte · obligaciones contractuales/legales
  revisadas · cierre administrativo/financiero revisado · documentación completa · cierre comunicado a
  interesados · recursos liberados/reasignados—. Cada uno confirma *"revisado y sin acción de cierre
  pendiente"* (puede confirmarse aunque el caso no requiera una operación compleja). **Todos** obligatorios para
  emitir. No duplican `pending_items_transferred` (detalle) ni acceptance (`accepted_by/on`). **Las 7
  confirmaciones entran al `snapshot` canónico (clave `closure_checklist`) y quedan cubiertas por
  `snapshot_hash`** (evidencia congelada, D11).
- **Guard de cierre:** el Closure solo se emite (submit) para un Project en estado **terminal** (`Completed` o
  `Cancelled`); un Project no terminal rechaza el submit. **`Completed`** exige aceptación formal
  (`accepted_by` + `accepted_on`). **Guard automático de Change Requests abiertos:** no se puede cerrar si el
  Project tiene CR **abiertos**. Un CR está abierto ⇔ `workflow_state ∈ {Draft, In Review, Approved,
  Implemented}` **y** `docstatus != 2` (**un CR cancelado nunca cuenta como abierto**); Rejected/Closed no
  bloquean. Se consume la fuente única de Governance (`count_open_change_requests`); no se duplica la lista ni
  se añade un check manual. Coherente con el estado de ciclo derivado (D7).
- **Congelación al submit:** el Closure **compone desde `build_project_control`** (cutoff = `closure_date`) la
  evidencia **no económica** (cronograma/esfuerzo/cambios) y la congela en `snapshot` con hash; **no recalcula
  ni reimplementa** esos dominios.
- **Toda la evidencia humana capturada entra al `snapshot`/`snapshot_hash`:** `closure_checklist`, aceptación
  (`accepted_by`/`accepted_on`), `final_result`, `pending_items_transferred`, `closure_observations` y la
  metadata de emisión (`issued_by`/`issued_at`, fijados **antes** de construir el snapshot). No es segunda
  captura: se toman del propio documento en `before_submit`.
- **Integridad temporal:** `closure_date` **no puede ser futura**; si hay `accepted_on`, **no puede ser
  posterior** a `closure_date`. `Completed` exige aceptación (`accepted_by`+`accepted_on`); `Cancelled` no.
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

**Enmienda (Mejora continua).** Cada `PMO Lessons Learned` con `recommended_action` exige `action_owner` +
`target_date` y, al submit del Review, genera un **ToDo nativo** (`reference_type = "PMO Post-Project
Review"`, `reference_name` = el Review). Esas acciones pertenecen a **Continuous Improvement**, una capacidad
**separada** de la gobernanza del ciclo: **no** forman parte de Pending Governance Actions (D9), **no**
modifican el lifecycle del Project (D7) ni lo re-marcan como pendiente. El estado/cierre viven en el ToDo
(Open/Closed/Cancelled); sin DocType de acciones, sin workflow, sin estados custom, sin scheduler. El
seguimiento se presenta separado: un **Quick List** nativo ("Acciones de mejora continua") en el Workspace y
el **Script Report `PMO Continuous Improvement`** (P4: acota por Reviews visibles; nunca revela Review/Project
oculto). El snapshot v2 del Review congela `action_owner`/`target_date` (no el estado posterior del ToDo).

### D6 — Risk Analysis: diferido en esta iniciativa → implementado en ADR-0016 (enmendado 2026-09-25)
Risk Analysis se **difirió** durante esta iniciativa (no condicionó ni formó parte de sus bloques). **Enmienda:**
posteriormente se implementó —**ligero**— en **ADR-0016** (cuestionario administrable `PMO Risk Question` +
`PMO Project Risk Assessment`/`PMO Project Risk Item` como registro ligero, exposición cualitativa 3×3, owner,
status, riesgos manuales, reporte `PMO Project Risk Register`). Notas de compatibilidad con este ADR: el
**Handoff sigue siendo autosuficiente** (ADR-0016 **no** añade child de riesgos al Handoff) y **no** se añaden
señales de riesgo a Closure/Review/Dashboard/Project Control (eso queda diferido en ADR-0016). El `PMO Project
Risk` free-form original queda **descartado permanentemente** (el registro es la vista sobre los Risk Items).
`may_affect_controlled` es **solo señal** (Risk ≠ Change Control). El PHI sigue **bloqueado** (ADR-0013).

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
- `open_change_requests` = Change Requests **abiertos** = `workflow_state ∈ {Draft, In Review, Approved,
  Implemented}` **y** `docstatus != 2` (un CR cancelado **no** cuenta como abierto). Fuente única
  `count_open_change_requests`.

**Pending Governance Actions** (Custom HTML Block "PMO Governance") es una **lista de trabajo**: 6 indicadores
(Sin Handoff · Sin línea base · Solicitudes de cambio abiertas · Requieren cierre · Requieren revisión ·
Análisis de riesgo —reserva de UX, sin lógica—) y filas por Project con **acciones en lenguaje humano**
(*Crear Handoff · Crear línea base inicial · Atender N solicitud(es) de cambio · Emitir cierre · Realizar
revisión post-proyecto*), derivadas server-side de las señales. **No** se exponen claves internas de lifecycle
(`initiation/planning/execution_control`) al usuario. Las acciones se construyen en `_governance_actions`
(dashboard) consumiendo `governance_flags` (fuente única), sin duplicar reglas en JS.

(Señales de riesgo se añadirán con la capacidad de Risk, D6; hoy el indicador de riesgo es solo reserva de UX.)

**Frontera con Mejora continua.** Pending Governance Actions cubre **exclusivamente** el ciclo del Project y
**termina al emitir el Review** (`needs_review` pasa a `False`). Las acciones de Lessons Learned (ToDo) son
**Continuous Improvement** (ver D5) y **no** se incluyen aquí, **no** re-marcan al Project como pendiente ni
tocan `governance_flags`/`_governance_actions`. Su seguimiento es una sección separada del Workspace
(Quick List) + el reporte `PMO Continuous Improvement`.

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
- **Mantener el Charter como formulario de planeación completo (objetivo/alcance/entregables/supuestos/
  restricciones)** → genera recaptura administrativa y duplica Proposal/Project/Baseline; se rechaza. El Acta
  de Inicio actual recupera **solo** objetivo y alcance **de alto nivel** (no entregables/supuestos/
  restricciones) y añade la **autorización formal de inicio** (ver D3, enmienda Charter + Autorización).
- **Workflow de ciclo de vida en Project** → status paralelo; se rechaza (D7 derivado).

## Criterios de aceptación
- Existen **3 artefactos persistentes principales** (Handoff/Closure/Review submittable); los child DocTypes de
  soporte no cuentan como restricción; el resto es derivado/snapshot/Print Format/sección.
- **Ningún artefacto ni referencia de riesgo** se implementa en esta capacidad (D6/Fuera de alcance).
- El Handoff es **autosuficiente** (no depende de riesgos ni de otro artefacto para emitirse); captura objetivo
  y alcance **de alto nivel** + autorización formal de inicio, y **no** recaptura entregables/supuestos/
  restricciones ni el detalle de WBS.
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
