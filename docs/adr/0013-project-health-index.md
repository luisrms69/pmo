# ADR-0013: PMO Project Health Index (PHI) — indicador compuesto interno (marco)

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Ciclo:** posterior a v0.16.0 (sobre ADR-0011/0012)

## Contexto
Tras cerrar el contexto canónico (ADR-0011) y la economía (ADR-0012), Project Control produce muchas señales
objetivas (slip, forecast, vencidas, madurez de planeación, capacidad, costos autorizados vs registrados,
gobernanza) pero **no hay un resumen de una mirada** del estado de un proyecto ni una vista comparable de
portafolio. `pmo/health.py` ya es la **fuente única de salud** (semáforo) y **no se toca su semántica** en
este ADR.

Este ADR fija el **marco** del PHI. El **catálogo de checks, umbrales y critical checks** se define en un ADR
separado (**ADR-0013a**) **antes** de cualquier implementación (D9).

## Problema
Sin un índice compuesto, cada quien "lee" el estado del proyecto a mano y el portafolio no es comparable de un
vistazo. Un índice mal diseñado, en cambio, introduce falsa precisión, diluye eventos críticos y puede
contradecir al semáforo existente.

## Decisiones

### D1 — PHI vive en `health.py`, en coexistencia
PHI reutiliza las señales de dominio ya existentes (compone, no recalcula — ADR-0011 D2). **No cambia la
semántica del health/semáforo actual**; lo deja intacto. Tras validar PHI con proyectos reales se decidirá,
en un ADR posterior, si el semáforo pasa a ser una proyección del PHI.

### D2 — Alcance por acceso, no por usuario
El **PHI completo (incluida la dimensión Financial) se muestra únicamente a usuarios con acceso económico**
(gate de ADR-0012: rol económico AND Project READ). Los usuarios operativos siguen viendo el **health actual**,
no un PHI recortado. El PHI **no varía según el usuario**: o existe completo, o no existe. Durante la
coexistencia, para el usuario con acceso económico **PHI es el titular** y el semáforo actual queda como
detalle de diagnóstico (mismo cómputo, sin cambiarlo).

### D3 — Cinco dimensiones, pesos constantes versionados
Schedule 30 · Execution 25 · Resources 20 · Financial 15 · Governance 10, como **constantes documentadas en
código** (no Settings en v1). Son **initial calibration weights**: una **hipótesis inicial explícita**, no
pesos validados; los datos de proyectos reales decidirán si sobreviven. Recalibrar = cambio versionado
(CHANGELOG), no configuración en runtime. Se evaluará hacerlos configurables **solo si** la calibración lo
justifica.

### D4 — Frontera Schedule ↔ Execution (sin doble conteo)
Ninguna métrica aparece en dos dimensiones. Regla:
- **Schedule = proyección del plan** (¿terminaremos a tiempo?): slip vs baseline, forecast vs fecha
  comprometida, riesgo de fecha fin. Mira al **futuro**.
- **Execution = entrega al corte** (¿estamos entregando lo planeado a la fecha?): tareas que debían estar
  terminadas al Status Date vs terminadas, avance, y **tareas vencidas** (déficit de entrega). Mira al
  **presente/pasado**.

"Vencidas" pertenece a **Execution**, no a Schedule. Cada check se asigna a exactamente una dimensión y así se
documenta en el catálogo (ADR-0013a).

### D5 — Evaluabilidad por check; cuatro estados; cobertura separada del score
La evaluabilidad es **por check**, no por dimensión. Cada check está en uno de cuatro estados:
- **EVALUABLE** — aplica y hay evidencia confiable (aporta `s_c`);
- **N/E** — *debería* poder medirse pero falta referencia/evidencia confiable (fuera del score; **reduce
  Evidence Coverage**);
- **N/A** — legítimamente **no aplica** en ese contexto/momento (fuera del score y **fuera** del universo
  aplicable; **reduce Model Scope**, no la evidencia);
- **INCONSISTENT** — condición evaluable **negativa**/control roto (participa `s=0`; no se convierte en N/E).

La ausencia o cobertura insuficiente de baseline vuelve **N/E/N/A** únicamente a los **checks
baseline-dependent**, no a toda una dimensión (p. ej. Schedule sigue evaluable vía la desviación
vs compromiso, que no depende de baseline). Los pesos se renormalizan **a nivel de check** (por su peso
original `P_c`), de modo que un check N/E/N/A **no** devuelve peso completo a su dimensión.

El PHI **no siempre existe**. Se separan tres medidas (definiciones exactas en ADR-0013a):
`PHI` (desempeño de lo efectivamente medido) · `Evidence Coverage` (evidencia presente / peso aplicable) ·
`Model Scope` (peso aplicable / peso activo de la calibración). Cuando no hay base suficiente, **no se
publica número ni banda**: se muestra **Diagnostic only** con dimensiones/estados, ambas coberturas y las
condiciones críticas. **ADR-0013a** fija el **piso estructural** (incluida baseline vigente) y los mínimos
de cobertura; este ADR no fija umbrales concretos.

### D6 — Critical checks / caps (solo clasificación categórica)
Un subconjunto de checks se declara **crítico**. Si un check crítico está en **rojo**, la **clasificación
categórica (banda) del PHI queda con techo** (p. ej. no puede ser mejor que `Deviated`/`At Risk`). Regla fija
de v1:

> El cap modifica **exclusivamente la clasificación categórica** del PHI, **no** el score matemático. La UI
> debe mostrar explícitamente cuándo la clasificación fue limitada por un critical check, y su causa.

Ejemplo:

```text
PHI 92 / 100
AT RISK
Critical cap: Authorized economic reference inconsistent
```

El `92` sigue siendo el resultado ponderado (trazabilidad del cálculo intacta); `AT RISK` expresa que existe
una condición que impide considerarlo sano. **No se manipula el número.** Reglas del mecanismo:
- un check crítico en **N/E no capea** (no se capa sobre lo desconocido);
- **`critical condition detected` ≠ `critical cap applied`**: la condición se reporta **siempre** (aun en
  Diagnostic only, cuando no hay banda que capar); el cap solo si existe banda;
- varios críticos → gana el techo de banda más bajo;
- **la ausencia de baseline vigente NO es un critical cap**: es una **condición estructural** que fuerza
  **Diagnostic only** (no hay banda) — la mide GOV-1, que es **control estructural fuera del scoring**, no un
  check de Schedule.

La *lista* concreta de checks críticos se fija en ADR-0013a. El **mecanismo** queda fijado aquí.

### D7 — Referencia temporal explícita por dimensión
Cada dimensión **declara explícitamente su referencia temporal** (no se asume una global):
- **Schedule** y **Execution** se evalúan **al Status Date** (vía `build_status_report`, P4).
- **Financial** evalúa el **estado económico actual** (Costs no tiene snapshot histórico — ADR-0012 D6).
- **Resources** y **Governance** conservan la **temporalidad de sus señales canónicas**, que deberá
  **documentarse en el catálogo de checks** (ADR-0013a) — no se garantiza aquí una temporalidad que el backend
  quizá hoy no cumpla.

### D8 — Portafolio por summaries ligeros
El heat map/PHI de N proyectos **consume resúmenes del status engine** (ADR-0011 D6), **no** ejecuta
`build_project_control` integral N veces. El PHI tiene un **modo de cálculo ligero** para portafolio.

### D9 — Catálogo de checks en ADR-0013a, antes de implementar
Este ADR fija el **marco** (dimensiones, pesos, frontera, N/E, caps, gating, temporalidad, portafolio). Los
**8–12 checks concretos**, su conversión check → {verde/amarillo/rojo, puntos} y la **lista de críticos** se
definen en **ADR-0013a**, que debe cerrarse **antes de cualquier implementación** del scoring. No se diseñan
umbrales mientras se programa.

### D10 — Sin EVM y sin scatter en v1; disclaimer metodológico
No PV/EV/AC ni CPI/SPI (Financial es guardrail — ADR-0012). El **scatter** (PHI × margen % × ingreso) queda
fuera de v1 (arrastra el mismo gating de margen). Disclaimer obligatorio: "PMO Project Health Index es un
indicador compuesto interno de Buzola, inspirado en prácticas de project health assessment (ISO 21502/21508,
PMI Earned Value Management, APM Project Health Check); no constituye un índice oficial emitido por dichas
organizaciones".

## Fuera de alcance
EVM real; scatter v1; pesos configurables en runtime; cambiar la semántica del health/semáforo actual; PHI
para usuarios sin acceso económico; ponderación por tipo de proyecto; y el **catálogo de checks/umbrales**
(ADR-0013a).

## Consecuencias
- Un resumen de una mirada + heat map comparable, **sin datos ni motores nuevos**.
- Coexistencia reversible: si PHI no convence en calibración, se retira sin tocar el health existente.
- Los eventos críticos **no se diluyen** (D6); el índice no puede clasificar como sano un proyecto quebrado en
  una dimensión crítica, y el número permanece auditable.
- El costo real del trabajo es **definir y calibrar los checks** (ADR-0013a), no la plomería.

## Alternativas descartadas
- **Reemplazar el semáforo ya** → riesgo de dos señales en conflicto sin validación (se pospone, D1).
- **Pesos configurables / "validados" desde v1** → configuración/permisos/variabilidad antes de saber si los
  pesos sirven; se declaran hipótesis inicial (D3).
- **PHI recortado por usuario** → mismo proyecto con dos números; se rechaza (D2).
- **Cap que modifica el número** → pierde trazabilidad del cálculo; el cap es solo categórico (D6).
- **Ausencia de baseline como critical/penalización de Schedule** → es una **condición estructural** que
  fuerza Diagnostic only (la mide GOV-1, control fuera del scoring), no un check ni un cap de Schedule (D5/D6).
- **Garantía temporal global ("todo al corte salvo Financial")** → asume temporalidad no verificada de
  Resources/Governance; cada dimensión la declara (D7).
- **Promedio puro sin caps** → diluye eventos críticos; se rechaza (D6).

## Criterios de aceptación
- PHI se computa en `health.py` componiendo señales existentes; el health actual queda intacto.
- Se muestra solo con acceso económico y no varía por usuario.
- Pesos como constantes versionadas declaradas como hipótesis inicial; evaluabilidad por check (EVALUABLE/
  N/E/N/A/INCONSISTENT) renormalizando por `P_c`; caps por check crítico que afectan **solo la banda**, con
  motivo visible y número preservado.
- Cuando no hay base suficiente (piso estructural o mínimos de cobertura), el resultado es **Diagnostic only**
  (sin número ni banda), no un score fabricado. Piso estructural y umbrales se fijan en ADR-0013a.
- Sin doble conteo Schedule/Execution (cada check en una sola dimensión).
- Cada dimensión declara su referencia temporal; portafolio por summaries.
- El catálogo de 8–12 checks, umbrales y críticos se cierra en **ADR-0013a antes** de implementar el scoring.
