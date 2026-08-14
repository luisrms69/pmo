# ADR-0000: Estado inicial — pmo

**Fecha:** 2026-08-14
**Status:** Activo

## Contexto

App nueva creada como parte del ecosistema Buzola sobre frappe-bench-v16.
Project Management Office. App para gestión de proyectos sobre el DocType nativo `Project` de ERPNext.

No migra código del app legacy `project_management`, que se trata y desinstala por separado.
`pmo` comienza desde cero.

## Decisiones iniciales

- Bench: frappe-bench-v16 (Frappe 16.x, ERPNext 16.x)
- Branch protegida: version-16 (estándar Frappe upstream)
- Site de desarrollo: pmo-v16.dev → localhost:8412
- Site de tests: test-pmo.localhost
- Apps requeridas: erpnext (`required_apps = ["erpnext"]`)
- GitHub: https://github.com/luisrms69/pmo (público)
- Reglas Claude Code / git / testing: heredadas de `frappe-infrastructure` (symlink `.claude/commands`
  y referencia a `frappe-infrastructure/.claude/CLAUDE.md`); no se duplican en este repo.

## Notas

Primera funcionalidad prevista (aún no implementada): mover fechas de un Project que todavía no ha
iniciado. Sin DocTypes, Custom Fields, patches ni fixtures preventivos hasta necesitarlos.

Documentar decisiones arquitectónicas relevantes en ADRs subsiguientes.
