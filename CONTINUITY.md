# CONTINUITY.md — pmo

**Fecha:** 2026-09-30
**Rama activa:** `feat/pmo-unassigned-and-cr-priority` (base `version-16` @ v0.18.0 → objetivo PR **v0.19.0**, MINOR)
**Tarea actual:** `/ship` de cierre **v0.19.0**. Bloque pequeño y congelado sobre Project Control / Change
Control (sin tocar PHI/Financial): (A) **Tasks exigibles sin responsable** — `_planning_section.unassigned`
cuenta solo hojas activas, sin ToDo abierto, con `exp_start_date` ≤ Status Date (futuras/sin fecha no
penalizan); visible en Resumen (bloque Planeación) y Reporte Ejecutivo. (B) **Change Request Priority**
obligatorio (default Medium), visible en Reporte Ejecutivo y bandeja de Gobernanza, que ordena CR
High→Medium→Low (solo visual). (C) acceso **"Ir a proyecto"** (botón). (D) fix de normalización
`datetime.date → str` del cutoff en `build_project_control`/`get_summary_html` (417 al abrir Resumen/imprimir)
con test de regresión. Squash & Merge → tag `v0.19.0` sobre el merge commit → GitHub Release.
**Pendiente NO bloqueante:** UX/navegación de la tabla de Portfolio.
**Siguiente paso separado (NO en este bloque):** actualización de staging/producción.

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship` de la rama `feat/pmo-home-rescate`** (PR #22) hacia `version-16` (v0.18.0). Todo
implementado y con QA visual aprobado (PHI + Financial Health incluidos); suites del bloque verdes.

Plan que estoy siguiendo:
`/ship`: docs (CHANGELOG/CONTINUITY con PHI+Financial) → push → actualizar `/ship comentario-pr 22` →
esperar **CI verde** → `/ship merge` (Squash) → `/ship release` (tag v0.18.0 + GitHub Release) → limpieza.

Objetivo inmediato:
CI verde en PR #22 (HEAD con PHI+Financial) para proceder a merge + release.

Criterio de avance:
PR #22 OPEN contra `version-16`, working tree limpio, CI verde; luego merge + release + limpieza.

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
