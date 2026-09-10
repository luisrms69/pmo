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
- **Commits #2–#5: pendientes** (en orden).

## Siguiente paso
Tras commit #1 → **Commit #2 (Portafolio multi-proyecto)**: agregación P4 de indicadores por Project ya
existentes (Status/Planned-vs-Actual/forecast), sin motor nuevo. Diseño mínimo → implementar → tests →
reportar → autorización de commit.
No push/PR/release hasta terminar los 5 commits.

## Cuidados / no repetir
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Print Format base para #3 vive en `frappe-infrastructure` (revisar al iniciar #3, no antes).
- Rama protegida `version-16`; remoto `upstream`; BD/`bench migrate` con autorización; git solo vía `/ship`.
