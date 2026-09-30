# ADR-0013: PMO Project Health Index (PHI) — indicador compuesto interno (marco)

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted · **Ciclo:** posterior a Governance (ADR-0014) y Risk (ADR-0016)

> Este ADR **consolida y reemplaza** los borradores `Proposed` previos (rama `docs/adr-0013-project-health-index`)
> tras auditar el backend real con Governance y Risk ya implementados. La calibración concreta (checks,
> pesos, thresholds, caps) vive en **ADR-0013a**.

## Contexto
Project Control ya produce señales objetivas (slip, forecast, vencidas, cobertura de baseline, costos
autorizados vs registrados, ciclo de gobernanza, riesgos) pero no había **un resumen de una mirada** ni una
vista comparable de portafolio. `pmo/health.py` es la fuente única del semáforo (ADR-0011 D2) y **no se toca
su semántica**.

## Decisiones

### D1 — PHI vive en `health.py`, compone y no recalcula; coexiste con el semáforo
`compute_phi(signals)` es un **compositor PURO sin IO**: reutiliza señales de dominio ya existentes. Un
**adaptador delgado** (`pmo/phi.py`) las reúne (único punto con IO) y delega el cálculo. El semáforo `_health()`
queda **intacto** (coexistencia; su eventual reemplazo se decidirá tras validar PHI con datos reales).

### D2 — Motor user-invariant; el gate económico es de PRESENTACIÓN
El PHI **no varía según el usuario**: el motor calcula con la existencia real de dato (p. ej. propuesta
vinculada y consistencia económica), **no** según el rol del usuario que consulta. El gate económico de
ADR-0012 (`can_see_project_economics`) se aplica al **mostrar** el detalle financiero, no dentro del motor
(re-resuelve el D2 del borrador, que ataba el PHI al acceso económico del usuario).

### D3 — Elegibilidad binaria: PMO vs exento
Solo dos situaciones funcionales:
- **Sujeto a seguimiento PMO** → tiene PHI. Sus deficiencias de gobernanza **no** eliminan el PHI: se reflejan
  en los checks y **bajan** la calificación (no se crea una tercera categoría). Solo si es técnicamente
  imposible calcular por ausencia extrema de datos, se devuelve `phi=None` con `reason="insufficient_evidence"`
  (excepción **técnica**, no estado funcional).
- **Formalmente exento** (`pmo_governance_exempt` / `is_governance_exempt`) → **no tiene PHI**: `applicable=False`,
  `phi=None`, `reason="governance_exempt"`. No se calcula un PHI reducido ni se renormaliza sin gobernanza (no
  sería comparable). El "Seguimiento básico" de estos proyectos queda fuera de este ADR.

### D4 — Dimensiones con peso vs guardrails/caps
Solo tres dimensiones tienen **peso** (score matemático, Σ=100): **Execution, Schedule, Governance**.
**Financial, Resources y Risk NO tienen peso**: sus señales no permiten un check de salud **bilateral** sin
inventar una referencia temporal (costo/horas planificados al corte) ni EVM. Actúan como **critical conditions
/ guardrails / caps**. Pesos y catálogo concreto: ADR-0013a.

### D5 — Frontera Schedule ↔ Execution (sin doble conteo)
- **Execution** (mayor peso): ¿entregamos al corte lo que debía entregarse? Señal central existente
  `completed_by_cutoff / baseline_due_by_cutoff`. Las **vencidas** pertenecen aquí. Mira al presente/pasado.
- **Schedule**: ¿terminaremos a tiempo? slip vs baseline (normalizado por duración del plan) + slip vs fecha
  comprometida. Mira al futuro. Cada check pertenece a **una** sola dimensión.

### D6 — Governance se compone del motor canónico ADR-0014
Governance se deriva del motor `governance_inbox._evaluate/_facts` (controles Acta/Baseline/Risk/Change/
Closure/Review con estados completo/pendiente/no_aplica). **No** se implementan los GOV-2/GOV-3 hipotéticos del
borrador. `no_aplica` no cuenta como requerido (respeta la temporalidad del ciclo).

### D7 — Estados de check y renormalización por check
Cada check está en uno de cuatro estados: **EVALUABLE** (aporta `s_c`), **N/E** (debería medirse, evidencia no
confiable; baja Evidence Coverage), **N/A** (legítimamente no aplica; baja Model Scope), **INCONSISTENT**
(evaluable negativo; participa `s=0`). Renormalización **por check** (un N/E/N/A no devuelve peso completo a su
dimensión). Para un proyecto sujeto a PMO, un requisito de gobernanza **incumplido** NO se maquilla como N/A:
se refleja como condición negativa en su check (`N/A` significa **no aplica**, no "falta").

### D7b — Execution es el ancla: gate de emisión
Para publicar un número, **EXE-1 (entrega al corte) debe ser EVALUABLE** y **Model Scope ≥ 0.50**. Si Execution
no es evaluable → `phi=None, reason="execution_not_evaluable"` (Diagnostic only): sin la dimensión de mayor peso,
el resultado no es "salud integral" sino "promedio de lo que casualmente hay". Evidence Coverage y Model Scope se
comunican **separados** del score; `coverage_level` (sufficient/partial/insufficient) etiqueta la confianza sin
ser gate por sí solo. Detalle y umbrales en ADR-0013a §3.1–3.2.

### D7c — Pesos capturables (PMO Settings), resto en código
Los **pesos de dimensión** son la única calibración en runtime: viven en **PMO Settings** (Single) — Execution y
Schedule capturables, Governance = `100 - Execution - Schedule` (validado `EXE+SCH<100`, `GOV>0`). `compute_phi`
es puro y los recibe; el adaptador los lee con fallback a defaults `50/35/15`. Thresholds, bandas, caps y gates
permanecen versionados en código (no se convierte PMO Settings en catálogo general).

### D8 — Sin piso universal de baseline
Se **elimina** el piso estructural que forzaba "Diagnostic only" por baseline ausente. Un proyecto PMO sin
baseline **conserva PHI**: la carencia pega en **Governance** (control baseline pendiente) y en una
**critical condition estructural** (`governance_baseline_missing`, cap At Risk); los checks que genuinamente
dependen de una referencia (EXE-1 del baseline; SCH-1 de compromiso o baseline) quedan **N/E** (bajan Evidence
Coverage), sin fabricar ni ocultar.

### D9 — Critical conditions / caps: solo la BANDA, nunca el número
El PHI matemático es **auditable e inmutable**. Un critical cap puede **empeorar la banda** (techo `At Risk`),
nunca modificar el número; **nunca** fuerza `Deviated` (Deviated es solo score-driven). Las condiciones se
**reportan siempre** (incluso sin banda que capar). Catálogo de caps en ADR-0013a.

### D10 — Sin EVM; disclaimer metodológico
No PV/EV/AC ni CPI/SPI. Financial es guardrail (ADR-0012). Disclaimer: "PMO Project Health Index es un
indicador compuesto interno de Buzola, inspirado en prácticas de project health assessment (ISO 21502/21508,
PMI EVM, APM Project Health Check); no constituye un índice oficial de dichas organizaciones."

## Consecuencias
- Resumen de una mirada + base para heat map comparable, **sin datos ni motores nuevos**.
- Coexistencia reversible con el semáforo; los eventos críticos no se diluyen (D9).
- La UI de Project Control y el reporting se deciden **después** de validar el motor (fuera de este ADR).

## Criterios de aceptación
- PHI se computa en `health.py` (`compute_phi`, puro) sobre señales existentes; `_health()` intacto.
- User-invariant; exento → sin PHI; deficiencia de gobernanza baja el score, no elimina el PHI.
- Tres dimensiones con peso (EXE/SCH/GOV); Financial/Resources/Risk como caps/guardrails.
- Estados por check con renormalización; caps solo sobre la banda; número auditable.
- Sin piso universal de baseline; baseline faltante = Governance + condición estructural con cap.
