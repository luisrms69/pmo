# Changelog — pmo

## [0.2.0] — 2026-09-02

### Added
- **Privacidad de Project/Task (P0)** — aislamiento fail-closed: Project y Task privados por defecto.
  - Visibilidad por **owner / `PMO Project Member` / `PMO Executive Access` / DocShare**; una Task
    hereda la frontera de su Project, y la asignación directa (ToDo) da acceso **solo a esa Task**.
  - Enforcement por hooks nativos **sin tocar DocPerms**: `permission_query_conditions` (listados,
    Gantt, calendario, búsquedas, API) + `has_permission` (documento único/URL). SHARE manual
    restringido a `PMO Executive Access`/`Administrator` por el mismo hook (`ptype="share"`), sin
    Custom DocPerm; `assign_to` sin auto-share.
  - Política de WRITE: owner (Project + Tasks), member (Tasks del Project), assignee (su Task);
    `PMO Executive Access` solo lectura; `PMO Manager` sin acceso por el rol.
  - **Cierre de vectores que ignoran `pqc`**: override de `create_duplicate_project` (check READ del
    origen) y `Custom Role` que restringe los reports `Project Summary`, `Delayed Tasks Summary` y
    `Project wise Stock Tracking` a `PMO Executive Access`/`Administrator`. Global Search verificado.
  - Nuevos objetos: child DocType `PMO Project Member` (+ Custom Field `Project-pmo_members`), roles
    `PMO Manager` y `PMO Executive Access`, fixtures (`custom_field`, `role`, `custom_role`).
  - Tests: `test_privacy_{read,write,share,reports}.py`. Decisiones en ADR-0002 (D1–D11).

### Docs
- `docs/tecnico/arquitectura.md` (sección Privacidad P0) y `docs/usuario/privacidad-proyectos.md`.

## [0.1.1] — 2026-09-02

### Added
- ADR-0002 (Project/Task Privacy y Security Boundary) y ADR-0003 (Resource Capacity and Planned
  Allocation) como decisiones arquitectónicas base (estado Propuesto). Solo documentación; sin cambios
  de código ni de esquema.

## [0.1.0] — 2026-08-16

### Added
- Gantt de `Task` ordenado automáticamente por jerarquía (`lft ASC`), no por fechas, vía
  `doctype_calendar_js` (sin tocar core; solo afecta Task > Gantt).
- Importador administrativo de Tags nativos desde CSV (Page `tag_import`): Dry Run sin escritura,
  Aplicar con validación global todo-o-nada, idempotente, con desglose por documento.
- ADR-0001 y documentación técnica/usuario.

## [0.0.1] — 2026-08-14

### Added
- Scaffold inicial del app
- Integración con frappe-infrastructure (symlink `.claude/commands`, CLAUDE.md referencial)
- CI + linter (`.github/workflows/ci.yml`, `linter.yml`)
- `required_apps = ["erpnext"]`
