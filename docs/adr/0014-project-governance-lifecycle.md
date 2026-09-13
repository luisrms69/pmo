# ADR-0014: Project Governance & Lifecycle Documentation (con capa ligera de Risk)

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Depende de:** ADR-0002 (P4),
ADR-0004 (Baseline), ADR-0005 (Change Control), ADR-0011 (Project Control canónico) · **No toca:** PHI
(ADR-0013, bloqueado).

## Contexto
`pmo` cubre planeación, capacidad, baselines, control, cambios, economía y reporting, pero **falta el gobierno
documental del ciclo de vida**: autorización de arranque (Charter), cierre formal (Closure), evaluación
posterior (Post-Project Review) y una **capa mínima de análisis de riesgos**. La auditoría confirma que
Baseline (`PMO Project Baseline`, submittable + snapshot + hash + lineage) y Change Control
(`PMO Change Request`, workflow + aprobación + baseline_before/after) resuelven sus dominios, y que **no
existe** nada de riesgo reutilizable en pmo ni en ERPNext. Objetivo: **completar el ciclo reutilizando lo
existente**, sin sistemas paralelos.

Ciclo objetivo: `Proposal ganada → Charter → Baseline → Status/Control → Change Control → Closure →
Post-Project Review → Lessons Learned`.

## Problema
El arranque y el cierre no dejan evidencia congelada; no hay disciplina de riesgos; el expediente del Project
está disperso. El peligro es de **implementación** (motores/aprobaciones/baselines/status paralelos, un Risk
Management pesado, workflows nuevos), no de concepto.

## Decisiones

### D1 — Project nativo es el objeto central; no existe `PMO Project`
Todos los artefactos enlazan al `Project` de ERPNext. Prohibido duplicar customer/company/fechas/Tasks/WBS/
costos/ventas/horas/datos de Proposal: se **referencian** canónicamente.

### D2 — Cuatro artefactos persistentes principales; el resto se deriva/genera
Artefactos de gobierno: **Charter**, **Closure**, **Post-Project Review** (submittable) y **Risk** (no
submittable). **No** se fija un conteo total de DocTypes: los **child DocTypes de soporte** (p. ej.
`PMO Lessons Learned`, o un child para el snapshot de riesgos del Charter/Closure si no se guarda como JSON)
son **detalle de implementación, no una restricción arquitectónica**. Derivado/generado (sin artefacto
propio): estado de ciclo de vida, índice de expediente, cuerpo del Closure (Print Format), señales de
dashboard.

### D3 — Charter mínimo (capturado vs derivado-y-congelado)
- **Capturado:** `sponsor`, `project_manager`, `objective`, `scope_summary`, `deliverables`, `assumptions`,
  `constraints`.
- **Riesgos iniciales:** referencia a `PMO Project Risk` (D6) + **snapshot del set inicial** al emitir.
- **Derivado + snapshot al submit** (patrón `snapshot`+`snapshot_hash` del Baseline): customer/company,
  `pmo_committed_end_date`, economía autorizada (contrato erpnext_proposals), referencia a Proposal/Quotation,
  hitos/equipo iniciales.
- Submittable → evidencia histórica inmutable del arranque.

### D4 — Closure: toda la evidencia se congela al submit (snapshot-only)
- **Capturado:** `final_result`, aceptación formal (`accepted_by`, `accepted_on`), `pending_items_transferred`,
  `closure_observations`.
- **Congelación al submit:** en `on_submit`, `build_project_control` (al corte de cierre) + fuentes canónicas
  **alimentan un snapshot** guardado con hash. Métricas (fechas baseline/comprometida/real + desviación;
  ingreso autorizado/facturado; costo autorizado/real; margen; cambios; horas plan vs real) quedan
  **congeladas**, **no** como campos editables.
- **El Print Format posterior se reconstruye SOLO desde el snapshot congelado**, nunca consultando
  `build_project_control` en vivo. Flujo: `build_project_control → snapshot al submit → Closure congelado →
  Print Format`. Cambios posteriores en el Project **no** alteran retrospectivamente cómo "cerró". No inventa
  métricas.

### D5 — Post-Project Review mínimo (ISO 21513; proporcional)
Distinto del Closure (Closure = *cómo terminó*, factual; Review = *qué aprendimos*, posterior). Capturado:
`objectives_achieved`, `what_worked`, `what_didnt`, `causes`, `recommendations` + **child `PMO Lessons
Learned`** (`area` ∈ {planning, execution, change_control, resources, cost, governance, risk}, `lesson`,
`recommended_action`). Solo la child se estructura (reporting futuro). Puede consultar información viva/
histórica **mientras se prepara**; **al submit queda congelado** (D11). Sin cuestionario extenso.

### D6 — Risk Analysis: capa transversal, artefacto vivo único, sin subsistema
`PMO Project Risk` (no submittable, `track_changes`, link a Project):
`title · description · probability (Low/Med/High) · impact (Low/Med/High) · exposure · owner · response ·
status · change_request (Link opcional) · category (opcional)`.
- **`exposure`** = clasificación cualitativa `Low/Medium/High` **derivada de la matriz 3×3** (probability ×
  impact). **No** se persiste un número ni se trata como score.
- **`status`** = `Open / Mitigating / Closed / Materialized / Transferred` (incluye `Transferred` para alinear
  con la disposición que revisa el Closure).

Integración transversal (gobernada por ESTE ADR):
- **Charter:** los "initial risks" **son** estos registros; el Charter los referencia y **snapshotea** el set
  inicial al emitir. **Una sola captura de riesgo.**
- **Ejecución:** los registros son el **register vivo** persistente (por eso no submittable).
- **Status/Control:** sección `risks` en `build_project_control` con abiertos de exposición alta (compone, no
  reporta aparte). Es **vista viva**, no evidencia congelada.
- **Closure:** los riesgos relevantes (abiertos/materializados/transferidos/cerrados con su disposición) se
  **congelan dentro del snapshot del Closure al submit**; tras el submit el Closure **no** vuelve a consultar
  el register vivo. Flujo: `Risk Register vivo → snapshot de riesgos al submit del Closure → Closure
  inmutable`.
- **Post-Project Review:** consulta riesgos vivos/históricos durante el borrador; **al submit congela** lo
  evaluado (ocurridos/no anticipados, efectividad de respuestas, causas).
- **Change Control:** un riesgo **no** es CR; si la respuesta modifica alcance/fecha/baseline/economía/
  compromiso → se crea un `PMO Change Request` (existente) y el riesgo lo enlaza. **Sin nuevo mecanismo de
  aprobación.**
- **Límites:** sin Monte Carlo, ERM, risk appetite, scores numéricos, workflow, ni baseline/status/
  change-control paralelos.

### D7 — Estado de ciclo de vida derivado, no workflow
Función pura (`pmo/governance.py`, patrón `health.py`) que deriva un estado documental desde hechos
(Project.status + existencia/submit de Charter/Baseline/Closure/Review): `Initiation · Planning ·
Execution/Control · Closing · Closed · Post-project reviewed`. **No** hay workflow ni estado paralelo sobre
Project.

### D8 — Integración en Project Control: índice de expediente
Sección en `build_project_control`: Charter · Baseline vigente · Status/Control · Risks · Change Requests ·
Closure · Post-Project Review, con **enlaces + existencia + fechas**, sin duplicar contenido de otras vistas.

### D9 — Dashboard PMO (sin nuevo dashboard, sin maturity score)
Extender las filas de portafolio existentes (ya con `has_baseline`) con `has_charter`, `needs_closure`
(Completed sin Closure), `needs_review` (cerrado sin Review), `open_high_risks`, `open_change_requests`; una
sección "Project Governance" reusando `_build`.

### D10 — P4 reutilizado (sin segunda política)
Los artefactos heredan la visibilidad del Project vía `pmo.permissions` (`permission_query_conditions` +
`has_permission`), como Baseline/Change Request. Roles: creación/edición por rol PMO operativo;
emisión/aprobación (submit) por rol de gobierno; lectura según P4 + `PMO Executive Access`. El detalle de roles
por DocType se fija en su bloque.

### D11 — Evidencia e historial
Charter/Closure/Review: **submittable** + `track_changes` + **snapshot con hash** (patrón Baseline) +
**referencias canónicas**. **Toda** su evidencia (incluidos los riesgos relevantes del Closure) se congela al
submit; ninguno se reconstruye desde datos vivos posteriormente. No se copian bloques grandes de datos
referenciables.

### D12 — Desacople del PHI
Governance/Risk exponen señales **canónicas y consultables**, pero **no** se crean hooks del PHI ahora. El PHI
sigue **bloqueado** (ADR-0013); estas señales alimentarán su **auditoría final de señales** en su momento. Los
"initial risks" del Charter se resuelven como referencia/snapshot del `PMO Project Risk`, **no** como
dependencia del PHI ni captura independiente.

### D13 — Listo para reporting, sin KPIs ahora
El modelo debe **permitir** después (% con Charter, sin baseline, Completed sin Closure, tiempo de cierre, sin
Review, categorías de lessons, causas recurrentes, riesgos abiertos/recurrentes/materializados, efectividad)
**sin implementar** esos KPIs en esta capacidad; solo no impedirlos.

## Fuera de alcance
`PMO Project`; segundo change-control/baseline/status-reporting; workflow de ciclo de vida; Risk Management
pesado (Monte Carlo/ERM/risk appetite/predictivo/scores numéricos); masters de categorías; review-template
engine; KPIs de reporting; cualquier cambio al PHI.

## Consecuencias
- Ciclo de gobierno completo reutilizando Baseline/Change Control/Project Control/economía/P4.
- Evidencia **congelada e íntegra** de arranque y cierre (Closure inmune a cambios posteriores del Project, y
  con snapshot de riesgos); disciplina mínima de riesgos; expediente indexado.
- Cuatro artefactos persistentes + child de soporte + funciones derivadas: superficie proporcional, sin
  subsistemas.

## Alternativas descartadas
- **Métricas propias/editables en Closure** → duplicación/drift; se rechaza (D4 snapshot-only).
- **Print Format del Closure desde datos vivos** → alteraría retrospectivamente el cierre; se rechaza (D4).
- **Closure/Review consultando el register vivo tras el submit** → contradice la evidencia congelada; se
  rechaza (D6/D11: los riesgos relevantes se snapshotean al submit).
- **Risk submittable o como módulo** → no mantiene riesgos vivos; monstruo; se rechaza (D6).
- **Doble captura de riesgo (Charter vs register)** → se rechaza (D6 registros únicos).
- **`exposure` numérico persistido** → deriva en score sofisticado; se rechaza (D6 clasificación cualitativa).
- **Workflow de ciclo de vida en Project** → status paralelo; se rechaza (D7 derivado).
- **ADR separado para Risk** → fragmenta la arquitectura; Risk es transversal a este ciclo; se integra aquí
  (se creará un ADR aparte solo si surge una decisión arquitectónica realmente independiente).

## Criterios de aceptación
- Existen **4 artefactos persistentes principales** (Charter/Closure/Review submittable + Risk no-submittable);
  los child DocTypes de soporte no cuentan como restricción; el resto es derivado/snapshot/Print Format/sección.
- Charter, **Closure (incluidos sus riesgos relevantes)** y Review congelan **toda** su evidencia por
  snapshot+hash al submit; el Print Format del Closure se reconstruye **solo** desde su snapshot, nunca desde
  datos vivos.
- Risk es no-submittable, ~9 campos, `exposure` cualitativo derivado de matriz 3×3, `status` incluye
  `Transferred`; los initial risks del Charter son registros Risk.
- Toda respuesta de riesgo que toque condiciones controladas pasa por `PMO Change Request`.
- Estado de ciclo de vida es función derivada; no hay workflow nuevo en Project.
- P4 heredado vía `pmo.permissions`; sin segunda política.
- El PHI no se toca; las señales quedan consultables para su auditoría posterior.

## Secuencia de implementación (bloques posteriores)
BLOQUE 2 **Risk** (base de los initial risks) → BLOQUE 3 **Charter** → BLOQUE 4 **estado derivado + índice de
expediente** → BLOQUE 5 **Closure** → BLOQUE 6 **Post-Project Review** → BLOQUE 7 **Dashboard Governance**.
Cada bloque: diseño → implementar → validar → presentar → esperar autorización de commit.
