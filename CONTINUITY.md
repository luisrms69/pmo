# CONTINUITY.md — pmo

**Fecha:** 2026-10-09
**Rama activa:** `fix/pmo-fixtures-align-filter` (base `version-16` @ v0.22.0 `b090dc9` → objetivo PR **v0.22.1**, PATCH)
**Tarea actual:** `/ship pr` de cierre **v0.22.1** — **corrección de portabilidad de fixtures**: alinear el
filtro de exportación de `hooks.py` con `fixtures/custom_field.json` (22 → 20 Custom Fields), retirando dos
residuos de diseño y añadiendo un test de regresión que impide repetir la inconsistencia.

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship` de la rama `fix/pmo-fixtures-align-filter`** hacia `version-16` (objetivo v0.22.1,
PATCH). Corrección verificada: 4/4 pruebas nuevas + 127/127 relacionadas OK; `bench migrate` en
`pmo-v16.dev` limpio; ruff OK.

Plan que estoy siguiendo:
`/ship pr`: bump 0.22.0→0.22.1 + CONTINUITY → push + PR hacia `version-16` → CI verde → `/ship comentario-pr`
→ `/ship merge` → `/ship release` tag+Release `v0.22.1`.

Objetivo inmediato:
Cerrar **solo** esta corrección y dejar PMO listo para el diseño de Orientación UX (frente separado, NO en
esta rama).

Criterio de avance:
PR OPEN, working tree limpio, versión 0.22.1 en la rama; luego merge + release.

---

## Estado actual

### Qué corrige este PR
- **`hooks.py`**: el filtro `fixtures` → Custom Field nombraba solo 9 campos, pero `custom_field.json`
  contenía 22. Un `export-fixtures` futuro habría reescrito el archivo dejando fuera toda la pestaña PMO
  del Project (bomba de tiempo de portabilidad). Filtro alineado 1:1 a los **20** vigentes.
- **`custom_field.json`**: retirados 2 residuos de v0.18.0 **sin uso** (ocultos, 0 referencias):
  `pmo_committed_html` (reemplazado por el campo nativo `pmo_committed_end_date`) y `pmo_sec_ctrl`
  (sección oculta; "Control del proyecto" vive en la Page `pmo_project_control`). Repunte:
  `pmo_sec_access.insert_after` `pmo_committed_html` → `pmo_committed_end_date`.
- **Test nuevo** `test_fixture_integrity.py`: 4 pruebas estáticas (sin BD) que fallan si el fixture y el
  filtro de hooks divergen, si hay duplicados, si reaparecen los obsoletos, o si un `insert_after` ancla a
  un campo inexistente.

### Decisión deliberada (NO se hace en este PR)
- **No** se eliminan los 2 campos huérfanos de la BD de sitios existentes (requeriría patch). Quitarlos del
  fixture NO los borra (el import no elimina); quedan ocultos e inofensivos. Nuevas instalaciones reciben
  los 20 limpios.

### Pendiente inmediato
1. Push + PR hacia `version-16` (v0.22.1).
2. CI en verde.
3. `/ship comentario-pr` → `/ship merge` → `/ship release` tag+Release `v0.22.1`.

### No repetir / no ampliar
- No incluir nada de **Orientación UX** (frente separado posterior).
- No eliminar huérfanos de BD, no export-fixtures, no patches, no Property Setters, no tocar core.

---

## Archivos del PR
- `pmo/fixtures/custom_field.json` — 20 Custom Fields (−2 residuos; repunte insert_after).
- `pmo/hooks.py` — filtro `fixtures` alineado a los 20.
- `pmo/pmo/tests/test_fixture_integrity.py` — guard de regresión (nuevo).
- `pmo/__init__.py` — bump 0.22.0 → 0.22.1.
- `CONTINUITY.md` — este archivo.

---

## Riesgos / cuidados
- Redis del bench v16 (13001/11001) ha sido inestable; requiere `bench start` para correr tests.
- CI usa `ruff` + `prettier@2.7.1`; linters solo `.py`/`.js`, nunca `.json`.
- `pyproject.toml` deriva la versión vía flit; tocar solo `pmo/__init__.py::__version__`.
- El test es estático (sin BD) y site-independiente; usa `get_hooks`/`get_app_path`/`get_meta` (read-only).

## Información faltante
- Ninguna para continuar; PR contra `version-16`, merge + release v0.22.1 por el procedimiento habitual.
