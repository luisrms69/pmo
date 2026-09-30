# ADR-0013b: Financial Health / Salud financiera — señal independiente (calibración `fin-v1`)

**App:** pmo · **Estado:** Accepted · **Relación:** complementa ADR-0013/0013a (PHI) · **calibration_id:** `fin-v1`

> Calibración **NORMATIVA inicial**, **NO derivada de históricos reales**. Thresholds versionados en código
> (`pmo/financial_health.py`), **NO** en PMO Settings. Sujeta a recalibración futura con datos reales.

## Contexto
El PHI v1 deja Financial **fuera del score** (guardrails/caps: sobrecosto, inconsistencia) porque no hay un
check de salud financiera bilateral sin fasar el plan ni EVM. Este ADR define una señal **independiente** de
salud financiera que compara **consumo de costo** vs **avance físico** como cociente point-in-time.

## Decisiones

### D1 — Independiente del PHI
Financial Health **NO** entra al score PHI v1 y **no** varía su cálculo. Es una vista complementaria (se
mostrará al lado del PHI en Resumen/Portfolio, UI aparte). Motivos: pregunta distinta (eficiencia de costo
vs salud de entrega); disponibilidad distinta (requiere economía autorizada + esfuerzo); no debe reducir la
comparabilidad del PHI.

### D2 — Avance = `Project.percent_complete` NATIVO (fuente única, sin recálculo)
```
physical_progress = Project.percent_complete / 100
```
Se usa el **avance oficial nativo de ERPNext, tal como lo calcula según `percent_complete_method`** del propio
Project (Manual / Task Completion / Task Progress / Task Weight). **PMO no interpreta ni recalcula** ese avance:
es la **única medida de avance total canónica** del sistema (la misma que Resumen/Print/Closure ya muestran).
Auditoría previa: no existe en PMO ninguna medida de avance ponderada por esfuerzo; crearla habría introducido
un **segundo** número de avance divergente del mostrado. **NO** se usa `completed_by_cutoff/baseline_due`
(cumplimiento al corte, no scope total) ni se inventa avance/costo planificado al corte.

**Límites heredados (documentados):** con el método por defecto **Task Completion** el avance es por **conteo**
de tareas (ignora tamaño/esfuerzo); si un Project usa **Manual**, el avance —y por ende Financial Health— es
tan confiable como esa captura manual. Financial Health hereda el método configurado; no lo altera.

### D3 — Consumo de costo (fuentes canónicas)
```
cost_consumption = comparable_cost / authorized_cost
```
`authorized_cost` = contrato autorizado (`erpnext_proposals` vía `get_authorized_economics`); `comparable_cost`
= `total_costing_amount + total_purchase_cost` (labor+externo real, excluye material). No se crea cálculo
económico paralelo.

### D4 — Brecha y bandas (normativas v1)
```
cost_gap = (cost_consumption - physical_progress) × 100   (puntos porcentuales)
```
- `cost_gap ≤ +5 pp` → **healthy** (On budget)
- `+5 < cost_gap ≤ +15 pp` → **cost_pressure**
- `cost_gap > +15 pp` → **unfavorable**
(Brecha negativa = favorable → healthy.) Redondeo estable en el corte de banda para evitar ruido de float.

### D5 — Naturaleza (no EVM temporal)
`cost_gap`/razón es **formalmente el inverso del CPI**, PERO **no** inventa costo/valor planificado al corte
ni curva PV fasada: compara **dos fracciones acumuladas en el mismo instante**. Se prohíbe explícitamente el
EVM temporal (S-curve/PV) y el prorrateo de `expected_time` por duración.

### D6 — Casos especiales (precedencia)
1. **inconsistente** (economía) → `unavailable` (no calcular).
2. **sin referencia autorizada** (sin propuesta) → `na` (`no_authorized`).
3. **sobrecosto** (`comparable_cost > authorized_cost`, incluye `authorized_cost=0` con costo>0) → `over_budget`
   (precede a la banda normal).
4. **avance 0% + costo 0%** → `na` (`not_started`).
5. **avance 0% + costo >0** → `unfavorable` (gasto sin avance, sea cual sea el monto).
6. **proyecto terminado** (100%) → se calcula normal (resultado final de costo).
7. **sin baseline** → sí calculable (no lo usa).
8. **PMO-exempt** → sí calculable si hay economía autorizada suficiente (independiente de gobernanza).

### D7 — Salida del motor
`{calibration_id, applicable, state, reason, cost_consumption, physical_progress, cost_gap}`. `applicable` = hay
veredicto (healthy/cost_pressure/unfavorable/over_budget); `False` en na/unavailable.

## Consecuencias
- Señal financiera objetiva y auditable, reutilizando fuentes existentes; sin tocar el PHI.
- Su utilidad depende de la cobertura de `expected_time` y de la existencia de economía autorizada.

## Criterios de aceptación
- Implementado en `pmo/financial_health.py` (`compute_financial_health` puro + adaptador + endpoint P4).
- Matriz QA y casos especiales cubiertos por tests unitarios.
- Thresholds versionados (no en Settings); documentado que la calibración v1 no deriva de históricos.

## Limitaciones aceptadas v1
- El avance hereda `percent_complete_method`: con "Task Completion" (default) es por conteo (ignora tamaño);
  con "Manual" es subjetivo. Financial Health no lo corrige — usa la fuente única del sistema.
- `cost_gap` es CPI-inverso point-in-time (no EVM temporal).
- Sin proyectos reales para calibrar los cortes (+5/+15 pp son normativos).
