# ADR-0013a: PMO Project Health Index — catálogo y calibración candidata v1

**App:** pmo · **Estado:** Proposed · **Depende de:** ADR-0013 (marco) · **Naturaleza:** calibración **candidata**
(`initial calibration candidates`), no estándares externos ni valores validados.

> ⛔ **Este ADR NO autoriza implementar el PHI.** Registra la calibración candidata alcanzada **antes** de
> implementar Project Governance & Lifecycle Documentation y Risk Analysis. Tras implementarlas, sus señales
> canónicas nuevas se **auditarán** y solo entonces se revisará si justifican cambios en dimensiones/checks/
> calibración; luego se **congela** la calibración definitiva y recién ahí se implementa PHI + heat map.
> Cualquier cambio derivado de esa auditoría debe ser **deliberado y versionado** (nueva model/calibration
> identity), nunca silencioso.

## Contexto
ADR-0013 fijó el marco (una fuente, muchas vistas; economía bajo gate; coexistencia con el semáforo actual;
sin EVM; no fabricar score sin datos). Este ADR concreta **qué checks, con qué pesos, cómo se agregan, cuándo
se emite y con qué bandas**, para la calibración v1. Se apoya en una auditoría real del backend (señales
existentes de status/baseline/economía/change-control).

## 1. Catálogo v1 y pesos (Σ activo = 80; Resources 20 reservado)
**Scoring (7 checks):** `SCH-1 15 · SCH-2 15 · EXE-2 25 · FIN-1 10 · FIN-3 5 · GOV-2 5 · GOV-3 5`.
**Control estructural (fuera del scoring):** `GOV-1` = existencia de baseline vigente.
**Diagnóstico (fuera del scoring):** `FIN-2` (`Project.gross_margin<0` es normal antes de facturar → no puntúa).
**Resources:** 20% nominal **reservado**, sin checks activos en v1.

## 2. Estados de check
`EVALUABLE` (aporta `s_c`) · `N/E` (debería medirse, evidencia no confiable) · `N/A` (no aplica en el
contexto/momento) · `INCONSISTENT` (evaluable negativo/control roto). `s_c`: verde 1.0 / amarillo 0.5 / rojo 0.0.

## 3. Matemática (peso original `P_c` como unidad; peso activo calibración = 80)
```
APPLICABLE       = Σ P_c {EVALUABLE, INCONSISTENT, N/E}
EVIDENCE_PRESENT = Σ P_c {EVALUABLE, INCONSISTENT}
PHI               = 100 × Σ(P_c · s_c) / EVIDENCE_PRESENT      (EVALUABLE + INCONSISTENT)
Evidence Coverage = EVIDENCE_PRESENT / APPLICABLE
Model Scope       = APPLICABLE / 80
```
`N/A` sale de APPLICABLE (baja Model Scope). `N/E` permanece en APPLICABLE pero no en EVIDENCE_PRESENT (baja
Evidence Coverage). `INCONSISTENT` participa negativamente. Renormalización **por check**: un check N/E/N/A
no devuelve peso completo a su dimensión.

## 4. Emisión (tres salidas)
**Piso estructural:** baseline vigente presente **y** ≥1 check evaluable de Schedule o Execution.
- **Diagnostic only:** falla piso **o** Model Scope < 60% **o** Evidence Coverage < 60% → sin número ni banda;
  se muestran señales disponibles, N/A/N/E, inconsistencias, ambas coberturas y critical conditions.
- **Provisional / project-only:** emite score + banda; **no** entra a ranking de portafolio.
- **Portfolio-comparable:** Model Scope ≥ 85% **y** Evidence Coverage ≥ 90%.

Los cortes 85/90 se conservan formalmente aunque con la granularidad v1 impliquen de facto `MS=100 ∧ EC=100`.
No se codifica como `==100`. Relajar comparabilidad ⇒ nueva calibración.

## 5. Bandas globales (sobre el PHI matemático, antes de caps)
**On Track ≥ 80 · At Risk 50–79 · Deviated < 50.**

## 6. Critical v1 (restrictivo)
- **FIN-3 `inconsistent` → critical cap, techo `At Risk`** (único critical cap congelado).
- **GOV-1 sin baseline → critical condition estructural → Diagnostic only** (no capea banda inexistente).
- `critical condition detected` (se reporta siempre, aun en Diagnostic) ≠ `critical cap applied` (solo con banda).
- Ningún cap fuerza `Deviated`: **Deviated es solo score-driven**.
- **NO critical en v1** (promovibles después con datos): SCH-2, EXE-2, FIN-1, GOV-2, GOV-3. Queda fijado el
  **principio** de que una desviación *suficientemente grave* vs compromiso no debe quedar On Track por
  promedio; el disparo de SCH-2 como cap se decidirá **junto** con su corte rojo empírico (no atado a `>10 d`
  ni a `>0 d`).

## 7. Thresholds candidatos por check (hipótesis v1)

| Check | Verde (1.0) | Amarillo (0.5) | Rojo (0.0) | Evaluabilidad / notas |
|---|---|---|---|---|
| **SCH-1** | `slip/duración ≤ 0` | `0 < r ≤ 10%` | `> 10%` | normalizado por duración de baseline (del snapshot); sin `expected_start_date`/duración → N/E |
| **SCH-2** | `≤ 0 d` | `1–10 d` | `> 10 d` | días absolutos (compromiso puntual); **N/A** si sin `pmo_committed_end_date` |
| **EXE-2** | `≥ 90%` | `70–<90%` | `< 70%` | ratio `completed/due`; **N/A** si `due_by_cutoff==0`; **N/E** si baseline insuficiente |
| **FIN-1** | `≤ 100%` | `>100–≤110%` | `> 110%` | ratio comparable/autorizado; `auth=0 ∧ comp=0`→verde; `auth=0 ∧ comp>0`→rojo; `auth<0`→inconsistencia de datos; **punto-en-tiempo, no forecast**; **N/A** sin propuesta; **N/E** si referencia inconsistente |
| **FIN-3** | consistente | — | `inconsistent` | binario; **N/A** sin propuesta; rojo→INCONSISTENT + cap At Risk |
| **GOV-2** | 0 pendientes formalizados | pendientes sin `High` | ≥1 `High` pendiente | pendiente = `In Review` ∨ (`Approved` ∧ `applied_to_project==0`); usa `workflow_state`+`priority`+`applied_to_project` verificados |
| **GOV-3** | `≥ 90%` | `70–<90%` | `< 70%` | `in_baseline_pct` (forward-coverage, **ciego a borrados**); `<70%` = gate: vuelve N/E a SCH-1/EXE-2 |

**GOV-1** (estructural): baseline presente/ausente; ausencia → Diagnostic only + critical condition.
Todos los cortes de magnitud son **hipótesis de calibración v1**, pendientes de validación con datos reales.

## 8. Clasificación N/A / N/E (congelada v1)
- **N/A:** EXE-2 `due==0` · SCH-2 sin compromiso · FIN-1/FIN-3 sin propuesta.
- **N/E:** SCH-1/EXE-2 con baseline insuficiente (`in_baseline_pct<70%`) · FIN-1 con referencia inconsistente.
- **INCONSISTENT:** FIN-3 con referencia inconsistente.
- No se crean reglas para convertir N/A/N/E en evaluables; la falta se refleja en Model Scope / Evidence
  Coverage y, bajo los mínimos, en Diagnostic only.

## 9. Model/calibration identity
`calibration_id` v1 versiona: pesos, catálogo (7 scoring + GOV-1 estructural + FIN-2 diagnóstico), thresholds,
caps, reglas de estado/cobertura/emisión y `Resources reservado=20`. Activar Resources, reintroducir FIN-2,
incorporar señales de Governance/Risk o cambiar pesos/aplicabilidad ⇒ **nueva identidad**; los scores v1 no
serán directamente comparables con los posteriores.

## 10. Limitaciones aceptadas en v1 (sin acción)
- Portfolio-comparable ≡ 100/100 por granularidad (intencional).
- FIN-1 es punto-en-el-tiempo, no forecast.
- GOV-3 mide drift por adición, no por borrado de tareas del baseline.
- Deterioro disperso-leve y concentrado-grave pueden coincidir en el mismo PHI (tri-estado); solo los critical
  caps distinguen el caso grave.
- Sin reproducibilidad histórica: `APPLICABLE` cambia con la vida del proyecto (temporalidades heterogéneas).

## 11. Secuencia y auditoría final pendiente
El PHI queda **diseñado y documentado**; su implementación está **bloqueada** hasta: (1) implementar Project
Governance & Lifecycle Documentation; (2) implementar Risk Analysis / Risk Management; (3) **auditar** las
señales canónicas nuevas; (4) decidir —deliberada y versionadamente— si Governance/Risk entran al PHI (nueva
dimensión, dentro de una existente, o solo diagnóstico) y cualquier ajuste de calibración; (5) **congelar** la
calibración definitiva; (6) implementar PHI + heat map. **No** se diseñan aquí checks hipotéticos de
Governance/Risk. Nota de integración: los "riesgos iniciales" del futuro Project Charter deberán resolverse
como referencia/snapshot del Risk Register (no una captura de riesgos independiente); el PHI **no** debe crear
dependencia sobre ese campo.

## Consecuencias
- El trabajo de diseño del PHI queda preservado y auditable sin fingir calibración definitiva.
- La implementación no arranca sobre una calibración que sabemos que Governance/Risk pueden mover.

## Criterios de aceptación
- El diseño (estados, matemática, cobertura doble, emisión, bandas, critical v1, thresholds candidatos) queda
  registrado como **candidato**, no validado.
- Queda explícito que este ADR **no** autoriza implementar PHI.
- La calibración definitiva depende de la auditoría final tras Governance + Risk.
