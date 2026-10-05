# ADR-0017 — Schedule Intelligence (análisis de cronograma read-only)

**Estado:** aceptado · **Fecha:** 2026-09-30 · **Sustituye/relaciona:** ADR-0001 (Gantt/`lft`),
ADR-0004 (baselines), ADR-0006 (Status Date), ADR-0007 (fechas comprometidas), ADR-0009 (forecast y
desviaciones). Issue relacionado: #9 (CPM, diferido).

## Contexto

El cliente pide capacidades tipo Microsoft Project (reacomodo automático por dependencias). Al auditar el
código real se confirma un hecho decisivo: **ERPNext ya reprograma dependientes de forma nativa y
server-side** (`Task.on_update → reschedule_dependent_tasks`): cascada **FS, en días NATURALES, solo
tareas `Open`, recursiva**, mutando `exp_*`. Por tanto, construir un rescheduler FS propio sería
redundante y chocaría con el motor nativo.

El valor diferencial de PMO **no** es mover fechas, sino **diagnosticar y hacer visible lo que la cascada
nativa no entiende**: calendario laboral, múltiples predecesoras, ciclos, `pmo_deadline`, holgura y ruta
crítica. Este subsistema se llama **Schedule Intelligence** y es **estrictamente read-only**.

## Semántica de fechas vigente (NO se cambia)

| Concepto | Campo | Significado | Mutabilidad |
|---|---|---|---|
| Forecast / plan vigente | `Task.exp_start_date` / `exp_end_date` (Datetime) | Plan calculado; **se desplaza** con dependencias/edición y con la **cascada FS nativa** de ERPNext | Mutable (incl. auto-cascada nativa) |
| Real | `Task.act_start_date` / `act_end_date` / `actual_time` | Ejecución real (Timesheet/sistema) | **Inmutable** (read-only, sistema) |
| Baseline | `PMO Project Baseline.snapshot` (submitted + hash) | Foto aprobada del plan | **Inmutable** (rebaseline gobernado, ADR-0004/0005) |
| Deadline de Task | `Task.pmo_deadline` (Date) | Compromiso/fecha límite de la tarea; **no es constraint**, no mueve el programa | Mutable (edición) |
| Compromiso de proyecto | `Project.pmo_committed_end_date` (Date, read_only) | Fin comprometido; **no se desplaza solo** | Gobernado (endpoint `change_committed_end_date`) |
| Fecha de corte | `Project.pmo_status_date` (Date, ≤ hoy) | As-of del reporte | Mutable (validada) |

## Decisiones

1. **Read-only.** Schedule Intelligence **NUNCA** escribe `exp_*`, baseline, `pmo_deadline`,
   `pmo_committed_end_date`, actuals, PHI, Governance ni Change Requests. Solo lee y **compone señales**.
2. **Sin segundo modelo de forecast.** Se analizan directamente los `exp_*` persistidos. **No** se crean
   campos ni DocTypes de "forecast proyectado"; cualquier cálculo de red es **en memoria, efímero**.
3. **Cascada FS nativa: no se toca.** PMO **no** construye un rescheduler FS en esta etapa; solo
   **diagnostica** las limitaciones de la cascada nativa (días naturales, solo `Open`, multi-predecesora
   naïve, ignora calendario/`pmo_deadline`/constraints).
4. **Automation diferido y condicional.** Un eventual motor de escritura (constraints, días hábiles,
   preview) se evalúa **después** de Intelligence y solo si el cliente necesita más que la cascada nativa;
   exigirá su propio ADR de política escritura ↔ baseline/Change Control.
5. **Dependencias = FS implícito.** `Task Depends On` solo tiene `task` (sin tipo ni lag). Se interpreta
   **FS**. Tipo/lag (SS/FF/lead-lag) quedan **diferidos** (extensión de modelo futura).

### Duración canónica

- **Duración = días HÁBILES entre `getdate(exp_start_date)` y `getdate(exp_end_date)`**, inclusiva en
  ambos extremos. **`expected_time` NO es duración** (es esfuerzo en horas) y no se usa para esto.
- **Normalización a fecha:** todo el análisis de red opera a `getdate()` (se descarta la hora de los
  Datetime).
- **Calendario laboral:** `Project.holiday_list` → fallback `Company.default_holiday_list` (ambos
  nativos), resuelto por el `company` del Project. Se reutiliza `is_holiday` de ERPNext.
- **Degradación segura:** si **no** hay calendario resoluble, el análisis **no lanza**; marca
  `calendar_available = False`, cae a **días naturales** para lo que lo requiera y **omite** los chequeos
  que dependen estrictamente del calendario (p. ej. "día no laborable", "divergencia hábil vs natural"),
  surfacándolo como señal. **Project Control nunca debe romper.**

### Casos de red

- **Grupo/fase (`is_group`)**: rollup; **no** es nodo programable (sus fechas derivan de hijos).
- **Milestone (`is_milestone`)**: duración 0.
- **Fechas incompletas** (falta `exp_start` o `exp_end`): **no** se inventa duración; se reporta como
  **gap de planeación** y la tarea se excluye del forward-pass.
- **Completed / Cancelled / Template**: fuera de la red activa.
- **Iniciadas** (`act_start_date` / `% progreso`): se respeta el pasado; el análisis no reinterpreta ni
  "mueve" lo ya ocurrido.

### Reconciliación de "fines" (diagnóstico, no sustitución)

Se exponen y comparan **sin sustituir ninguno**:
- `max EF` calculado por la red (forward pass, días hábiles);
- `max(Task.exp_end_date)` (forecast nativo, cascada en días naturales);
- `Project.expected_end_date`.
Las divergencias son **señal de diagnóstico** (el plan no respeta la red, o la cascada natural-day difiere
de la hábil), nunca una corrección automática.

### CPM / holgura (I.2 implementado; ruta crítica dedicada en I.3)

- El ancla del backward pass es el **`max EF` de la red** (las Tasks sumidero describen la red, **no** el
  compromiso). Son **señales separadas**, nunca el ancla: **margen vs `pmo_committed_end_date`**;
  **deadline incumplido = `EF > pmo_deadline`** (el forecast calculado ya excede el compromiso, no `LF`);
  y **margen al deadline = distancia hábil `pmo_deadline − EF`** (positiva = colchón). **Criticidad =
  `slack ≤ 0`** (sin umbral arbitrario). Una eventual variante CPM *restringida por deadline* (anclar el
  backward en `pmo_deadline`) sería un cálculo **aparte** y **no** forma parte de I.2.
- **I.1 construye el forward pass** (ES/EF en días hábiles) como infraestructura común. **I.2 añade el
  backward pass (LS/LF)**, **holgura total** (`span(EF, LF)`), **holgura libre** (contra el ES más temprano
  de las sucesoras; terminal → holgura total) y la marca de criticidad. Ciclos → red **no evaluable** para
  holgura; fechas incompletas → **excluidas** (se cuentan, no se inventan); sin calendario → días naturales
  con bandera. La vista dedicada de **ruta crítica / visualización** queda a **I.3**.

## Alcance por etapas

- **I.0** — este ADR + fundamento (duración/calendario/forward-pass). *(esta iteración)*
- **I.1** — Diagnóstico de integridad del programa (read-only). *(implementado)*
- **I.2** — Slack / Float (backward pass + holgura total/libre, read-only). *(implementado)*
- **I.3** — Critical Path: interpretación/visualización del CPM de I.2 — resaltado en el Gantt propio de
  Estado, secuencia(s) legible(s) de la ruta, detalle ES/EF/LS/LF por tarea crítica, ventana y duración.
  Multi-rama = múltiples rutas (no se inventa una cadena única). Sin motor ni semántica nueva.
  *(implementado; cierra issue #9)*
- **Schedule Automation** — *(diferido y condicional; requiere ADR propio)*.

### Calendario del cronograma (Schedule Readiness)

Capa READ-ONLY (`schedule_readiness`) que indica si el cálculo en días hábiles es **confiable**. No es un
onboarding: se limita al **calendario**. Precedencia **explícita**: `Project.holiday_list` **prevalece**;
si existe pero **no cubre** el periodo del proyecto (min `exp_start` … max `exp_end` de tareas activas),
**no hay fallback silencioso a Company** — se marca *cobertura insuficiente* y debe corregirse esa lista.
Solo si el Project no tiene lista se usa `Company.default_holiday_list`. Estados (label y severidad resueltos
en el dominio, SSOT): **ready** (listo, días hábiles), **missing** (no configurado → días naturales),
**insufficient_coverage** (la lista no cubre todo el periodo). La UI lo muestra como **"Calendario del
cronograma"** y **absorbe** los avisos repetidos de "sin calendario" de las secciones de Estado. No escribe
nada: el usuario configura la Holiday List de forma nativa.

### Clasificación: fuente única de verdad (SSOT)

- **Toda decisión de clasificación/severidad vive en el dominio** (`pmo/scheduling.py`): `is_critical`,
  `deadline_breach`, `slack_sev`/`deadline_sev` por tarea, `severity` de márgenes y `sev` por métrica en
  los resúmenes. Los templates **no** evalúan umbrales (`<= 0`, `< 0`, `count > 0`): solo mapean el token
  de severidad (`ok`/`warn`/`bad`) a una clase CSS mediante un macro `sevcls`. Así el criterio no se
  duplica ni se desincroniza entre Python y HTML.
- Al centralizar se corrigieron dos coloreados engañosos que vivían en el template: **holgura mínima = 0**
  es el estado NORMAL (existe ruta crítica) → `ok`, no rojo; y **margen a deadline = 0** (EF == deadline,
  se cumple justo) → `ok`, no incumplido. Incumplido es estrictamente `EF > deadline` (margen < 0).

### Terminología de usuario (sin jerga)

La UI evita "red/network": secciones **"Revisión del cronograma"** (I.1), **"Holgura de tareas"** (I.2) y
**"Ruta crítica"** (I.3, término estándar que el cliente MS Project reconoce). "Fechas incompletas" →
"tareas sin fecha de inicio o fin"; "ventana crítica" → "periodo de la ruta crítica". El código interno
puede seguir usando network/grafo.

## Consecuencias

- Mejora ejecutiva real sin cambiar la filosofía de fechas ni introducir ambigüedad.
- La capa de dominio (`pmo/scheduling.py`) es reutilizable por I.2/I.3 y por reportes.
- No añade DocTypes, custom fields, Property Setters ni patches; no toca core.
