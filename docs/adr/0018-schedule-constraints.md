# ADR-0018 — Schedule Constraints and Native Rescheduling

**Estado:** aceptado (II.0 — contrato) · **Fecha:** 2026-10-05 · **Relaciona:** ADR-0017 (Schedule
Intelligence, read-only), ADR-0009 (forecast y desviaciones), ADR-0007 (fechas comprometidas), ADR-0004/0005
(baselines y Change Control). Issue: #9 cerrado por v0.20.0 (CPM); este frente abre **Schedule Automation**.

## Contexto

ADR-0017 fijó Schedule Intelligence como capa **estrictamente read-only**: analiza los `exp_*` nativos y
**no escribe nada**. El cliente necesita además **constraints** tipo Microsoft Project (SNET/FNLT/MSO/MFO).
La auditoría del `Task` real de ERPNext v16 (`erpnext/projects/doctype/task/task.py`) confirma un hecho
decisivo que define la arquitectura de este frente:

- **ERPNext ya propaga dependencias FS, server-side y recursivo**, dentro del ciclo `save()`:
  `Task.on_update → reschedule_dependent_tasks()` recorre las sucesoras `Open` cuyo `exp_start_date` es
  anterior al fin de la predecesora y, **en días naturales** (`date_diff`/`add_days`), hace
  `nuevo_inicio = fin_pred + 1`, conserva la duración para el nuevo fin, marca
  `flags.ignore_recursion_check = True` y ejecuta `task.save()` sobre la sucesora (task.py:286‑311).

Como la propagación es un `save()` recursivo, **una regla de PMO que normalice la Task *dentro* de ese
mismo `save()` se aplica por igual a**: edición manual, Gantt, API/importación y a la Task **movida por la
cascada nativa**. Por tanto PMO **no necesita** construir un segundo scheduler ni recorrer/mover sucesoras.

Este frente **cruza deliberadamente** la frontera read-only de ADR-0017 (de ahí un ADR propio): introduce
una mutación local y acotada del forecast. No reemplaza ADR-0017; lo complementa.

## Decisión principal

> **ERPNext permanece como el ÚNICO motor de propagación FS. PMO solo normaliza/valida la Task que se está
> guardando contra un constraint local; nunca busca ni mueve sucesoras, ni implementa propagación propia.**

Mecanismo: **un solo punto de propagación** — `FS nativo → constraint local → FS nativo → constraint
local → …`, sin segunda cascada PMO.

## Decisiones (contrato semántico II.0)

1. **Punto de enganche = `before_validate`** (doc_event de Task en `hooks.py`). Razón basada en el código:
   el `validate()` del controlador llama `validate_dates()` → `validate_parent_project_dates()` (task.py:121),
   que **lanza** si una fecha sale de `Project.expected_start/end_date`. Ajustar en un hook `validate`
   (que corre *después* del `validate` nativo) dejaría las validaciones nativas de coherencia y límites de
   Project corriendo sobre fechas **viejas**. Enganchando en **`before_validate`**, PMO desplaza primero y
   **las validaciones nativas se ejecutan sobre la fecha ya corregida**. PMO **no** llama a `save()` por su
   cuenta (evita doble cascada y recursión): muta en memoria y deja que el `save()` en curso persista.
2. **Días naturales en cualquier mutación de escritura.** El write-path de PMO (desplazamiento SNET)
   replica la aritmética **natural** de `reschedule_dependent_tasks()` (`date_diff`/`add_days`), para no
   introducir una semántica distinta a la del core. **Separación explícita:** *Schedule Intelligence analiza
   en días **hábiles** (ADR-0017); la automation **escribe** en días **naturales** (igual que el core).*
3. **SNET (Start No Earlier Than) = único constraint MUTANTE (inicialmente).** Si el FS nativo propone un
   inicio **anterior** al SNET, PMO desplaza **esa** Task al SNET conservando su duración (natural); el
   `on_update` nativo continúa la cascada desde el nuevo fin. Si el FS ya coloca el inicio en o después del
   SNET, no hay conflicto (FS gana).
4. **FNLT (Finish No Later Than) = exclusivamente derivado / NO bloqueante.** `exp_end_date >
   pmo_constraint_date` produce una **violación de programación** (señal derivada en tiempo real, como
   Schedule Intelligence). **Nunca** lanza (`throw`) ni comprime duración ni adelanta la Task, **ni siquiera
   en edición manual**: un `throw` durante un `save()` de cascada abortaría toda la edición de la
   predecesora (rollback) y daría comportamiento inconsistente manual vs cascada. El forecast resultante
   permanece y la violación se hace visible.
5. **FNLT ≠ `pmo_deadline`.** Son señales distintas por razones distintas: **FNLT** = *límite de
   programación* ("el programa no es válido si termina después de X"); **`pmo_deadline`** = *compromiso /
   intención* ("nos comprometimos a terminar para X", ADR-0009). `pmo_deadline` permanece **exactamente**
   como está (compromiso, no constraint; no mueve fechas). Ambos pueden generar indicadores; se etiquetan y
   explican por separado para no confundirlos.
6. **Tasks iniciadas / completadas / canceladas NO se reprograman.** SNET **deja de mutar** y pasa a
   **diagnóstico** para no reescribir el pasado. **Definición ejecutable (para evitar criterios divergentes
   entre código y diagnóstico):** una Task se considera **iniciada** para efectos de SNET cuando exista
   **evidencia objetiva de ejecución, siendo `act_start_date` la señal canónica**. Cualquier regla adicional
   basada en `status` (p. ej. tratar `Completed`/`Cancelled`/`Overdue`/`Pending Review`) deberá **definirse
   explícitamente en II.1 antes de implementarse**; **no** se inferirá de forma genérica (nada de
   `status != "Open"` implícito). Un constraint con fecha anterior a `act_*`/corte se señala como
   configuración obsoleta/imposible; nunca mueve al pasado.
7. **MSO / MFO fuera de alcance.** No se implementan ni se listan en el Select inicial. MSO (Must Start On)
   y MFO (Must Finish On) son igualdades rígidas que, ante un FS incompatible, exigirían resolución de
   conflicto (qué mover: inicio, duración, predecesoras, recursos) — eso ya es un motor de scheduling, sin
   necesidad demostrada. Un "debe terminar el X" del cliente suele ser en realidad `pmo_deadline = X`, que
   ya existe.
8. **Grupos / fases (`is_group`) fuera.** No reciben constraints inicialmente. Son elementos estructurales
   de la WBS y no participarán como nodos mutables de constraints en esta primera implementación. *(Nota
   factual: ERPNext **no** deriva nativamente las fechas del grupo a partir de sus hijos — `update_project`
   recalcula el Project, no hace rollup de fechas al Task padre; por eso aquí no se afirma tal rollup.)*
   Milestones: evaluables después; no entran en el primer bloque.
9. **Baseline, actuals y compromisos intactos.** Los constraints **nunca** tocan `baseline` (snapshot
   inmutable, ADR-0004), `act_*` (propiedad del sistema) ni `pmo_committed_end_date`/`pmo_deadline`. Un
   forecast cambiado por SNET es **forecast nuevo**; la baseline sigue permitiendo medir la desviación.
10. **Sin segundo modelo de datos.** No hay DocType de constraints, ni tabla child, ni estado persistido de
    violación, ni campos calculados, ni segundo forecast. La violación se **deriva en tiempo real** de
    `exp_* + pmo_constraint_type + pmo_constraint_date`, con el mismo patrón SSOT de ADR-0017 (clasificación
    en el dominio; templates/JS solo presentan).

## Contrato (resumen)

| Regla | Mutación | Comportamiento |
|---|---|---|
| SNET + Task no iniciada | **Sí** | `before_validate`; mueve `exp_start/end` hacia adelante conservando duración en días naturales |
| SNET + Task iniciada | No | Violación / diagnóstico (no reescribe el pasado) |
| FNLT | **Nunca** | `exp_end > constraint_date` → violación derivada (no-throw) |
| MSO / MFO | No existen | Fuera de alcance |
| `pmo_deadline` | Nunca | Compromiso existente, independiente de FNLT |
| Baseline | Nunca | Snapshot permanece intacto |
| Actuals | Nunca | `act_*` permanece propiedad del sistema |
| Propagación FS | ERPNext | PMO nunca busca ni mueve sucesoras |

## Modelo de datos previsto (para II.1, aún NO implementado)

Dos Custom Fields en `Task`, vía **fixtures** (sin Property Setter, sin tocar core):

- `pmo_constraint_type` — Select: vacío · `Start No Earlier Than (SNET)` · `Finish No Later Than (FNLT)`.
  (MSO/MFO **no** se listan todavía, aunque el modelo quede conceptualmente extensible.)
- `pmo_constraint_date` — Date.

Una Task tiene **un solo** tipo/fecha de constraint (sin múltiples constraints inicialmente). El cambio de
esquema (fixtures + `bench migrate`) es de **II.1** y requiere autorización explícita; **II.0 no lo ejecuta**.

## Alcance por etapas

- **II.0** — este ADR + contrato semántico. *(esta iteración)*
- **II.1** — SNET mínimo: 2 Custom Fields (fixtures) + hook `before_validate` (desplazamiento natural
  conservando duración) + tests que prueben que la **cascada nativa sigue propagando** desde la fecha
  corregida, sin recursión extra ni segunda cascada PMO. *(bloque separado; requiere autorización de
  esquema/migrate)*
- **II.2** — FNLT diagnóstico (derivado en `scheduling.py`, no-throw) + visibilidad en Task y Project
  Control → Cronograma. *(diferido)*
- **II.3** — Integración/QA: Schedule Intelligence distingue `constraint violation` de `deadline exceeded`.
  *(diferido)*
- **MSO / MFO** — candidatos futuros, **no** deuda comprometida.

## Notas de implementación / verificación (de la auditoría del core)

- `reschedule_dependent_tasks` usa `end_date = self.exp_end_date or self.act_end_date` (task.py:287): si hay
  forecast, la cascada usa `exp_end_date` (no convierte el actual en driver). El desplazamiento SNET opera
  sobre `exp_*`, consistente con esto.
- `validate_parent_project_dates` hace `return if frappe.in_test` (task.py:122): los límites de Project **no**
  se validan bajo tests. Las pruebas de SNET/FNLT no chocarán con esa cota; la interacción SNET↔límites de
  Project debe verificarse **fuera** de `in_test` (QA real).
- El spike decisivo de II.1: confirmar que una Task movida por `reschedule_dependent_tasks()` y normalizada
  por el hook `before_validate` deja que ERPNext **continúe propagando** desde la nueva fecha, sin recursión
  adicional ni segunda cascada PMO. Si falla, **no** se salta a construir un scheduler: se reevalúa el alcance.

## Consecuencias

- PMO gana constraints operativos reales sin convertirse en un motor de scheduling ni duplicar la cascada FS.
- La frontera read-only de ADR-0017 se mantiene para el **análisis**; la escritura queda acotada a SNET sobre
  una sola Task, en `before_validate`, en días naturales.
- No añade DocTypes, Property Setters ni patches; los Custom Fields (II.1) van por fixtures. No toca core.
