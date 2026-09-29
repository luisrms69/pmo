# CONTINUITY.md — pmo

**Fecha:** 2026-09-28
**Rama activa:** `feat/pmo-home-rescate` (base `version-16` @ v0.17.0 → objetivo PR **v0.18.0**, MINOR)
**Tarea actual:** `/ship` de cierre **v0.18.0**. La rama reúne (un solo release, 18 commits sobre v0.17.0):
**rescate UX de PMO** (Home, Portafolio, Project Control/Resumen), **Panel PMO / Ciclo de Gobernanza** en el
Project (pestaña PMO nativa), **Handoff = Acta de Inicio / Charter** con autorización + sync Handoff→Project
(ADR-0014 D3 enmendado, snapshot v2), **PM canónico** read-only, **cambio gobernado de Fin comprometido**
(ADR-0007 D6, endpoint + Version/Comment), **fusión de "Planificado vs Real"** en Estado/Cronograma
(sección aditiva "Consumo de esfuerzo por tarea") con retiro de esa pestaña, y **actualización documental**
(ADRs 0007/0008/0011/0014 + arquitectura + guías de usuario). Squash & Merge → tag `v0.18.0` sobre el merge
commit → GitHub Release. **Siguiente frente (no iniciado): Reportes PMO.**

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship` de la rama `feat/pmo-home-rescate`** hacia `version-16` (v0.18.0). Todo implementado y con
QA visual aprobado; suite completa verde (597 tests / 51 módulos).

Plan que estoy siguiendo:
`/ship` completo: preflight (limpio) → bump 0.18.0 + CHANGELOG + CONTINUITY → push → PR a `version-16` →
`/ship comentario-pr` → `/ship merge` (Squash) → `/ship release` (tag v0.18.0 + GitHub Release) → limpieza.

Objetivo inmediato:
Push + PR contra `version-16` con `__version__` **0.18.0** y verificar CI.

Criterio de avance:
PR abierto contra `version-16`, working tree limpio, CI verde; luego merge + release + limpieza.

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
