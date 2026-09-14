# ADR-0015: Change Control v2 — flujo único addenda-céntrico (supersede ADR-0005)

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Supersede:** ADR-0005
(Integrated Change Control) · **Depende de:** ADR-0002 (P4), ADR-0004 (Baseline),
ADR-0012 (economía), ADR-0014 (Governance), y de los contratos de `erpnext_proposals` **ADR-0019**
(addendas) y **ADR-0020** (contrato económico) — con las enmiendas de esta iniciativa. · **No toca:**
ADR-0014 (Governance/Closure/Handoff quedan cerrados; solo consumen el CR resultante).

> **Qué se deroga de ADR-0005.** Esta decisión **reemplaza** el modelo de rutas múltiples del CR. En
> particular deroga: (a) **D14** (aceptación del cliente paralela `customer_approval_*` para cambios "sin
> Quotation"); (b) el uso de **`impacts_commercial`** como *router* que decide si hay o no Addenda; (c) toda
> la familia de rutas implícitas "CR comercial / no comercial / costo / esfuerzo / sin Proposal". Los demás
> principios de ADR-0005 (frontera dura hacia `erpnext_proposals`, dos autoridades gobernanza/comercial,
> P4 del CR, versionado por rechazo, atomicidad sin commit interno) **siguen vigentes** y se refuerzan.

## Contexto

La prueba funcional del CR mostró que la implementación se separó del diseño económico/comercial que
`erpnext_proposals` ya gobierna (ADR-0019/0020): **`Autorizado(Project) = Original(root) + Σ(addendas
Ganadas aplicadas)`** por magnitud independiente (revenue, labor, external, total cost, margin), con
identidad `ROOT-ADD-NN` generada atómicamente por `erpnext_proposals`. El CR trató la Addenda como
**opcional** (atada a `impacts_commercial`), habilitando una ruta "sin Quotation" con aceptación del
cliente paralela.

**Consecuencia crítica:** un cambio que consume esfuerzo/costo adicional pero que **no** se enruta por una
Addenda (p. ej. "lo absorbemos, +100 h sin cobrar") **no mueve el autorizado**. Cuando llega el Actual,
aparece un **falso sobrecosto** de ejecución y se corrompe la lectura `Autorizado vs Real`.

## Problema

Necesitamos **un solo flujo** para toda Solicitud de Cambio formal, con la economía gobernada **únicamente**
por `erpnext_proposals`, sin segundo motor económico en PMO, sin campos de "costo autorizado" en el CR, sin
selección manual de Quotation/`proposal_group`, y sin que un exceso de ejecución pueda disfrazarse de cambio
autorizado.

## Decisiones

### D1 — Discriminador único (definitivo)
**Toda Solicitud de Cambio formal → CR + exactamente una Addenda `ROOT-ADD-NN`, incluso con delta $0.**
**`Replan` = únicamente replaneación interna sin Solicitud de Cambio.** Un exceso de ejecución contra el
mismo alcance **no** es CR ni Replan: es **desviación Real** y debe permanecer visible (nunca se oculta
subiendo el autorizado). No existe bifurcación por "impacto comercial" ni por magnitud del delta.

### D2 — La Addenda es la espina del cambio (fuente económica única)
El delta autorizado (cualquier combinación de ingreso/labor/external/scope/horas, incluido $0 o
absorción de costo sin ingreso) **vive en la Addenda**. PMO **no** calcula ni persiste economía; consume
`erpnext_proposals`. La identidad `ROOT-ADD-NN` la crea `erpnext_proposals` (`create_addendum_quotation`);
PMO la conserva **read-only** en `proposal_group` y **deriva** server-side la versión vigente (nunca la
selecciona el usuario, nunca elige una Quotation arbitraria).

### D3 — Aplicar Addenda en dos fases (apply-split)
`apply_addendum_to_project` (enmienda a ADR-0019) se estructura en **dos fases**:
- **SIEMPRE:** valida Addenda `Ganada`; valida root/coherencia/canonicalidad; asocia `proposal_project`;
  **recomputa/sincroniza** la economía autorizada del Project (`sync_project_authorized_cost`). El resultado
  del autorizado **puede quedar idéntico** (una Addenda $0 no necesariamente lo cambia: se asocia y participa
  en la recomputación).
- **SOLO si existen Scope Items ejecutables:** ejecuta la validación de scope/fases correspondiente
  (`_validate_scope_for_project`, que incluye Proposal Template/Phase) y **materializa Tasks**.

Consecuencia: una Addenda **económica-only**, de **costo absorbido**, de **solo Required Items**,
**puramente contractual** o de **delta $0 sin scope ejecutable** **se aplica** (asocia + sincroniza economía)
**sin materializar Tasks** ni **inventar** Tasks que la Addenda no describe. Un delta de **+esfuerzo** se
representa como Scope Item → **Task delta separada** trazable a la Addenda; **regla dura: no se edita la Task
original por ese mismo delta** (evita doble contabilización). No se construye mutación de Tasks existentes en
v1 (gap documentado).

**El apply-split NO relaja `proposal_template` ni `proposal_cost_center`.** Ambos siguen siendo **requisitos
del WORKFLOW** para **formalizar** la Addenda (salir de Borrador / alcanzar `Ganada`): toda Addenda formal
llega **con** Template y Cost Center. El apply-split gobierna solo la **materialización de Tasks**. **Son
problemas distintos:** formalizar (workflow) vs. materializar (apply-split). El único cambio de workflow en
`erpnext_proposals` sigue siendo quitar `net_total>0` para grupos `ROOT-ADD-NN` (B1).

### D4 — Aceptación del cliente = `Ganada` (deroga D14)
`Ganada` es la **única** aceptación del cliente del cambio. Se **eliminan** los campos
`customer_approval_status/by/on/notes`. PMO **no** duplica la aprobación comercial.

### D5 — Orden del flujo (con salida limpia de rechazo)
```
CR Draft → crear Addenda ROOT-ADD-NN → preparar → Addenda "En Revisión" (docstatus 1, delta CONGELADO)
→ CR In Review → CR Approved
→ Addenda "Aprobada" → "Enviada al Cliente" → "Ganada"
→ apply_addendum_to_project → CR Implemented → Baseline Approved Change → CR Closed
```
La decisión de gobernanza (`CR Approved`) se toma con la Addenda en **`En Revisión`** (ya congelada y
exacta). Si gobernanza **rechaza**, la Addenda sigue en `En Revisión` y se rechaza con la transición nativa
`En Revisión → Rechazada` (el workflow de Proposals **no** tiene `Aprobada → Rechazada`; por eso el orden es
éste y **no** se añade transición ni estado a Proposals).

### D6 — Delta gobernado + huella + re-aprobación (guard de integridad)
Gobernanza aprueba **una versión exacta y congelada**, no un grupo abstracto. `erpnext_proposals` provee una
**huella canónica** del delta congelado gobernado de una versión de Addenda: `get_addendum_delta_fingerprint`,
**definida en ADR-0019** (cubre el delta COMPLETO: economía + scope + planificación); ADR-0020 define/consume
solo su **porción económica**. El **delta gobernado** incluye: ingreso, labor, external, Items/Required Items,
Scope Items, horas, y los atributos de plan a nivel scope-item (offsets, duración, dependencias, hitos). La
`pmo_committed_end_date` a nivel Project **no** está en la Addenda: la gobierna la Baseline Approved Change.
La huella es **semántica, no técnica**: NO incluye `name`, nombres de child rows, timestamps, `proposal_version`
ni IDs que cambien al versionar; una nueva versión con el **mismo delta produce la misma huella**; preserva la
multiplicidad de filas, normalizadas y ordenadas canónicamente. Estable solo en `docstatus>=1` (congelado).

- **Precondición de `CR Approved`:** la Addenda vinculada debe estar realmente en **`En Revisión`**
  (`docstatus=1`, congelada y exacta); PMO **rechaza server-side** aprobar el CR contra un **Borrador** (un
  Draft aún puede mutar y no tiene huella comparable). Al `CR Approved`, PMO fija **read-only**
  `approved_addendum` (la Quotation exacta revisada) y `approved_delta_fingerprint` (huella de **esa** versión
  en `En Revisión`).
- Si se reversiona (rechazo del cliente → nueva versión del mismo `ROOT-ADD-NN`) y la huella de la nueva
  versión (en `En Revisión`) **difiere**, el Project Owner debe **re-aprobar** esa versión mediante una acción
  explícita ("Reaprobar versión de Addenda") que actualiza `approved_addendum`/`approved_delta_fingerprint`
  y deja trazabilidad por Version. **Sin estado nuevo en el CR** (sigue `Approved`).
- **Cualquier** cambio en un dato gobernado = re-aprobación. **Sin umbrales monetarios ni porcentajes.** Solo
  cambios puramente editoriales/narrativos que no alteren ningún dato gobernado continúan sin re-aprobación.
- **Guard de `apply` (fail-closed):** `apply` verifica que la huella de la versión `Ganada` == la huella
  aprobada. Si difieren, **falla cerrado**. Nunca se aplica al Project algo distinto de lo que gobernanza
  autorizó.

### D7 — Enforcement server-side (no solo UX)
Los gates son **server-side**, independientes de botones/JS. PMO intercepta el guardado/transición de la
`Quotation` vía `doc_events` (hook de PMO sobre `Quotation`, que conoce Quotation y CR); **`erpnext_proposals`
sigue ignorando al CR** (dependencia `pmo → erpnext_proposals` intacta). Reglas:
- **CR no `Approved` + Addenda en `En Revisión`** → PMO **bloquea server-side** cualquier avance de la Addenda
  salvo `Rechazada`.
- **CR `Approved` + transición `En Revisión → Aprobada`** → PMO la permite **solo si** la huella de **esa**
  versión == `approved_delta_fingerprint`. Si **difiere** (caso típico: rechazo del cliente → **nueva versión**
  del mismo `ROOT-ADD-NN` con delta distinto), PMO **bloquea server-side** el avance hasta que el Project Owner
  ejecute **"Reaprobar versión de Addenda"** (D6), que actualiza `approved_addendum`/`approved_delta_fingerprint`.
  Este gate en `Aprobada` cierra el hueco de que una versión con delta distinto llegue al cliente **antes** de
  la re-aprobación; **no** se delega la protección a `apply` (que la bloquearía demasiado tarde).
- **CR `Approved` + versión ya re-aprobada (o nunca cambiada)** → PMO permite continuar la Addenda
  `Aprobada → Enviada al Cliente → Ganada`.
- **CR `Rejected`** → **no** se auto-ejecutan acciones con permisos elevados; un `Proposals Manager` ejecuta la
  transición nativa de la Addenda a `Rechazada`.
- **`apply`** compara **siempre** la huella de la versión `Ganada` contra `approved_delta_fingerprint` y
  **falla cerrado** si difieren. Este guard vive en el **wrapper de PMO** (`change_control.apply_addendum_to_project`),
  antes de delegar; no depende de UI.

### D8 — Baseline uniforme
Todo CR que llega a `Implemented` genera una Baseline **`Approved Change`** que **referencia el CR** y fija
`CR.baseline_after`; solo entonces cierra. `Replan` nunca cierra CRs. Regla única, trazabilidad uniforme.
Costo aceptado: un cambio puramente económico (sin efecto en cronograma) produce un snapshot casi idéntico
al anterior; es raro y barato frente al beneficio de un único camino y `baseline_after` siempre poblado.

### D9 — Datos/modelo del CR
- **Eliminar:** `customer_approval_status`, `customer_approved_by`, `customer_approved_on`,
  `customer_approval_notes`.
- **Añadir read-only:** `approved_addendum` (Link Quotation), `approved_delta_fingerprint` (Data).
- **Conservar:** `proposal_group` (read-only), `applied_quotation` (read-only), `applied_to_project`,
  `applied_at`, `baseline_before`/`baseline_after` (read-only), `implementation_owner`,
  `stakeholder_communication`, `decision_notes`.
- **Cero campos económicos nuevos.** `impacts_commercial` deja de rutear (puede quedar como etiqueta
  informativa de impacto o eliminarse en implementación).

## Fuera de alcance
- Mutación de horas/costo de una Task existente desde una Addenda (gap conocido; convención = Task delta
  separada; feature futura opcional).
- Segundo motor económico en PMO; campos manuales de "costo autorizado"; captura de `proposal_group` o
  selección manual de Quotation; múltiples workflows por tipo de CR.
- Cualquier cambio a ADR-0014 (Closure/Handoff). Governance consume el CR resultante sin cambiar su contrato.

## Consecuencias
- `Autorizado vs Real` deja de corromperse: solo una Addenda Ganada aplicada mueve el autorizado; el exceso
  de ejecución aparece como desviación real.
- Un solo flujo, sin colección de excepciones. La economía queda 100% en `erpnext_proposals`.
- Nunca se aplica un delta que gobernanza no autorizó (guard de huella fail-closed).
- Se elimina la doble autoridad de aceptación del cliente.

## Alternativas descartadas
- **Discriminador económico** ("si modifica el autorizado → CR+Addenda; si no → Replan"): reabre una
  bifurcación y puede misrutear un cambio formal de delta $0 hacia Replan. Se rechaza; el discriminador es
  formal (Solicitud de Cambio) vs interno (Replan).
- **Gate de "contenido económico" para addendas** (revenue≠0 ∨ labor>0 ∨ …): inventa una segunda definición
  manual de "contenido" al lado del motor canónico y bloquea addendas de $0. Se rechaza; solo se quita
  `net_total>0` para addendas.
- **`Ganada` antes de `CR Approved`**: pediría al cliente aceptar un cambio que gobernanza no autorizó. Se
  rechaza (ver D5).
- **Añadir transición `Aprobada → Rechazada` en Proposals**: acopla el workflow de Proposals a un concern de
  PMO. Se rechaza (Alternativa 2 / D5).
- **Re-aprobación con umbrales/tolerancias**: genera discusiones y agujeros. Se rechaza; cualquier cambio en
  dato gobernado = re-aprobación (D6).

## Criterios de aceptación
- Toda CR implementada tiene exactamente una Addenda `ROOT-ADD-NN` aplicada y Ganada; `Replan` no cierra CRs.
- El autorizado del Project solo cambia por `apply_addendum_to_project`; PMO no calcula economía.
- El usuario nunca captura/selecciona `proposal_group` ni Quotation; la versión vigente se deriva.
- `apply` falla cerrado si la huella Ganada ≠ huella aprobada; re-versión con delta distinto exige
  re-aprobación explícita, sin estado nuevo.
- Enforcement server-side (hook de PMO sobre Quotation + guard de huella en el wrapper), no dependiente de JS.
- `customer_approval_*` eliminados; `Ganada` es la única aceptación del cliente.
- Baseline Approved Change para todo CR Implemented.

## Secuencia de implementación (bloques posteriores; sin código en este ADR)
BLOQUE 0 **ADRs** (este ADR-0015 en `pmo`/`feat/project-governance-lifecycle` + enmiendas ADR-0019/0020 en
`erpnext_proposals`/`feat/addenda-change-control-v2`) → **erpnext_proposals** B1 (gate `net_total` root vs
addenda) → B2 (**apply-split**: fase 1 asociar+sincronizar economía siempre; fase 2 validar scope/fases +
materializar Tasks solo si hay Scope Items ejecutables) → B3 (huella canónica del delta,
`get_addendum_delta_fingerprint`; **incluye el fix de versionado: `create_new_proposal_version()` debe copiar
también `required_items` con su congelamiento — hoy se pierden, ver ADR-0019 §7.4 — para que una revisión no
altere el autorizado ni cambie la huella del mismo delta**) → E2E económico aislado → **pmo** B4 (limpieza de
modelo: quitar `customer_approval_*` + router `impacts_commercial`; auto-resolver versión vigente) → B5
(registro de delta gobernado + re-aprobación + guard de huella en el wrapper de `apply`) → B6 (orquestación de
orden vía hook de Quotation + Baseline Approved Change) → **E2E real** (+100 h absorbidas; re-versión divergente
exige re-aprobación; apply-mismatch fail-closed; overrun como desviación). Cada bloque: diseño → implementar →
validar → presentar → autorizar commit.
