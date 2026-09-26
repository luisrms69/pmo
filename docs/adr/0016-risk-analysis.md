# ADR-0016: Risk Analysis (R1) — cuestionario administrable + registro ligero

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted (implementado) · **Depende de:** ADR-0002 (P4),
ADR-0014 (Governance) · **Enmienda:** ADR-0014 **D6** (Risk Analysis deja de estar diferido). · **No toca:**
economía/Change Control (ADR-0012/0015), Project Control (ADR-0011), PHI (**ADR-0013, bloqueado**).

> **Numeración.** Este ADR es **0016**, no 0013: el número **0013 está reservado para el PHI (bloqueado)** y
> así lo referencian ADR-0014 y el resto del cuerpo documental. Usar 0013 para Risk consumiría esa reserva y
> rompería la frontera "no PHI".

> **Enmienda (2026-09-25) — separación Assessment / Risk Register.** La primera implementación de R1 usó los
> `PMO Project Risk Item` del Assessment **como** Risk Register (registro = vista de items). La **prueba manual
> demostró que ese modelo es conceptualmente incorrecto**: mezcla el *instrumento de identificación/cribado*
> (respuestas al cuestionario) con el *registro vivo* (riesgos que evolucionan) y **entierra la historia** del
> riesgo en Version/Activity. Esta enmienda lo corrige separando responsabilidades (ver D5–D8 y D11–D13). La
> decisión "items = register" queda **derogada**.

> **Modelo corregido (cadena de responsabilidad):**
> 1. **`PMO Risk Question`** — catálogo/instrumento de identificación.
> 2. **`PMO Project Risk Assessment`** — cribado/identificación del Project + evaluación inicial *as identified*.
> 3. **`PMO Project Risk`** — riesgo persistente y vivo durante la ejecución (estado vigente).
> 4. **`PMO Project Risk Register`** (reporte) — vista de los `PMO Project Risk` del Project.
> 5. **Historia del riesgo — NATIVA** (`track_changes` → `Version` + Timeline). El motivo funcional obligatorio
>    del cambio se publica como **Comment nativo** desde el campo transitorio `update_note` (ver D7, enmienda Opción E).

## Contexto

`pmo` cubre planeación, capacidad, baselines, control, cambios, economía, gobernanza y mejora continua, pero el
**análisis de riesgos** quedó explícitamente diferido en ADR-0014 D6. Una revisión metodológica (PMI/PMBOK e
ISO 31000) confirmó que el enfoque *prompt de identificación → análisis cualitativo → registro* es sólido, con
dos condiciones: (1) el riesgo concreto necesita un **enunciado** (la pregunta no es el riesgo); (2) la
identificación no puede ser una **lista cerrada** (debe admitir riesgos no anticipados).

Existía ya un cuestionario embrionario (`PMO Project Risk Assessment` + `PMO Project Risk Item`) con 6 preguntas
**hardcodeadas**, exposición derivada 3×3 y P4, pero **sin punto de entrada en UI, sin catálogo administrable,
sin enunciado del riesgo y sin campos de seguimiento**. R1 lo completa metodológicamente y lo hace alcanzable,
**deliberadamente ligero**.

## Problema

- El cuestionario no es administrable (preguntas en código) ni extensible por dominio.
- El "riesgo" no se puede expresar: falta la descripción (risk statement) — el registro no es accionable.
- No hay forma de capturar riesgos fuera del catálogo (identificación cerrada).
- No hay registro de seguimiento (owner/estado) durante la ejecución.
- No hay superficie de consulta (registro) ni navegación.

## Decisiones

### D1 — El cuestionario es un instrumento de identificación (prompt list)
Cada pregunta es un **prompt de aplicabilidad** (aplica/no aplica), técnica reconocida por PMBOK. NO es el
riesgo. La aplicabilidad la decide el equipo **por Project** (juicio de contexto, ISO 31000); **no hay motor de
reglas** de aplicabilidad.

### D2 — Catálogo administrable en UN solo DocType (`PMO Risk Question`)
Master global (sin P4; no es project-scoped): `code` (estable, autoname, referencia de snapshot e i18n),
`section` (**Select**), `question`, `active`, `sort_order`. El acto frecuente —gestionar preguntas— es data pura
para el admin (System Manager / PMO Manager). **No** se crea un segundo DocType de secciones: la sección no
tiene comportamiento propio en R1 (la precarga carga todas las activas por igual); un catálogo de secciones
sería estructura administrativa sin ventaja funcional. `Data` libre se descarta (duplicados inconsistentes);
`Select` da valores controlados. **Añadir una sección** (acto raro) se hace por el **mecanismo versionado normal
de la app** (editar el JSON del DocType) — **nunca Property Setter**. Ruta de crecimiento no disruptiva: si en
el futuro se requiere auto-servicio de secciones, se promueve `section` a `Link` sin romper histórico (el
snapshot lo protege).

### D3 — Secciones iniciales: generales + especializada Tecnologías de Información
Generales: External dependencies · Scope & requirements · Schedule · Cost / economic · Resources & team ·
Stakeholders & governance. Especializada inicial: **Information Technology**. La arquitectura admite futuras
secciones especializadas **sin** plantillas ni motores por industria.

### D4 — Precarga con SNAPSHOT (inmunidad histórica)
Al crear un `PMO Project Risk Assessment`, se precargan las preguntas **activas** del catálogo y se **snapshotea**
`code` + texto + sección en cada fila. Editar/desactivar el catálogo después **no** altera assessments
existentes. El catálogo no se vuelve a consultar tras el insert.

### D5 — El Assessment Item registra IDENTIFICACIÓN (as identified), no estado vivo
El `PMO Project Risk Item` es el registro de **cribado/identificación**. Cuando `applies = Yes` guarda:
**`description`** (enunciado del riesgo, **obligatorio**; forma sugerida *causa → evento incierto → efecto*, como
ayuda, no tres campos) · `probability` · `impact` · `exposure` **as identified** (derivada server-side, matriz
3×3; nunca del cliente) · `may_affect_controlled` (**solo señal**) · `is_manual` · `risk` (link al riesgo vivo
generado). **owner / response / status NO viven aquí.** Al `applies = No` se limpian los campos de identificación.
Tras generarse el riesgo, los campos de identificación quedan **de solo lectura** (`read_only_depends_on:
eval:doc.risk`) para preservar el *as identified*; la evolución ocurre en el `PMO Project Risk`.

### D6 — `PMO Project Risk` es el Risk Register vivo (deroga "items = register")
Cada riesgo identificado es una **entidad persistente e independiente** (`PMO-RISK-.#####`) con **estado vigente**:
`probability` · `impact` · `exposure` (derivada) · `owner` · `response`/tratamiento · `status`
(**Open / Managing / Closed / Materialized**; *Materialized* = frontera riesgo→issue, PMBOK) · `may_affect_controlled`
(señal) · `identified_on` · origen (`source_section`/`source_question_code`/`assessment`/`source_item` o `is_manual`).
**No submittable**, `track_changes` on, P4 heredado del Project. **Sin workflow, transiciones forzadas, ciclos ni
automatización**: el owner fija el estado a mano.

### D6b — Ciclo de vida del Assessment (modelo final: Save nativo)
Uno por Project (`project` unique) e **inmutable** una vez creado; **NO submittable**; vivo/reevaluable durante el
proyecto. El workflow usa el **Guardar nativo de Frappe** (sin acciones/botones extra):
- **El Save materializa** los `PMO Project Risk` de los items `applies = Yes` **completos** que aún no tienen
  `item.risk`. Una identificación válida exige, server-side, **description + probability + impact** (impide guardar
  una fila aplicable incompleta); `exposure` se deriva server-side (matriz 3x3; nunca del cliente).
- **Idempotente** (clave `item.risk` / origen `(assessment, source_item)`): guardar repetido **no duplica** ni
  modifica Risks existentes. Tras generarse, la identificación del item queda de solo lectura
  (`read_only_depends_on: eval:doc.risk`), preservando el *as identified*.
- **Reevaluación** = el mismo Assessment: al marcar nuevas preguntas aplicables completas y guardar, se generan
  **solo** esos nuevos riesgos; los existentes se administran SOLO desde `PMO Project Risk`. Riesgos no anticipados
  / recurrencias → **escape hatch manual** (fila manual sin `question_code`, o `PMO Project Risk` directo).
- **Estado derivado** por `pmo.risk_signals` (sin persistir máquina de estados): `none` (sin Assessment) /
  `assessed` (existe). Señales adicionales de riesgos: abiertos/en gestión, exposición alta, sin responsable, sin
  tratamiento — consumidas por el form de Project (indicadores) y por Project Control (sección Riesgos).
- Al borrar un riesgo generado se libera `item.risk` (puede re-generarse al guardar si el prompt sigue aplicando).

**Inmutabilidad de `project` (regla estructural compartida).** Un documento pertenece al Project en que se creó y
no se traslada. Los **7 DocTypes pmo con Link estructural a Project** (Risk, Risk Assessment, Baseline, Change
Request, Closure, Handoff, Post-Project Review) aplican `set_only_once` (UX) + enforcement server-side común
`pmo.project_link.enforce_immutable_project` (vía `doc_events`, cubre form/API/script/import/save).

### D7 — Historia del riesgo: NATIVA (`track_changes`/`Version` + Timeline) + motivo como Comment (enmienda Opción E)
**Enmienda (2026-09-25):** se **deroga** el child custom `PMO Project Risk Update`. La revisión técnica de Frappe
v16 confirmó que `track_changes=1` + el DocType nativo `Version` ya conservan **qué cambió, old → new, quién y
cuándo** (un solo `Version` por save aunque cambien varios campos; `frappe/model/document.py::save_version` +
`frappe/core/doctype/version/version.py::get_diff`), consultables en el **Timeline** nativo
(`version_timeline_content_builder.js`). Un child propio **duplicaba** eso (y era más débil: no guardaba el valor
anterior). Lo único que Frappe no cubre es el **motivo funcional obligatorio**: se resuelve con el campo
**transitorio** `update_note`, obligatorio cuando en un Risk existente cambia un campo **material**
(`description`, `probability`, `impact`, `status`, `owner`, `response`, `may_affect_controlled`; `exposure` es
derivada y no es trigger). Tras un save exitoso, `on_update` publica el motivo como **Comment nativo**
(`Document.add_comment`) en el Timeline del mismo Risk y **limpia** `update_note`. Varios cambios materiales en un
save → **una sola nota → un solo Comment**. La **creación inicial no exige nota** (la identificación queda en
`identified_on` + origen del Assessment + evento de creación nativo); no se fabrica un Comment artificial.
**Frontera:** Activity/`Version` = auditoría técnica de campos; el **Comment** = motivo funcional del cambio.

### D7b — Riesgos no anticipados (escape hatch)
Un riesgo no anticipado puede existir como `PMO Project Risk` **manual**: (a) añadiendo una fila manual al
Assessment (sin `question_code` → genera un riesgo `is_manual`), o (b) creando directamente un `PMO Project Risk`
(sin `assessment`). No obliga a inventar una pregunta del cuestionario.

### D8 — Registro y navegación (UX final)
Reporte **`PMO Project Risk Register`** (Script Report P4-safe): **vista consolidada cross-project** sobre los
`PMO Project Risk` visibles (resuelve visibilidad por Project; no descubre riesgos/Projects ocultos). Filtros:
project / status / exposure. UX (workspace *PMO Governance*): card **Gestión de riesgos** (Evaluación de riesgos +
Riesgo del proyecto + Registro de riesgos) y card **Configuración de riesgos** (catálogo de preguntas). En el form
nativo de Project: botones **Realizar/Ver evaluación de riesgos** y **Gestionar riesgos** (lista filtrada por el
Project) + indicadores derivados; y una **sección Riesgos en Project Control** que reutiliza las mismas señales
(`pmo.risk_signals`, fuente única de cálculo). Print Format estándar de `PMO Project Risk` que reutiliza
Version/Comment nativos (sin historia paralela). Terminología visible en español (i18n); nombres internos intactos.

### D9 — P4 heredado del Project (assessment + risk) y sin P4 (catálogo)
`PMO Project Risk Assessment` y `PMO Project Risk` heredan la visibilidad del Project (read = Project visible;
write = project writer; Executive read-only; share denegado; fail-closed sin Project). El catálogo
`PMO Risk Question` es master global sin P4 (solo capacidad de rol).

### D10 — Semilla idempotente por el mecanismo versionado de la app
El catálogo inicial se siembra con un **patch post-model-sync idempotente** (`seed_risk_questions`, seed-if-empty
por `code`): nunca sobrescribe ni borra ediciones del admin (catálogo vivo). No se usan fixtures para las
preguntas (evita pisar ediciones en cada migrate).

## Frontera con Change Control (Risk ≠ Change Control)

`may_affect_controlled` es **solo señal**: no crea ni referencia un `PMO Change Request`, no mueve economía ni
baseline. Un riesgo que al materializarse exija cambiar un compromiso se atiende por Change Control v2
(ADR-0015), como cualquier otro cambio. Esta frontera es dura e intencional.

## Fuera de alcance (R1)

Cuantitativo / Monte Carlo · scoring numérico · matrices > 3×3 · risk appetite / tolerancias / umbrales ·
estrategia de respuesta estructurada (Avoid/Mitigate/Transfer/Accept) · triggers · riesgo residual/secundario ·
costo de respuesta · workflow de status / ciclos programados / notificaciones · motor de reglas de aplicabilidad
· plantillas por industria · DocType de secciones (Select por ahora) · link Risk → Change Request (diferido;
`may_affect_controlled` sigue siendo solo señal) · **PHI** (ADR-0013, bloqueado). *(Las señales de Risk hacia
Project Control SÍ se implementaron en el pase UX final — ya no están diferidas.)*

> **Nota sobre el `PMO Project Risk` histórico (commit `3523371`).** El modelo corregido introduce un
> `PMO Project Risk` como **entrada de Risk Register alimentada por la identificación**, reutilizando del diseño
> histórico su idea de entidad-por-riesgo (identidad, status, prob/impact/exposure, owner, response). **NO** se
> recupera su parte innecesaria: `response_strategy` estructurado, estado `Transferred`, ni su naturaleza
> puramente free-form desligada del cuestionario.

## Consecuencias

- Risk Analysis pasa de diferido (ADR-0014 D6) a **implementado ligero**, alineado con PMI/PMBOK e ISO 31000
  (identificar → evaluar cualitativamente → responder → monitorear) sin subsistema cuantitativo.
- Separación limpia: el **cuestionario/Assessment** identifica y evalúa *as identified*; el **`PMO Project Risk`**
  es el registro vivo con estado vigente; la **historia es nativa** (`Version`/Timeline) y el **motivo** del cambio
  se publica como **Comment nativo** (Opción E; sin child de historia paralela).
- El registro es utilizable para seguimiento con identidad e historia por riesgo, sin ERM ni cuantitativo.
- La extensibilidad de secciones queda abierta sin comprometer simplicidad ni histórico.

## Nota — replanteamiento posterior de la UX global de PMO

La **UX global de la app PMO** (navegación, coherencia entre módulos, descubribilidad) será objeto de un
**replanteamiento integral posterior** ("rescate PMO"), como bloque/proyecto propio. R1/Risk queda funcionalmente
cerrado con este diseño; su UX podrá reencuadrarse dentro de ese replanteamiento. No se abre aquí un ADR del
rescate porque su solución aún no está diseñada.
- Las señales de Risk hacia Project Control quedan **habilitadas** (hay exposure/estado consultables) pero
  **no** conectadas: se abordarán en una iniciativa posterior.
