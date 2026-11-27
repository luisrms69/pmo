# CONTINUITY.md — pmo

**Fecha:** 2026-11-27
**Rama activa:** `feat/capacity-ui-semantics` (base `version-16` @ v0.23.2 → objetivo PR **v0.23.3**, PATCH)
**Tarea actual:** `/ship pr` → merge → release v0.23.3 de la mejora de **semántica y presentación** de
planificación de capacidad (sin cambios en el motor).

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship`** de la rama `feat/capacity-ui-semantics` hacia `version-16` (objetivo v0.23.3,
PATCH). El cambio hace visible el trabajo asignado **sin fechas** ("Sin programar") y unifica la
terminología de capacidad de cara al usuario. **El motor de cálculo NO se tocó.**

Plan que estoy siguiendo:
`/ship pr` (commit 10d2f97 ya hecho) → gate pr-ready → push + PR hacia `version-16` → CI verde →
`/ship comentario-pr` → `/ship merge` (merge manual del usuario en GitHub) → `/sync-check` →
`/ship release` v0.23.3 → limpieza de rama.

Objetivo inmediato:
PR OPEN contra `version-16` con la mejora, listo para revisión y CI.

Criterio de avance:
PR creado y CI verde; tras merge, las 4 fuentes de verdad alineadas (versión 0.23.3 · mergeCommit ·
tag v0.23.3 · GitHub Release v0.23.3).

---

## Estado actual

### Ya cerrado
- Diagnóstico Tony/PROJ-0080 (comportamiento correcto; 12h sin programar no consumen capacidad libre).
- Implementación local aprobada por el usuario; QA visual OK; 144/144 tests + suite completa en verde.
- Commit `10d2f97` creado (9 archivos: reportes, page JS, tests, es.po, docs, bump 0.23.3).

### En progreso
- `/ship pr`: CONTINUITY (este archivo) → gate pr-ready → push + PR.

### Pendiente inmediato
1. Gate pr-ready (push + creación del PR hacia `version-16`).
2. CI verde del PR.
3. `/ship comentario-pr` → `/ship merge` (merge manual) → `/sync-check` → `/ship release` v0.23.3.

### No repetir / no ampliar
- **No** tocar el motor de capacidad (`capacity.py`, `availability.py`, `planned_load.py`): matemática intacta.
- **No** incorporar `unscheduled_hours` a `planned_total`/`free` ni a las series temporales.
- **No** modificar `erpnext_proposals` ni los datos de PROJ-0080 (pruebas aprobadas).
- **No** nombrar el festivo en el tooltip de disponibilidad (limitación aceptada; sería ampliar alcance).
- **No** introducir CHANGELOG nuevo fuera de `docs/CHANGELOG.md` (ya actualizado).

---

## Decisiones vigentes
- `unscheduled_hours` se expone **una sola vez por empleado** (1ª fila del reporte) → sumar la columna no
  duplica al cambiar granularidad/agregar/exportar.
- La separación programado/sin-programar se resuelve **en servidor** (flag `scheduled` + split del bucket
  confidencial), porque el cliente no puede distinguir una tarea sin fechas de la fila confidencial. P4 intacto.
- Gráfica: 3 series (Disponibilidad, Programado, Capacidad libre punteada); se retira capacidad teórica.
- SemVer **PATCH** (0.23.2 → 0.23.3): semántica/presentación, sin motor ni API nueva.

---

## Archivos relevantes ahora

### Leer primero
- `docs/usuario/capacity-planning.md` (terminología/vistas actualizadas) · `docs/CHANGELOG.md` (0.23.3).

### Del PR (ya commiteados en 10d2f97)
- `pmo/pmo/report/pmo_capacity_planning/pmo_capacity_planning.py` · `pmo/pmo/report/pmo_work_by_resource/pmo_work_by_resource.py`
- `pmo/pmo/page/capacity_planning/capacity_planning.js` · `pmo/locale/es.po` · tests · `pmo/__init__.py`.

### No tocar
- Motor: `pmo/capacity.py`, `pmo/availability.py`, `pmo/planned_load.py`.

---

## Riesgos / cuidados
- `es.po` requiere `bench compile-po-to-mo` para surtir efecto (ya compilado local; CI recompila).
- Línea punteada depende de la clase interna `line-graph-path` de frappe-charts (confirmada esta versión;
  si cambia, degrada sin romper).
- `pyproject.toml` deriva versión vía flit; tocar solo `pmo/__init__.py::__version__`.

## Información faltante
- Ninguna para continuar; tras el PR, el merge es manual del usuario en GitHub.
