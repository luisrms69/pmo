# CONTINUITY.md — pmo

**Fecha:** 2026-09-10
**Rama activa:** `feat/product-readiness-round` (base `version-16` @ v0.11.0, commit `6ff63cb`).
**Ronda:** Product readiness — **una rama, 5 commits, objetivo release `v0.12.0`.**

## Plan que estoy siguiendo
5 mejoras, un commit independiente por cada una (no rama/PR por mejora):
1. UX captura/mantenimiento `PMO Capacity`.  ← **commit en curso**
2. Dashboard / portafolio multi-proyecto.
3. Salida presentable `PMO Status Report` (Commit #3: revisar primero el Print Format existente en
   `frappe-infrastructure` antes de diseñar — acordado).
4. Corrección documental `capacity-planning.md` (texto stale de Actual/Util. real) + actualización completa
   de `docs/roadmap.md` (integrada aquí, sin sexto commit).
5. Workspace PMO unificado / landing enlazando las capacidades implementadas.

Guardarraíles: P4; nativo primero; sin motores paralelos; sin tocar #9/#10/constraints; sin rediseñar ADRs.

## Estado por commits
- **Commit #1 — UX `PMO Capacity`. ✅ (commit en curso)**
  - `pmo/capacity.py`: `get_capacity_detail` (resolver único {hours,origin,from_date}; `get_capacity` wrapper).
  - Report `PMO Resource Capacity` (cobertura: capacidad efectiva/origen/vigencia por recurso; scope por
    observador; sin Project/Task). `pmo_capacity.js` (default from_date + intro). Docs usuario+arquitectura.
  - migrate en test-pmo OK (report registrado); smoke `execute()` OK. Tests `test_resource_capacity.py` (7).
    **Suite 244/244**, sin regresión Capacity/Availability.
- **Commit #2 — Portafolio multi-proyecto. ✅ (commit en curso)**
  - Report `PMO Portfolio`: fila por Project visible (salud En plan/En riesgo/Desviado, forecast, slips,
    vencidas, forecast>compromiso, Planned/Actual/%); reusa `build_status_report` (P4) + suma esfuerzo nativa.
    `try/except PermissionError` por proyecto. Filtros Company + Incluir completados. Docs usuario+arquitectura.
  - migrate en test-pmo OK (registrado); smoke `execute()` OK. Tests `test_portfolio.py` (7). **Suite 251/251**.
- **Commit #3 — Status Report presentable. ✅ (commit en curso)**
  - Print Format estándar `PMO Project Status` (Jinja, doc_type Project) resumen-primero + tareas relevantes;
    método Jinja `pmo.print_status.pmo_project_status` (reusa build_status_report; P4). Fechas ISO (evita bug
    locale). Agnóstico al generador PDF (wkhtmltopdf 1º; Gotenberg vía config del site). No toca el PF del
    cliente. migrate OK; render HTML ✔; PDF generado (18KB, quirk de exit de wkhtmltopdf en headless → test
    skip). Tests `test_print_status.py` (4). **Suite 255/255 (+1 skip)**.
- **Commit #4 — documental. ✅ (commit en curso)**
  - `capacity-planning.md`: corregida nota stale (Actual SÍ se muestra en el reporte + Planned vs Actual).
  - `docs/roadmap.md`: consolidado (Entregado v0.7–v0.11; v0.12.0 marcada **En implementación, sin release**;
    Workspace landing = pendiente Commit #5). 7 pendientes preservados con tiers; #9/#10 referenciados.
- **Commit #5 — Workspace PMO unificado / landing. ✅ (commit en curso)**
  - Workspace público `PMO` (seq 10, primero): shortcuts hero + cards agrupando 9 reportes + 3 DocTypes de
    config. Sin charts/number_cards. `PMO Capacity`/`PMO Control` intactos (regression test). migrate OK.
    Tests `test_pmo_workspace.py` (5). **Suite 260/260 (+1 skip PDF)**.

## Siguiente paso
**Ronda de 5 commits COMPLETA.** Falta bump `__version__ → 0.12.0` (aún en 0.11.0) antes del PR, docs de
release, y `/ship push` → `/ship pr` (base `version-16`). El bump lo aplico en el paso de PR-ready (un solo
bump por PR). No push/PR/release aún.

## Cuidados / no repetir
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Print Format base para #3 vive en `frappe-infrastructure` (revisar al iniciar #3, no antes).
- Rama protegida `version-16`; remoto `upstream`; BD/`bench migrate` con autorización; git solo vía `/ship`.
