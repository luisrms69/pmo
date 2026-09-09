# ADR-0007: Fecha comprometida de cronograma (Task deadline / Project committed end)

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted · **Ciclo:** v0.8.0 (Gobierno avanzado del cronograma — fase 1)

## Aceptación (2026-09-09)

Implementado en v0.8.0 sin desviaciones respecto de D1–D5. Custom Fields `Task.pmo_deadline` y
`Project.pmo_committed_end_date` (Date, por fixture); validaciones suaves (`pmo/schedule_commit.py`,
`doc_events` `Task`/`Project` `validate`) que **avisan y no bloquean** (D4) — el aviso usa fecha ISO directa
(no `format_date`) para no depender del locale. `snapshot_schema_version` sigue en 1; Baseline y Status Date
sin cambios; ADR-0004/0006 sin modificar (D5). Sin constraints tipados. Verificado con `bench migrate` en
`test-pmo.localhost` (campos creados), smoke test (breach → avisa y guarda; sin breach → guarda sin aviso;
persiste) y suite 211/211.

## Contexto

ADR-0004 estableció que las fechas de cronograma en PMO son **plan/forecast no vinculante**:
`Task.exp_start_date`/`exp_end_date` se **calculan** y se desplazan por dependencias y reprogramación, y
el **Actual** (Timesheet) nunca se bloquea. ADR-0006 añadió el control a fecha de corte (Status Date).
Falta un concepto que hoy no existe en ERPNext ni en PMO: la **fecha comprometida**, separada de la fecha
calculada.

## Problema

No se puede distinguir, sobre un mismo Project/Task, entre:
- **fecha planeada/calculada actual** — lo que el cronograma dice hoy (se mueve con dependencias/replanificación);
- **fecha comprometida** — el compromiso acordado que **no** cambia automáticamente porque el cálculo se mueva.

Sin esa distinción no se puede responder "el cronograma calcula el 15, pero el compromiso era el 10".

## Decisiones

### D1 — Distinción explícita: planeado/calculado vs comprometido
- **Planeado/calculado (ya existe, NO se toca):** `Task.exp_start_date`/`exp_end_date` y
  `Project.expected_end_date`. Son salida del modelo de cronograma; **cambian** con dependencias,
  reprogramación y edición. Siguen siendo forecast no vinculante (ADR-0004).
- **Comprometido (nuevo):** una fecha de referencia fijada por **decisión de negocio/acuerdo** (puede ser
  contractual, pero también un compromiso interno o acordado). **No se desplaza automáticamente** con la
  reprogramación del cronograma; **no es inmutable**: puede modificarse **explícitamente** por una decisión
  autorizada (edición deliberada del campo). Es un **compromiso**, no una restricción que altere el cálculo.

### D2 — `Task.pmo_deadline` (Date)
Fecha límite/comprometida de la **tarea**. **No** mueve la tarea, **no** dispara reprogramación, **no**
bloquea la ejecución real (Timesheet/Actual). Es referencia para comparar contra la fecha calculada.

### D3 — `Project.pmo_committed_end_date` (Date)
Fecha **comprometida** de terminación del **proyecto**, distinta de `expected_end_date` (calculada). Mismo
carácter de referencia; no altera el cálculo.

### D4 — Validaciones suaves (warnings, nunca bloqueantes)
Coherente con ADR-0004 (fechas no vinculantes; el Actual nunca se bloquea):
- Si `getdate(Task.exp_end_date) > Task.pmo_deadline` → **warning** ("el fin planeado excede la fecha comprometida").
- Si `Project.expected_end_date > Project.pmo_committed_end_date` → **warning**.
- **No** se bloquea el guardado, ni el Timesheet, ni el Actual. Campos vacíos = sin compromiso (válido).
- Se enganchan en los `doc_events`/mixin existentes; **sin** tocar el scheduler nativo.

### D5 — Sin impacto en Baseline ni Status Date
- **NO** se sube `snapshot_schema_version` (sigue en 1). El snapshot de Baseline **no** cambia.
- **NO** se modifica el reporte ni la lógica de Status Date (ADR-0006).
- **ADR-0004 y ADR-0006 no se modifican**; ADR-0007 solo los referencia.
- Implementación: **Custom Fields por fixture** (requiere `bench migrate` para sincronizar metadata; sin
  data/migration patch). Sin DocTypes nuevos.

## Fuera de alcance (diferido)
- **Constraints tipados** `pmo_constraint_type`/`pmo_constraint_date` y los tipos MS Project
  **SNET/FNLT/MSO/MFO** → **diferidos a un ciclo futuro** si aparece una **necesidad real**. Un deadline (D2)
  es una referencia que solo avisa; un constraint tipado restringe/gobierna la programación y exige más
  diseño (y roza CPM) — por eso no entra ahora.
- Auto-reprogramación, scheduler propio, CPM/ruta crítica (#9), EVM, forecast, reservas de capacidad (#10).
- Cambios en Baseline/snapshot y en Status Date.

## Consecuencias
- Se puede registrar y visualizar el **compromiso** por Task y por Project, y detectar (por warning) cuando
  el cálculo lo excede, sin alterar el cronograma ni el Actual.
- Baseline y Status Date quedan intactos → cero riesgo sobre lo ya liberado (v0.5–0.7).
- `bench migrate` requerido una vez (Custom Fields).

## Riesgos
- **Solapamiento conceptual** con futuros constraints tipados: se mitiga documentando que `pmo_deadline` es
  **solo referencia** (no gobierna programación); un `Finish No Later Than` tipado sería otra cosa y llegaría
  en un ciclo futuro.
- Warnings ignorables: por diseño (no bloqueantes); es gobernanza informativa, no control duro.

## Alternativas descartadas (para este ciclo)
- Modelar el compromiso como un **constraint tipado** (FNLT) → más pesado, roza scheduling; diferido.
- **Baselinar** el compromiso (snapshot v2) → descartado en este ciclo para no tocar el esquema de Baseline.
- Hacer la validación **bloqueante** → contradice ADR-0004 (fechas no vinculantes).
- Describir la fecha comprometida como **inmutable** → descartado: no se mueve con el cálculo, pero sí puede
  cambiarse por decisión autorizada.

## Criterios de aceptación
- Existen `Task.pmo_deadline` y `Project.pmo_committed_end_date` (Date, por fixture).
- Guardar con `exp_end_date` > `pmo_deadline` (o `expected_end_date` > `pmo_committed_end_date`) **avisa**
  pero **no** bloquea; el Timesheet/Actual nunca se bloquea.
- `snapshot_schema_version` sigue en 1; Baseline y Status Date sin cambios; ADR-0004/0006 sin modificar.
- Campos vacíos no generan warnings.
