# CONTINUITY.md — pmo

**Fecha:** 2026-10-05
**Rama activa:** `feat/pmo-schedule-intelligence` (base `version-16` @ v0.19.0 → objetivo PR **v0.20.0**, MINOR)
**Tarea actual:** `/ship pr` de cierre **v0.20.0** — **Schedule Intelligence** (read-only) end-to-end.
Alcance congelado: **ADR-0017** + **I.1** diagnóstico de integridad ("Revisión del cronograma") + **I.2**
holgura/slack (backward pass, margen vs compromiso, deadline por `EF>deadline`) + **I.3** ruta crítica
(secuencias, multi-rama, resaltado en Gantt) + **SSOT de clasificación + renombrado UX** (sin jerga "red")
+ **Schedule Readiness** ("Calendario del cronograma", precedencia Project→Company, cobertura de rango) +
**integración en PMO Portfolio** vía segunda tabla **Cronograma** (read-only). Cubre el **issue #9** (CPM /
ruta crítica) → `Closes #9`. Capa de dominio en `pmo/scheduling.py`; nada reprograma ni toca la cascada FS
nativa. PR hacia `version-16`; **sin merge** (lo autoriza el usuario aparte, luego `/ship release` v0.20.0).
**Diferido/condicional:** Schedule Automation (constraints SNET/FNLT/MSO/MFO) — solo diseño, sin código.
**Datos QA del entorno (NO parte del PR):** Holiday List `PMO QA Calendario 2026` asignada a `PROJ-0007` en
`pmo-v16.dev` (limpieza pendiente de autorización aparte).

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship pr` de la rama `feat/pmo-schedule-intelligence`** hacia `version-16` (objetivo v0.20.0,
MINOR). Schedule Intelligence I.0–I.3 + Readiness + Portfolio/Cronograma implementado, con QA visual
aprobado y suites verdes (scheduling 53, portfolio 8, project_control 44).

Plan que estoy siguiendo:
`/ship pr`: bump 0.20.0 + CHANGELOG/CONTINUITY → push → crear PR hacia `version-16` con `Closes #9` →
validaciones finales / CI. **DETENER antes de merge** (lo autoriza el usuario); luego `/ship merge` +
`/ship release` (tag v0.20.0 + GitHub Release) + limpieza.

Objetivo inmediato:
PR OPEN contra `version-16` con el frente Schedule Intelligence, listo para merge (CI en verde).

Criterio de avance:
PR OPEN, working tree limpio, versión 0.20.0 en la rama, `Closes #9`; luego merge + release + limpieza.

---

## Estado actual

### Ya cerrado
- ADR-0011 (`ba1070f`); Reporte Ejecutivo v1 (`bf57b19`); Calidad de Planeación (`a10d387`); fix shadowing `_` (`8650276`).
- **Bloque económico (ADR-0012)**: frontera `pmo/project_economics.py` (contrato lazy, 3 estados + ok,
  gate económico), sección `costs` en `build_project_control` (comparable_cost vs gross_margin_cost_basis),
  bloque compacto en `executive.html` (solo Page), pestaña **Financiera** (`financial.html` +
  `get_financial_html`), `impact_amount`/`impact_days` marcados no vinculantes. Docs: ADR-0012 +
  arquitectura.md + project-control.md. Tests: `test_project_economics.py` + ampliación de
  `test_project_control.py`.
- Validación real end-to-end en `pmo-v16.dev` (cadena PROJ-0009: root + addenda aplicada + addenda pendiente).
- Tests: suite completa **267 + 41 OK**. Linters (ruff check/format, prettier@2.7.1) limpios.

### Pendiente inmediato
1. CI del PR #20 en verde (corregir solo fallos atribuibles al cambio).
2. **DETENERSE antes de merge/tag/release** (merge lo hace el usuario; luego `/ship release` → tag+Release `v0.16.0`).

### No repetir / no ampliar
- No ampliar más la UI económica ni sembrar más datos (MVP aceptado por el usuario).
- No segunda fuente de verdad económica; todo autorizado entra por el contrato (ADR-0012 D1).
- Economía **nunca** en Print Format/PDF (ADR-0012 D6, decisión estructural).
- No degradar estado `inconsistent` a ausencia (ADR-0012 D3).

---

## Decisiones vigentes
- **SSOT económico = Quotation congelada** vía `get_project_authorized_economics`; pmo compone, no recalcula.
- **Gate económico único server-side**: rol {PMO Manager, PMO Executive Access, System Manager} **AND**
  Project READ, evaluado antes de componer `costs`; si no pasa, `pc.costs` no existe en el payload.
- **`comparable_cost`** = costing+purchase (vs autorizado); **`gross_margin_cost_basis`** = +material
  (base del `gross_margin` nativo). Material no contamina el comparable.
- `frappe.logger("pmo").warning` (no `frappe.log_error`) en el estado `inconsistent` — evita ensuciar el suite.
- Moneda v1: comparación solo con base única; el contrato es fail-closed ante moneda incompatible.

---

## Archivos relevantes ahora
### Leer primero
- `pmo/project_control.py` — builder canónico + sección `costs` + `get_financial_html`.
- `pmo/project_economics.py` — frontera/gate hacia `erpnext_proposals`.
- `pmo/templates/project_control/{executive,financial}.html`.
- `docs/adr/0012-project-economics-integration.md`.
### Fuera de git (no commitear)
- `one_offs/seed_finance.py` — seed económico dev-only (cadena real PROJ-0009, gitignored).

---

## Riesgos / cuidados
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Tras i18n/build → `clear-cache` para que el servidor tome traducciones nuevas.
- CI usa `ruff check` + `prettier@2.7.1` exactos; linters solo sobre `.py`/`.js`, nunca `.json`.
- `pyproject.toml` deriva la versión vía flit (`dynamic`); tocar solo `pmo/__init__.py::__version__`.

## Información faltante
- Ninguna para continuar; el PR se crea contra `version-16` y se detiene antes de merge/tag/release.
