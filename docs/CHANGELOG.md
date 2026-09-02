# Changelog — pmo

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
