# ADR-0005: Integrated Change Control

**Estado:** Accepted (aprobado 2026-09-06; implementación en v0.6.0 — pendiente)
**Fecha:** 2026-09-06 · **App:** `pmo` · **Objetivo de versión:** v0.6.0
**Depende de:** ADR-0002 (Privacidad Project/Task, P4), ADR-0004 (Schedule Governance & Baselines). **No reabre** ninguno.

## Contexto

ADR-0004 dejó baselines inmutables (Baseline=congelada / Current Plan=mutable / Actual=realidad) pero
**no** el mecanismo que gobierna el paso de una baseline a la siguiente. Un cambio de alcance, cronograma,
recursos o condiciones comerciales debe **registrarse, evaluarse y aprobarse antes** de tocar el Current
Plan, quedar **auditado** (origen, razón, impacto, decisión, before/after, documento comercial,
implementación, cierre) y **no duplicar** la captura de alcance que ya vive en `Quotation` /
`erpnext_proposals`.

Verificado en el bench (Frappe 16.x, ERPNext 16.x): **no existe** un contenedor "Change Request" nativo
(ni en Projects ni en Selling). Lo demás es reutilizable:

- **Frappe Workflow** → lifecycle + aprobación gated por rol/estado, con `doc_status` por estado.
- **`allow_on_submit`** (`base_document._validate_update_after_submit`) → edición controlada de campos
  específicos tras el submit, sin bypass de la inmutabilidad del documento.
- **ToDo / Assignment Rule** → asignación/enrutamiento.
- **Comment / Communication / File / Version (track_changes)** → evidencia y discusión.
- **`Quotation` + `erpnext_proposals`** → alcance (Scope Items), esfuerzo, entregables, valuación,
  precio/condiciones, **programación** del alcance y **versiones**, con su **propio Workflow** comercial.
- **`create_project_from_quotation`** (`utils/project.py`) → transforma Scope Items en Tasks; es
  **idempotente** y **reutiliza** el Project si `Quotation.proposal_project` está seteado (append con
  dedup por `source_quotation_scope_item`). Confirmado: **`Ganada` no aplica nada por sí sola**; la
  aplicación solo ocurre al invocar esa función (hoy, botón manual).

El objetivo es conservar lo útil del proceso vigente del cliente, mejorar con bajo costo y **eliminar
burocracia, no funcionalidad**; sin convertir ERPNext en Primavera.

## Decisiones

### D1 — Único DocType nuevo: `PMO Change Request`

Submittable, autoname `PMO-CR-.#####`, módulo PMO. Contenedor unificador de todo cambio (comercial y no
comercial). **Impacto estructurado mínimo:** `priority` (Select: Baja/Media/Alta, default Media), 5 Checks
de tipo de cambio (scope/schedule/effort/commercial/risk), deltas `impact_hours`/`impact_days`/
`impact_amount` (+ `currency`, default company currency del Project; estimación **no vinculante**),
`impact_notes` y `evaluation_notes`. **Sin** severidad por dimensión, **sin** fechas (viven en la
Quotation/Tasks/Baseline), **sin** dimensión de calidad, **sin** ventana/downtime estructurados, **sin**
campos de business case. La discusión técnica multi-actor usa **Comments nativos**.

**Campos:**

- Solicitud: `project` (Link, reqd), `title` (reqd), `raised_by` (Link User, default sesión, ro),
  `origin` (Select: Cliente/Interno/Regulatorio/Otro), `request_date` (Date, default hoy, ro),
  `priority`, `reason` (Small Text, reqd), `description` (Text Editor).
- Impacto: `impacts_scope|schedule|effort|commercial|risk` (Check), `impact_hours` (Float),
  `impact_days` (Int), `currency` (Link Currency), `impact_amount` (Currency, options=`currency`),
  `impact_notes` (Small Text), `evaluation_notes` (Text), `impact_summary` (Data, ro, computado — para el
  Register).
- Comercial: `proposal_group` (Data), `applied_quotation` (Link Quotation, ro).
- Baselines: `baseline_before` (Link PMO Project Baseline, ro, auto), `baseline_after` (Link, ro).
- Decisión: `approved_by` (Link User, ro), `approved_at` (Datetime, ro), `decision_notes` (Small Text).
- Implementación: `applied_to_project` (Check, ro), `applied_at` (Datetime, ro),
  `implementation_notes` (Small Text).
- Estándar: `workflow_state`, `amended_from`.

### D2 — La Proposal ES una `Quotation`

**No** se crea ningún DocType ni entidad "Proposal" en `erpnext_proposals`. Los **Scope Items de la
Quotation son la única fuente del alcance**; horas/esfuerzo, entregables, valuación, precio/condiciones,
**programación** (`planned_start_offset_days` + `planned_duration_days` + `dependency_scope_item_codes` +
`is_milestone`, ancladas en `transaction_date`) y **versiones** viven en la Quotation. **Nunca** se
recapturan Tasks equivalentes en el CR.

### D3 — Lifecycle (Workflow nativo)

`Draft → En revisión → Aprobado / Rechazado → Implementado → Cerrado`. **Sin** estado `Aplicado` (se
representa con los campos `applied_*`, no con un estado).

| Estado       | doc_status                |
|--------------|---------------------------|
| Draft        | 0                         |
| En revisión  | 0                         |
| Aprobado     | 1 (submit)                |
| Rechazado    | 1 (submit)                |
| Implementado | 1 (update-after-submit)   |
| Cerrado      | 1 (update-after-submit)   |

**Transiciones:**

- `Draft → En revisión`: gate de baseline vigente (D4) + congela `baseline_before`.
- `En revisión → Aprobado` / `En revisión → Rechazado`: submit (owner, D6/D13).
- `En revisión → Draft`: devolver.
- **`Aprobado` — acción "Aplicar Quotation al Project"** (solo cuando hay Quotation): materializa los
  Scope Items como Tasks y fija `applied_to_project`/`applied_at`/`applied_quotation`. **No cambia el
  Workflow por sí sola** (permanece en `Aprobado`). Idempotente. Ver D7.
- **`Aprobado → Implementado` — acción "Marcar implementado"**: la ejecuta el usuario **después** de
  completar también los ajustes de fechas/asignaciones/Current Plan. Gate: si el CR tiene
  `proposal_group`, exige `applied_to_project=1`. Para cambios **sin** Quotation, el PM ajusta el Current
  Plan y luego ejecuta "Marcar implementado" (esas ediciones **son** la implementación).
- `Implementado → Cerrado`: gate `baseline_after` (D9).

**Flujo resultante:**

- Con Quotation: `Aprobado → [Aplicar Quotation al Project] → ajustar Current Plan → Marcar implementado
  → Implementado`.
- Sin Quotation: `Aprobado → ajustar Current Plan → Marcar implementado → Implementado`.

`Rechazado` = `docstatus 1` → **evidencia terminal inmutable**.

### D4 — Gate de baseline vigente

Un CR **no puede formalizarse** (pasar a `En revisión`) si el Project no tiene una **Baseline vigente**
(`get_effective_baseline`). Antes de esa baseline se está en **planificación**, no en Change Control. Al
formalizar, `baseline_before` se resuelve y **congela**. Gate **duro**, no warning.

### D5 — Cardinalidad de baselines (reconciliada con el modelo actual de Baseline)

**Actualización (reconciliación con `PMO Project Baseline`, tipo `Approved Change`).** La cardinalidad
"muchos CR → una `baseline_after`" **queda derogada**. Modelo vigente **uno-a-uno**:

- `baseline_before` sigue viviendo **en el CR** (Link, read-only, congelado al formalizar).
- `baseline_after` en el CR es **read-only para el usuario** (`allow_on_submit` solo porque el sistema lo
  actualiza tras el submit del CR). **No** hay selección manual, ni botón "Use current baseline", ni query
  de selección: se eliminan.
- Una `PMO Project Baseline` de tipo **`Approved Change`** referencia **exactamente un** `PMO Change Request`
  (campo `change_request`, ADR-0004 D4) y, **al Submit**, fija automáticamente
  `PMO Change Request.baseline_after = esa Baseline` mediante `doc.save` normal bajo la autoridad del Project
  Owner (sin `ignore_permissions`, sin segunda semántica).
- El usuario **no** relaciona manualmente CR y Baseline en ambos lados. Secuencia:
  `CR Approved → implementar en el Current Plan → Mark Implemented → crear Baseline Approved Change
  seleccionando ese CR → Submit fija CR.baseline_after → CR puede Closed`.
- `Replan` **no** se usa para cerrar Change Requests (replaneación de gestión sin CR).

### D6 — Autoridad y coordinación de Workflows (Modelo 1)

- **Cambios CON Proposal/Quotation:** la autoridad sobre **solución, condiciones comerciales y aceptación
  del cliente** vive en el **Workflow de la Quotation** (`Aprobada` = solución interna; `Ganada` =
  cliente aceptó), con sus roles propios. El CR **no re-aprueba** esos términos ni recrea
  Sponsor/Comité/Cliente en PMO. El `Aprobado` del CR es la **decisión de gobernanza** = *"autorizo
  incorporar este cambio a este Project y su baseline"*, y el **gate de "Aplicar" exige que la Quotation
  esté `Ganada`**.
- **Cambios SIN Proposal:** autoridad mínima = **Project Owner** (único gate del CR).
- Se evitan dos sistemas de aprobación paralelos: lo comercial se **apoya** en el Workflow de la Proposal;
  el CR solo añade la decisión de incorporación.

### D7 — Aprobado ≠ Aplicado ≠ Implementado

- `Ganada` **no** modifica el Project por sí sola (verificado).
- **"Aplicar Quotation al Project"** (acción whitelisted): valida CR `Aprobado` + Quotation `Ganada`
  (docstatus 1, no superseded, single-live de su grupo, mismo customer/company); **pre-setea
  `proposal_project` = Project existente**; invoca `create_project_from_quotation` → **reutiliza** el
  Project y **anexa** solo los Scope Items nuevos (dedup por `source_quotation_scope_item`). Al completar,
  fija `applied_to_project`/`applied_at`/`applied_quotation`. **No cambia el Workflow por sí sola.**
  **Nunca crea otro Project.**
- **`Implementado`** es una **confirmación explícita posterior** = *el cambio aprobado completo está
  reflejado en el Current Plan* (Tasks materializadas **y** fechas/asignaciones ajustadas). Gate: si hay
  `proposal_group`, exige `applied_to_project=1`; en cambios solo-cronograma (sin Proposal), el PM edita
  el plan a mano y marca `Implementado`.

### D8 — CR ↔ Quotation (cardinalidad / versioning)

El CR guarda `proposal_group` (Data — hilo lógico, historial completo vía versioning por rechazo dentro de
su grupo) **y** `applied_quotation` (Link, ro — la versión `Ganada` efectivamente aplicada). Se
**preserva** el modelo de versioning de `erpnext_proposals` (rejection-driven, single-live por grupo). El
addendum usa un **`proposal_group` distinto** del original (evita el bloqueo de single-live contra la
propuesta original `Ganada`, que no es estado muerto).

### D9 — Nueva Baseline después de implementar (reconciliado)

Tras `Implementado`, el owner crea una nueva `PMO Project Baseline` de tipo `Approved Change`
**seleccionando ese CR**; al Submit de esa Baseline se fija automáticamente `CR.baseline_after` (mismo
Project, `effective_date ≥ baseline_before`). Solo entonces el CR puede **Cerrarse**. El gate
`Implementado → Cerrado` exige `baseline_after` **y** `stakeholder_communication`.

### D10 — Persistencia post-submit (nativa, sin bypass)

Los campos que cambian legítimamente tras aprobar son **`allow_on_submit=1`**: `applied_to_project`,
`applied_at`, `applied_quotation`, `baseline_after`, `implementation_notes` (`workflow_state` lo maneja el
Workflow). El **contenido de la solicitud** (`project`, `title`, `reason`, `description`, checks, deltas,
`priority`, `evaluation_notes`, `baseline_before`, `approved_by/at`, `decision_notes`) **no** es
`allow_on_submit` → queda **inmutable** por el core (`_validate_update_after_submit`). Las transiciones
submitted→submitted usan `doc.save()` nativo (`apply_workflow`). **No** se usa `frappe.db.set_value` de
rescate. **Amend no forma parte del lifecycle**: `Rechazado`/`Cerrado` son terminales (`before_cancel`
bloquea su cancelación → no son amendables); `cancel` queda solo como "retirar" un `Aprobado` **no
aplicado** (owner), bloqueado si `applied_to_project` o `Cerrado`. Un nuevo intento es **otro CR**.

### D11 — Comparator mínimo Baseline↔Baseline

Módulo determinista sobre snapshots v1 (reutiliza los ya almacenados; no reconstruye, no toca esquema).
Identifica: Tasks añadidas/eliminadas, cambios de fechas, `expected_time`, estructura/WBS, estado,
assignments (`override_hours`/`effective_hours`) y fechas de Project. Whitelisted
`get_baseline_comparison(a, b)` con check `read` sobre **ambas** baselines (= `is_project_visible`) y mismo
Project → **P4-safe**, sin fuga cross-project. Render **modesto** (diálogo/tabla), rotulado **"cambios
entre baselines"**. Con el modelo actual la Baseline `Approved Change` referencia un único CR; el CR abre
el comparador como contexto (before → after). Sin overlay Gantt.

### D12 — Change Register (Report View nativo)

`PMO Change Request` es el propio registro. Se entrega un **Report View** nativo (**P4-safe** por
`permission_query_conditions`, no Query/Script Report) con columnas/filtros: Project, CR, título, estado,
fecha, `priority`, tipo(s) de impacto (`impact_summary`), horas/días/monto, `proposal_group`/
`applied_quotation`, `baseline_before`, `baseline_after`.

### D13 — P4 del CR (ADR-0002)

Hooks (sin tocar DocPerms), mismo patrón que `PMO Project Baseline`: `read` = `is_project_visible`;
`create`/`write` = project writer (owner **o** member; `write` solo en `docstatus 0`);
`submit`/`cancel`/`amend` = **owner** (esto sella owner-only aprobar/rechazar); `share` = False.
`permission_query_conditions` por proyectos visibles. `PMO Executive Access` read-only; `PMO Manager` sin
acceso. Los miembros pueden crear, documentar, evaluar y enviar a revisión, pero **no aprueban por ser
members**. Coherencia de UI: `condition` en las transiciones de aprobación (además del gate P4), para no
depender solo de que el submit falle tras pulsar.

### D14 — Reconciliación con el procedimiento del cliente (FO-AG Control de Cambios)

Se alinea el CR con el procedimiento real **sin** reintroducir matriz A/M/B, Calidad, Evaluación de Valor,
business case, CCB complejo, fechas de implementación duplicadas ni firmas gráficas. Campos añadidos:

- **Aceptación del cliente (solo cambios SIN addendum):** `customer_approval_status`
  (`Pending`/`Approved`/`Not Required`), `customer_approved_by` (Contact), `customer_approved_on` (Date),
  `customer_approval_notes` (Small Text). Con `proposal_group` la aceptación **deriva** de la Quotation
  Ganada/aplicada (no se recaptura). Sin e-signature.
- **`implementation_owner`** (Link Employee): responsable de confirmar la incorporación al Current Plan;
  default inicial `Project.pmo_operational_owner` (no modifica el Project), editable mientras el CR sea
  editable, obligatorio antes de `Mark Implemented`.
- **`stakeholder_communication`** (Small Text, `allow_on_submit`): evidencia de comunicación a interesados;
  admite `N/A`. Comments/Communication/Files nativos siguen como evidencia complementaria.

**Gates finales del Workflow** (`Draft → In Review → Approved/Rejected → Implemented → Closed`):
- `In Review`: baseline vigente + congela `baseline_before` (D4).
- `Rejected`: **`decision_notes` obligatorio**.
- `Implemented`: `implementation_owner` definido; si `impacts_commercial` → `proposal_group` +
  `applied_to_project`; si **no** hay addendum → `customer_approval_status` = `Approved` (Contact+fecha) o
  `Not Required` (justificación); `Pending` bloquea.
- `Closed`: `baseline_after` (fijada por la Baseline `Approved Change`) + `stakeholder_communication`.

**Señal de Governance (abiertos/accionables):** `OPEN_CHANGE_REQUEST_STATES = {Draft, In Review, Approved,
Implemented}`; terminales `Rejected`/`Closed`. `Pending Governance Actions` la consume automáticamente
(fuente única `pmo.governance`).

## Interacción con `erpnext_proposals` — contrato publicado (v0.22.0)

El contrato vive en `erpnext_proposals` (repo/ciclo aparte) y quedó **publicado en `v0.22.0`**. PMO lo
**consume por delegación** (`pmo/change_control.py`, vía `frappe.get_attr` = feature-detection; error claro
si el app no está o es `< 0.22.0`). PMO **no** interpreta `<ROOT>-ADD-<NN>`, **no** calcula secuencia,
**no** crea `proposal_group`, **no** resuelve el Project desde `project_name`, **no** escribe
`proposal_project`, **no** crea Tasks del addendum.

- **Convención de grupo (en `erpnext_proposals`):** un addendum usa un `proposal_group` **nuevo**
  `<ROOT>-ADD-<NN>`; sus versiones conservan ese grupo (versioning por rechazo intacto, single-live por
  grupo). El sufijo `-ADD-<NN>` es marca reservada (un grupo normal no puede introducirlo manualmente).
- **`create_addendum_quotation(root_quotation) -> str`** (`utils.addendum`): resuelve el root canónico,
  bloquea por root, calcula la secuencia y crea **atómicamente** la addenda (delta comercial: hereda solo
  contexto comercial seguro; **no** copia items/scope/`proposal_project`/template). Exige **autoría
  comercial** (`assert_can_manage_proposals` → `Proposals Manager`/`System Manager`).
- **`apply_addendum_to_project(quotation, project) -> dict`** (`utils.project`): valida (Ganada, docstatus 1,
  no superseded, single-live del grupo, mismo customer/company), **escribe `proposal_project`** y anexa los
  Scope Items como Tasks (reuse + dedup). Resuelve/valida el Project destino por la relación persistente
  `Quotation.proposal_project` (nunca por nombre).

**Consumo desde PMO (sin campos nuevos):** la acción `crear_addenda` del CR localiza una Quotation del
contrato por `Quotation.proposal_project == CR.project` y delega en `create_addendum_quotation`; persiste la
identidad de la addenda en el campo existente **`proposal_group`**. La aplicación usa
`apply_addendum_to_project` y fija `applied_*` solo tras retorno exitoso. Precondición: **`erpnext_proposals
>= 0.22.0`** instalado en el sitio.

### Autoridad (ADR-0005 Modelo 1) — sin elevación de permisos

Dos autoridades **distintas y ambas nativas**, sin bypass/`ignore_permissions`/impersonation:
- **Crear la addenda (acto comercial):** `assert_can_manage_proposals` (`Proposals Manager`/`System
  Manager`), impuesta por `erpnext_proposals`. La acción PMO además exige **`write` sobre el CR** editable
  (owner o colaborador con DocShare-write; P4). Es la **intersección** de ambas autoridades (participante
  del proyecto **con** autoría comercial); si falta la comercial → `PermissionError` claro.
- **Gobernar/aplicar/cerrar el CR y sellar la Baseline:** **Project Owner** (P4). `Ganada` ≠ `Aplicada`: la
  aplicación es un acto **explícito** desde el CR.

No es una incompatibilidad arquitectónica: es la separación de funciones que ADR-0005 ya definía (autoridad
comercial en la Quotation; gobernanza en PMO).

## Consecuencias

Registro de cambios unificado y auditable; se preservan Baseline=congelada / Current=mutable /
Actual=realidad y "no mutar el Current Plan antes de aprobar"; **una sola fuente del alcance** (Quotation →
Tasks); autoridad comercial no duplicada (Workflow de la Quotation). Reutiliza lo nativo (Workflow,
`allow_on_submit`, ToDo/Assignment Rule, Comment/Communication/File/Version) + snapshots v1. Alcance de
construcción: **un DocType**, **un Workflow**, **un comparator**, hooks P4, un Report View — y, aparte, un
helper acotado en `erpnext_proposals`.

## Gaps reconocidos (no implementados)

- Ventana de implementación / downtime (dominio ITIL de cambios a producción).
- Beneficios formales / business case / alineación estratégica estructurada.
- CCB / Sponsor / aprobador delegado (autoridad más allá del Project Owner).
- Reapertura de un CR (nuevo intento = nuevo CR).

## Fuera de alcance (v0.6)

CPM/float, what-if/scenarios, resource leveling, EVM/Cost Baseline, Monte Carlo, variation-order
accounting, constraints avanzados, **Status Date / Planificado vs Real (v0.7)**, UI rico del comparator.

## Alternativas descartadas

- **(B)** Conducir el cambio solo por Quotation-addendum + baselines, sin DocType → no cubre cambios sin
  impacto comercial ni da registro unificado de gobernanza.
- **(C)** Módulo Change Management completo (scoring/CCB/variation orders/EVM) → sobreingeniería, contrario
  al criterio costo/beneficio.

## Relación con ADR previos

- **ADR-0002:** reutiliza el boundary P4 (`is_project_visible`, `PMO Executive Access` read-only,
  `PMO Manager` sin acceso).
- **ADR-0004:** consume Baselines inmutables y snapshots v1. **Reconciliación vigente (D5):** la Baseline
  de tipo `Approved Change` **sí** lleva un Link `change_request` (uno-a-uno) y, al Submit, fija
  `CR.baseline_after`. Queda **derogada** la decisión previa de "no añadir el link en Baseline / cardinalidad
  muchos-CR del lado del CR". No modifica invariantes de lineage / effective_date / cancelación.
