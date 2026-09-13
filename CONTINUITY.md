# CONTINUITY.md — pmo

**Fecha:** 2026-09-12
**Rama activa:** `feat/pmo-reporting-architecture` (base `version-16` @ v0.15.0 → objetivo PR **v0.16.0**)
**Tarea actual:** Bloque económico del Reporte Ejecutivo (ADR-0012) commiteado; preparando bump 0.16.0 + CHANGELOG y PR contra `version-16`.

---

## Recuperación rápida

Estoy trabajando en:
El **PR de arquitectura de reporting canónica** de Project Control. La rama reúne (un solo PR):
ADR-0011 (contexto canónico) + Reporte Ejecutivo v1 + Calidad de Planeación + **bloque económico
(ADR-0012)**. El bloque económico añade la sección `costs` a `build_project_control` consumiendo el
contrato de `erpnext_proposals` (`get_project_authorized_economics`), sin recalcular economía.

Plan que estoy siguiendo:
ADR-0011 + ADR-0012 + spec económica del usuario (BLOQUE 0–5, MVP aceptado). Flujo `/ship pr` autorizado
de corrido: commit → bump/CHANGELOG → gates → push → PR. DETENERSE antes de merge/tag/release.

Objetivo inmediato:
Crear/actualizar el PR contra `version-16` con bump **0.16.0** (MINOR) y verificar CI.

Criterio de avance:
PR abierto contra `version-16`, working tree limpio, CI verde (o solo fallos ajenos al cambio).

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
1. Bump `__version__` 0.15.0 → **0.16.0** + entrada CHANGELOG 0.16.0 (una versión por PR).
2. `/ship pr`: push + crear PR contra `version-16`; verificar CI.
3. **DETENERSE antes de merge/tag/release** y presentar checkpoint.

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
