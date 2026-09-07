# CONTINUITY.md — pmo

**Fecha:** 2026-09-07
**Rama activa:** `feat/change-control` (base `version-16` @ v0.5.0).
**E2E comercial: RECHAZADO como gate** (revisión funcional). NO avanzar a bump/push/PR/release. Se corrigen
hallazgos uno por uno. **Punto 1 (PMO Members) ✅**: retirado `PMO Project Member` + `Project-pmo_members`;
membresía **derivada nativa** `owner + DocShare(Project) + ToDo activo` (D6 honra flags; owner comparte su
Project). Patch `migrate_pmo_members_to_docshare`. ADR-0002 revisado (D1/D2/D6/D7/D8). **Suite 188/188.**
Siguiente pendiente del usuario: **Punto 2 — Proposal Group**.
**Tarea actual:** **v0.6.0 — Integrated Change Control.** Arquitectura cerrada y **ADR-0005 Accepted**.
Bloques 1–5 ✅ + UX 5.1 ✅ (`3dfa02c`). **UX 5.2 — comparador como reporte real ✅** (commit en curso):
Script Report `PMO Baseline Comparison` (pantalla completa, `execute` reutiliza `compare_baselines`, P4 por
delegación, solo diferencias, una fila por diferencia atómica, resumen + variación, export/print nativos);
**modal retirado** (`baseline_compare.js` + `app_include_js` eliminados); botones de CR/Baseline hacen
`set_route` al reporte (CR = contexto, no atribución). **Suite 187/187.**

**Dependencia `erpnext_proposals` RESUELTA:** contrato `apply_addendum_to_project(quotation, project)`
implementado y liberado en **v0.20.0** (`d2c2c3a`): Project existente únicamente, guards comerciales
reutilizados, `write` sobre Project como autoridad, idempotencia de Tasks, `proposal_project` fijado solo
tras materializar, sin commit interno, `Ganada` no dispara nada. ADR-0019 (en ese repo) quedó como
`Propuesto` pese a estar liberado — inconsistencia documental menor, no bloquea.

**Siguiente paso (antes del Bloque 6): E2E comercial real** en `pmo-v16.dev`: instalar/verificar
`erpnext_proposals v0.20.0` → CR → Quotation/Addendum Ganada → Aplicar al Project existente → Tasks sin
duplicar → Current Plan → Implementado → baseline_after → Cerrado → reporte de comparación. Si pasa → Bloque
6 (bump 0.6.0 + push/PR).

> v0.5.0 ya está **mergeado y liberado** (PR #6 → `f4fb3bc`; tag/Release v0.5.0). DEMO en `pmo-v16.dev`
> se dejó disponible (no limpiar aún).

---

## Recuperación rápida

ADR-0005 (Accepted) define Change Control integrado. Referencia viva:
`docs/adr/0005-integrated-change-control.md`. Fronteras:
`CR = gobernanza` · `Quotation/erpnext_proposals = solución/alcance/valuación/aprobación propia` ·
`Project/Task = Current Plan` · `PMO Project Baseline = referencia before/after` · `Timesheet = Actual`.

---

## Plan por bloques (un PR único a `version-16`)

- **Bloque 1 — ADR-0005 (docs) + CHANGELOG `[0.6.0]` en preparación. ✅** commit `15fb9dd`.
- **Bloque 2 — DocType `PMO Change Request` + P4. ✅** DocType submittable (`PMO-CR-.#####`), controller
  con invariantes base (defaults, `impact_summary`, moneda, integridad baselines, `before_submit`,
  `before_cancel`), P4 (`has_permission_change_request` + `get_permission_query_conditions_change_request`,
  helper `_is_project_writer`) en `permissions.py`+`hooks.py`, tests `test_change_request.py` (8), docs
  técnico/usuario. **Suite 159/159.** *(commit en curso)*
- **Bloque 3 — Workflow + acción Aplicar + Aplicado/Implementado. ✅** Fixtures `workflow.json` +
  `workflow_state.json` (estados en español, evita el default "Draft"); gates por transición
  (`_apply_workflow_gates`) + `before_update_after_submit` (Frappe NO corre `validate` en
  submitted→submitted); condición owner-only en transiciones de decisión (UI) + gate P4; `before_submit`
  red de seguridad de baseline; `before_cancel` bloquea terminales. Acción whitelisted
  `aplicar_quotation_al_project` delegando en `pmo/change_control.py` → contrato
  `erpnext_proposals.apply_addendum_to_project` (mockeado en tests; sin escribir `proposal_project`).
  JS `pmo_change_request.js`. Tests (17 en `test_change_request.py`). **Suite 168/168.** *(commit en curso)*
- **Bloque 4 — Comparator Baseline↔Baseline. ✅** `pmo/compare.py`: `compare_snapshots` (puro, sobre
  snapshots v1: added/removed/changed de tasks — fechas/horas/estado/estructura/assignments — + project
  dates; orden determinista) y `compare_baselines` whitelisted (P4 read en ambas + mismo Project). UI:
  `public/js/baseline_compare.js` (global, `pmo_show_baseline_diff`) + botón en CR ("¿Qué cambió?
  (baselines)") y en Baseline ("Comparar con la anterior"). Tests `test_baseline_compare.py` (11).
  **Suite 179/179.** *(commit en curso)*
- **Bloque 5 — Change Register (Report Builder P4-safe). ✅** Reporte estándar `PMO Change Register`
  (`pmo/pmo/report/pmo_change_register/`, is_standard=Yes, ref PMO Change Request): 15 columnas, orden
  request_date desc + priority desc, roles Projects User/Executive/System Manager (pqc restringe filas).
  Se evita Query/Script Report (ignoran pqc). Test `test_change_register_list_p4`. Docs técnico+usuario.
  **Suite 180/180.** *(commit en curso)*
- **UX 5.2 — comparador como Script Report `PMO Baseline Comparison`. ✅** *(commit en curso)* Reemplaza el
  modal (retirado). `execute` reutiliza `compare_baselines`; P4 por delegación; solo diferencias; una fila
  por diferencia atómica (Tipo/WBS-Tarea/Campo/Antes/Después/Variación); resumen superior; CR = contexto.
  Botones de CR/Baseline con `set_route`. Tests `test_report_baseline_comparison.py` (5). **Suite 187/187.**
- **E2E comercial real** (dependencia resuelta, `erpnext_proposals v0.20.0`): instalar/verificar en
  `pmo-v16.dev` y correr el flujo con Quotation completo.
- **Bloque 6 — bump `__version__`→0.6.0 + cierre.** Luego `/ship push` + `/ship pr`.

## Decisiones vigentes (ADR-0005, resumen)
- **Único DocType nuevo `PMO Change Request`** (submittable, `PMO-CR-.#####`). Impacto mínimo: `priority`
  (Baja/Media/Alta), 5 Checks (scope/schedule/effort/commercial/risk), deltas horas/días/monto (+`currency`),
  `impact_notes`, `evaluation_notes`. Sin severidad por dimensión, sin fechas, sin calidad, sin business case.
- **La Proposal ES una `Quotation`** (sin entidad nueva en `erpnext_proposals`). Scope Items = única fuente
  del alcance; nunca recapturar Tasks.
- **Workflow:** Draft → En revisión → Aprobado/Rechazado → Implementado → Cerrado. `Rechazado`=`docstatus 1`.
  **Sin estado `Aplicado`** (campos `applied_*`). D3↔D7 coherentes.
- **Aprobado ≠ Aplicado ≠ Implementado.** "Aplicar Quotation" solo materializa Scope Items + fija `applied_*`;
  "Marcar implementado" es acto explícito posterior (gate: si hay `proposal_group`, exige `applied_to_project=1`).
- **Gate baseline vigente** al formalizar (`En revisión`); `baseline_before` congelada. `baseline_before`/
  `baseline_after` en el CR; **muchos CR → una misma `baseline_after`**; **sin** Link singular en Baseline.
- **Autoridad Modelo 1:** con Proposal → autoridad comercial/cliente en el Workflow de la Quotation (gate
  "Aplicar" exige `Ganada`); sin Proposal → Project Owner único gate. Executive read-only; Manager sin acceso.
- **CR↔Quotation:** `proposal_group` (hilo/historial) + `applied_quotation` (versión Ganada aplicada). El
  addendum usa `proposal_group` distinto del original. Nunca crea Project nuevo (reuse `proposal_project`).
- **Persistencia post-submit vía `allow_on_submit`** (sin `frappe.db.set_value` de rescate). Amend no se usa;
  Rechazado/Cerrado terminales.
- **Comparator mínimo Baseline↔Baseline** (rotulado "cambios entre baselines", no atribución por CR).
- **Change Register = Report View** nativo (P4-safe por `permission_query_conditions`).

## Dependencia de entrega (bloqueante para "cerrado")
`pmo v0.6.0` **no** se considera funcionalmente cerrado hasta que `erpnext_proposals` implemente/libere el
helper `apply_addendum_to_project(quotation, project)` (ciclo Git separado, autorización propia) y pase la
integración end-to-end: `CR → Quotation versionada → Ganada → aplicar al Project existente → Scope Items →
Tasks → completar Current Plan → Baseline after → cerrar CR`, **sin crear otro Project**. Rutas sin Quotation
(cronograma) no dependen del helper.

## Verificaciones hechas (spike v0.6.0, contra código real)
- `create_project_from_quotation` (`erpnext_proposals/.../utils/project.py`): idempotente, **reutiliza**
  Project si `proposal_project` seteado; append con dedup por `source_quotation_scope_item`. `Ganada` NO
  aplica sola (solo botón `quotation.js:503`).
- Versioning (`proposal_versioning.py`): por rechazo, single-live por `proposal_group` (Ganada NO es estado
  muerto → un addendum en el MISMO grupo se bloquearía; usar grupo distinto). `proposal_project` es
  **read_only=1** → pre-setearlo exige helper server-side (gap real, no cero-cambio).
- Programación del alcance vive en `Quotation Scope Item` (`planned_start_offset_days`,
  `planned_duration_days`, `dependency_scope_item_codes`, `is_milestone`) anclada en `transaction_date` → no
  duplicar fechas en el CR.
- Post-submit nativo: `base_document._validate_update_after_submit` bloquea cambios salvo `allow_on_submit`;
  `apply_workflow` (submitted→submitted) hace `doc.save()`. Amend requiere cancel previo.

## Cuidados / no repetir
- Git solo vía `/ship`. No trabajar en `version-16`. Rutas Desk v16 = `/desk/...` (pero `pmo-v16.dev`
  responde por `/app` — wizard forzado rompe `/desk`).
- `erpnext_proposals` tiene la ruta anidada `apps/erpnext_proposals/erpnext_proposals/erpnext_proposals/...`.
- one_offs/ ignorado. Linters solo `.py`/`.js`, nunca `.json`.
- BD: cualquier escritura/`bench migrate` requiere autorización explícita. Tests en `test-pmo.localhost`.
- ADR como referencia, no dogma: si aparece limitación real/alternativa más simple, reportar antes de
  desviarse (sin re-abrir toda la arquitectura).
