# CONTINUITY.md — pmo

**Fecha:** 2026-09-08
**Rama activa:** `docs/changelog-060-release` (base `version-16` @ v0.6.0, commit `3a6fa72`).
**Estado:** post-release de **v0.6.0** (tag `v0.6.0` + GitHub Release publicados y alineados). Follow-up
documental: corregir la sección `[0.6.0]` del CHANGELOG (había quedado "En preparación / no publicado") y
bump **`__version__` → 0.6.1** (PATCH, por modificar `version-16` tras la release).

## Plan que estoy siguiendo
Cierre correcto del ciclo post-release + fix del desfase del CHANGELOG. Un solo PR mínimo hacia `version-16`,
**detenerse antes del merge**.

## Qué se hizo en esta rama
- `docs/CHANGELOG.md`: sección `[0.6.0]` reescrita para reflejar la release real (fecha 2026-09-08; sin
  "En preparación / Release no publicado / Planned"); contenido movido a Added/Changed/Removed/Docs, fiel a
  ADR-0005 y a las release notes publicadas. Añadida entrada `[0.6.1] — 2026-09-08` (Fixed: corrección del
  CHANGELOG). Secciones históricas (`[0.5.0]` y anteriores) intactas.
- `pmo/__init__.py`: `__version__` 0.6.0 → **0.6.1**.

## SemVer
- Base `upstream/version-16` = 0.6.0. Cambio documental sobre `version-16` post-release → regla `/ship`:
  todo PR mergeado ≥ PATCH → objetivo **0.6.1**. Sin cambio funcional para satisfacer SemVer.

## Gates
- Diff exacto revisado (2 archivos). Gate de datos de cliente: limpio. `ruff` (import-sort/linter/format):
  OK. `mkdocs build --strict`: sin ERROR/WARNING. No aplica E2E ni suite (cambio exclusivamente documental
  + bump).

## Housekeeping pendiente (decisión del usuario)
- `feat/change-control`: mergeada por **squash** (PR #7). `git branch --merged` no la detecta (artefacto de
  squash); borrado local exigiría `git branch -D` (**force**, prohibido) → **no borrada**. Remota aún existe.
- `pmo-v16.dev`: 3 filas legacy de `PMO Project Member`; limpieza one-off bloqueada por el guard (pendiente
  de decisión). `one_offs/` y metadata legacy: **sin tocar**.

## Siguiente paso
`/ship commit` → `/ship push` → `/ship pr` (base `version-16`). Detenerse con el PR abierto y CI evaluado.
No merge/tag/release.
