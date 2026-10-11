# CONTINUITY.md — pmo

**Fecha:** 2026-10-11
**Rama activa:** `feat/pmo-orientation` (base `version-16` @ v0.22.1 `2f312bd` → objetivo PR **v0.23.0**, MINOR)
**Tarea actual:** `/ship pr` de cierre **v0.23.0** — **«Pendientes del proyecto»**: encabezado único en el
form nativo de Project que muestra hasta 3 **excepciones accionables** (responsable · situación · acción),
reutilizando señales existentes. Sin motores nuevos, sin DocType/Custom Field/Property Setter.

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship` de la rama `feat/pmo-orientation`** hacia `version-16` (objetivo v0.23.0, MINOR).
Implementación completa y validada visualmente en `pmo-v16.dev`; 18 tests nuevos + regresión OK.

Plan que estoy siguiendo:
`/ship pr`: bump 0.22.1→0.23.0 + CONTINUITY → push + PR hacia `version-16` → CI verde →
`/ship comentario-pr` → `/ship merge` (Squash & Merge manual del usuario) → `/ship release` v0.23.0.

Objetivo inmediato:
PR OPEN contra `version-16` con «Pendientes del proyecto», listo para merge (CI en verde).

---

## Estado actual

### Qué entrega este PR
- **`pmo/orientation.py`** (nuevo): `get_orientation(project)` — compositor read-only (P4 vía
  `project_governance_state`), ≤3 recomendaciones de 6 familias: `pm_unassigned`, `handoff`,
  `unassigned_tasks`, `planning_incomplete`, `baseline`, `governance` (1 fila, selección por etapa).
  Corte = `today()`. Exención (Opción A): operativas (incl. `pm_unassigned`) se muestran; gobernanza
  (handoff/baseline/governance) se suprime. **No** ejecuta `build_status_report`/`build_project_control`.
- **`pmo/project_control.py::_planning_section`** (aditivo): expone `total` y `schedule_incomplete`
  (tareas hoja DISTINTAS sin inicio/fin/estimación; una a la que faltan los tres cuenta 1). No altera
  pct/componentes/unassigned/consultas existentes.
- **`pmo/public/js/project_pmo.js`**: `pmo_header(frm)` — **encabezado único** arriba del form vía
  `frm.dashboard.set_headline` (patrón contextual tipo Facturación México). Título «Pendientes del
  proyecto (N)», ≤3 filas. **Único escritor del slot**: se retiraron los dos `set_intro` de baseline
  (naranja + azul) de `pmo_governance_group`. Limpio si no hay pendientes. Guards: `seq`
  (anti-respuesta-obsoleta), `removePrior` (anti-duplicado), `.catch` que no rompe el form. Acciones
  reutilizan handlers existentes.
- **`pmo/pmo/tests/test_orientation.py`** (nuevo): 18 tests.

### Decisiones de diseño (aprobadas)
- Nombre «Pendientes del proyecto»; solo **excepciones**, ≤3, sin semáforos/puntajes/%.
- Barra naranja "Sin línea base" → fila del panel; barra azul "Baseline: rev·fecha" → **retirada** (es
  dato, vive en Project Control + lista PMO Project Baseline; **no** se re-muestra como barra).
- Rejilla "Ciclo de Gobernanza", menú PMO, indicadores de riesgo y popups: **intactos**.

### Pendiente inmediato
1. Push + PR hacia `version-16` (v0.23.0).
2. CI verde (job Server = install fresco + migrate + suite).
3. `/ship comentario-pr` → `/ship merge` (merge manual del usuario) → `/ship release` tag+Release `v0.23.0`.

### No repetir / no ampliar
- No devolver ninguna barra de baseline (la rev/fecha es dato, no excepción).
- No tocar rejilla/menú/indicadores/popups/motores en este frente.
- Indicadores de riesgo y adelgazamiento del menú PMO = pasos opcionales posteriores (decisión aparte).

---

## Archivos del PR
- `pmo/orientation.py` · `pmo/project_control.py` · `pmo/public/js/project_pmo.js` ·
  `pmo/pmo/tests/test_orientation.py` · `pmo/__init__.py` (bump) · `CONTINUITY.md`.

---

## Riesgos / cuidados
- El render del encabezado es JS (no cubierto por unit tests); validado visualmente + evidencia del
  endpoint. Backend (familias/exención/conteos/P4) sí en los 18 tests.
- `set_intro` y `set_headline` comparten el slot superior (`form.js`); PMO es ahora el **único** escritor.
- Redis del bench v16 inestable; requiere `bench start` para correr tests.
- CI usa `ruff` + `prettier@2.7.1`; linters solo `.py`/`.js`, nunca `.json`.
- `pyproject.toml` deriva la versión vía flit; tocar solo `pmo/__init__.py::__version__`.

## Información faltante
- Ninguna para continuar; PR contra `version-16`, merge manual del usuario, luego release v0.23.0.
