# ADR-0013a: PMO Project Health Index — catálogo y calibración v1 (`phi-v1`)

**App:** pmo · **Estado:** Accepted · **Depende de:** ADR-0013 (marco) · **calibration_id:** `phi-v1`

> Calibración **inicial versionada** (hipótesis explícita, no validada con datos). Recalibrar = cambio
> versionado (nueva `calibration_id` + CHANGELOG), **nunca** configuración en runtime. Reemplaza la calibración
> candidata del borrador (5 dimensiones / pesos 30-25-20-15-10 / piso de baseline), ya obsoleta tras
> implementar Governance (ADR-0014) y Risk (ADR-0016).

## 1. Dimensiones con peso (Σ = 100)
| Dimensión | Peso | Justificación |
|---|---:|---|
| **Execution** | **50** | Entrega al corte: el dato más directo de salud. Mayor peso. |
| **Schedule** | **35** | Trayectoria a tiempo (baseline + compromiso). |
| **Governance** | **15** | Higiene de controles PMO (motor ADR-0014). |

**Financial, Resources y Risk NO puntúan** (guardrails/caps, §4). Motivo: sus señales solo permiten
condiciones **inequívocas** (sobrecosto, sobreconsumo, inconsistencia, riesgo alto no gestionado), no un check
de salud bilateral sin fasar el plan ni EVM.

**Pesos capturables (única calibración en runtime).** Los **pesos de dimensión** viven en **PMO Settings**
(Single): `Execution Weight` y `Schedule Weight` son capturables (PMO Manager / System Manager); `Governance
Weight` se **calcula** (`100 - Execution - Schedule`) y valida `Execution + Schedule < 100` y `Governance > 0`.
Defaults `50 / 35 / 15`. El resto de la calibración (thresholds, bandas, caps, gates) permanece **en código**
(`pmo/health.py`); PMO Settings **no** es un catálogo general. `compute_phi` es puro: recibe los pesos; el
adaptador los lee de Settings con fallback a defaults.

## 2. Catálogo de checks (scoring)
| Check | Dim | Peso | Verde 1.0 | Amarillo 0.5 | Rojo 0.0 | N/A | N/E |
|---|---|---:|---|---|---|---|---|
| **EXE-1** entrega al corte | Execution | 50 | `done/due ≥ 90%` | `70–90%` | `< 70%` | `due==0` | sin baseline |
| **SCH-1** slip vs baseline (norm.) | Schedule | 20 | `slip/dur ≤ 0` | `≤ 10%` | `> 10%` | — | sin baseline/duración |
| **SCH-2** slip vs compromiso (días) | Schedule | 15 | `≤ 0` | `1–10` | `> 10` | sin `pmo_committed_end_date` | — |
| **GOV-1** controles requeridos | Governance | 15 | `cumplidos/req == 1` | `≥ 0.5` | `< 0.5` | `req==0` | — |

- `done/due` = `completed_by_cutoff / baseline_due_by_cutoff` (`build_status_report`).
- `slip/dur` = `final_date_slip_days` / duración del snapshot de baseline (inicio→fin del MISMO snapshot).
- `req/cumplidos` desde `_evaluate/_facts`: estados `completo`(=cumplido) y `pendiente` cuentan como requeridos;
  `no_aplica` se excluye.
- `s_c`: verde 1.0 / amarillo 0.5 / rojo 0.0.

## 3. Matemática (renormalización por check)
```
APPLICABLE       = Σ peso {EVALUABLE, INCONSISTENT, N/E}
EVIDENCE_PRESENT = Σ peso {EVALUABLE, INCONSISTENT}
PHI              = round(100 × Σ(peso·s_c) / EVIDENCE_PRESENT)     (sobre EVALUABLE + INCONSISTENT)
Evidence Coverage = EVIDENCE_PRESENT / APPLICABLE
Model Scope       = APPLICABLE / 100
```
`N/A` sale de APPLICABLE (baja Model Scope). `N/E` queda en APPLICABLE pero no en EVIDENCE_PRESENT (baja Evidence
Coverage).

### 3.1 Gates de emisión (qué se publica)
Se publica número **solo** si se cumplen los tres:
1. **No exento** (si exento → `applicable=False, phi=None, reason="governance_exempt"`).
2. **EXE-1 EVALUABLE** — Execution es el **ancla** de la salud integral. Si EXE-1 es `N/A` o `N/E` →
   `phi=None, reason="execution_not_evaluable"` (Diagnostic only). Evita el "promedio de lo que casualmente hay"
   (p. ej. PHI alto solo con Governance). Esto **subsume** el antiguo cap estructural de baseline: sin baseline,
   EXE-1 es N/E → Diagnostic only (la condición `governance_baseline_missing` se **reporta**, pero ya no capa
   una banda inexistente).
3. **Model Scope ≥ 0.50** — si no → `phi=None, reason="insufficient_model_scope"`.

Backstop: `EVIDENCE_PRESENT == 0` → `phi=None, reason="insufficient_evidence"` (inalcanzable si EXE-1 evaluable).
En todos los "sin número" se conservan dimensiones/checks/**condiciones** para diagnóstico.

### 3.2 Cobertura como etiqueta (no gate por sí sola)
`coverage_level` desde Evidence Coverage: **≥0.80 sufficient · 0.60–0.79 partial · <0.60 insufficient**. Se
muestra JUNTO al número (Evidence Coverage y Model Scope se comunican **separados** del score). No decide por sí
sola la emisión (los gates de §3.1 sí).

## 4. Guardrails / critical conditions (NO puntúan; §5 el cap)
| Código | Fuente | Disparo | Cap |
|---|---|---|---|
| `economic_reference_inconsistent` | `get_authorized_economics.reason=="inconsistent"` | referencia económica inconsistente | **techo At Risk** |
| `high_exposure_risk_unmanaged` | `risk_signals` | `high_exposure>0` **y** (`no_owner>0` ∨ `no_response>0`) | **techo At Risk** |
| `governance_baseline_missing` | estado | `started` **y** sin baseline vigente (proyecto PMO) | Diagnostic only (subsumido por §3.1: EXE-1 N/E) — se **reporta** |
| `cost_overrun` | costos nativos | `comparable_cost > authorized_cost` (`>0`) | condición (sin cap v1) |
| `effort_overrun` | esfuerzo | `actual_hours > budget_hours` (Σ `expected_time`) | condición (sin cap v1) |

`comparable_cost = total_costing_amount + total_purchase_cost` (labor+externo real; excluye material). Los
overrun marcan `before_completion` cuando `percent_complete < 100`. Umbrales de cap severo para overrun quedan
**pendientes de justificación empírica** (no se capan en v1).

## 5. Bandas y caps
- Bandas sobre el PHI matemático: **On Track ≥ 80 · At Risk 50–79 · Deviated < 50**.
- Se exponen **`band_raw`** (banda antes de cap) y **`band`** (después de cap) para trazabilidad UI.
- Un cap (§4) empeora **solo la banda** a techo `At Risk` cuando el score daría `On Track`; **nunca** modifica el
  número ni fuerza `Deviated`. Si el score ya es `At Risk`/`Deviated`, el cap no altera nada (se reporta la
  condición). Coherencia verificada con 50/35/15: EXE rojo solo → 50 (At Risk); EXE+SCH rojo → 15 (Deviated);
  GOV rojo solo → **85 (On Track)** — decisión: una deficiencia de Governance **por sí sola** puede seguir siendo
  On Track (es higiene, peso 15); la única falla estructural que impide número (baseline faltante) se maneja por
  el gate de emisión (§3.1), no por peso.

## 6. Comparabilidad de portafolio
`portfolio_comparable = Model Scope ≥ 0.85 y Evidence Coverage ≥ 0.90`. Por debajo, el número es **provisional**
(no comparable en ranking), pero se emite igual (no "sin número"). Validación real: los proyectos QA sin
baseline/compromiso caen a Model Scope 0.35–0.85 → provisional, como corresponde.

## 7. Elegibilidad
- Exento (`is_governance_exempt`) → `applicable=False, phi=None, reason="governance_exempt"`.
- Sujeto a PMO con deficiencias → PHI emitido; las deficiencias bajan el score (Governance) y/o disparan
  condiciones/caps. No se esconde un incumplimiento como N/A.

## 8. Model/calibration identity
`phi-v1` versiona: pesos (50/35/15), catálogo (EXE-1, SCH-1, SCH-2, GOV-1), thresholds, guardrails/caps,
reglas de estado/cobertura/emisión y bandas (80/50). Activar Financial/Resources/Risk con peso, añadir checks,
o cambiar pesos/aplicabilidad ⇒ **nueva identidad** (scores no directamente comparables).

## 9. Limitaciones aceptadas v1
- Financial/Resources solo detectan el extremo negativo (overrun) e inconsistencia; no miden eficiencia.
- SCH-1 normaliza por duración del snapshot de baseline (aprox. defendible del span planeado).
- GOV-1 mide cumplimiento de controles, no su calidad interna.
- Sin reproducibilidad histórica: APPLICABLE cambia con la vida del proyecto.

## Criterios de aceptación
- Implementado en `pmo/health.py` (`compute_phi`, puro) + adaptador `pmo/phi.py` (IO) + endpoint
  `get_project_phi` (P4).
- Tests unitarios del compositor (18) + no-regresión de `_health()`.
- Validado sobre proyectos QA reales (`pmo-v16.dev`) sin modificarlos.
