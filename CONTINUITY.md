# CONTINUITY.md — pmo

**Fecha:** 2026-10-06
**Rama activa:** `feat/pmo-schedule-constraints` (base `version-16` @ v0.20.0 → objetivo PR **v0.21.0**, MINOR)
**Tarea actual:** `/ship pr` de cierre **v0.21.0** — **Schedule Constraints** (SNET write-path acotado +
FNLT diagnóstico) end-to-end.
Alcance congelado (3 commits): **ADR-0018** (II.0, `dca52c2`) + **SNET** write-path acotado (II.1,
`a774c16`: `before_validate` normaliza solo la Task que se guarda sobre `exp_*`, nunca propaga; ERPNext
sigue siendo el único propagador FS) + **FNLT diagnóstico + clasificador SSOT + indicador de Task** (II.2,
`ec1b8ac`: `constraints.py` con `classify_constraint` + endpoint read-only `get_constraint_status`;
`analyze_schedule_integrity` detecta `fnlt_violation`/`snet_violation` —esta última sin importar el origen
de la escritura, incluido `set_value` del Gantt nativo—; indicador derivado en el form nativo de Task vía
`set_intro`; findings/contadores en Project Control; traducciones es.po). Principio: **ERPNext opera el
cronograma; PMO lo gobierna y diagnostica**; nada construye un segundo scheduler.

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship` completo de la rama `feat/pmo-schedule-constraints`** hacia `version-16` (objetivo
v0.21.0, MINOR): PR → merge → tag/Release → limpieza de rama. Schedule Constraints funcionalmente terminado
(II.0–II.2), los 3 commits pusheados; QA visual del indicador y Project Control aprobado; suites verdes
(constraints 16, scheduling 13).

Plan que estoy siguiendo:
`/ship pr`: bump 0.21.0 + CONTINUITY → push → crear PR hacia `version-16` → `/ship comentario-pr` →
validaciones/CI. **El merge lo ejecuta el usuario en GitHub** (el skill prohíbe que Claude lo ejecute);
luego `/sync-check` + `/ship release` (tag v0.21.0 + GitHub Release) + borrado de rama.

Objetivo inmediato:
PR OPEN contra `version-16` con el frente Schedule Constraints, listo para merge (CI en verde + comentario
técnico publicado).

Criterio de avance:
PR OPEN, working tree limpio, versión 0.21.0 en la rama; luego merge + release + limpieza.

---

## Estado actual

### Ya cerrado
- **II.0 ADR-0018** (`dca52c2`): contrato Schedule Constraints + límite de enforcement (escrituras fuera de
  `Task.save()` como el Gantt nativo con `set_value` no se interceptan; se detectan después).
- **II.1 SNET** (`a774c16`): `pmo/constraints.py` write-path acotado — `apply_start_constraint`
  (`before_validate`), `compute_snet_start_end`, elegibilidad (no iniciada/completada/cancelada/grupo/hito),
  duración en días naturales, preserva hora; `notify_start_constraint` (on_update, suprimido en cascada).
- **II.2 FNLT + SSOT + indicador** (`ec1b8ac`): clasificador `classify_constraint` (8 estados SNET/FNLT) +
  `get_constraint_status` (read-only); detección `fnlt_violation`/`snet_violation` en
  `analyze_schedule_integrity`; `task_pmo.js` (indicador `set_intro`); limpieza de copy en Project Control.
- Tests verdes: `test_constraints` 16, `test_scheduling` 13. Linters (ruff check/format, prettier@2.7.1) OK.

### Pendiente inmediato
1. Crear PR hacia `version-16` + `/ship comentario-pr` (gate previo al merge).
2. CI del PR en verde.
3. Merge (lo ejecuta el usuario en GitHub) → `/sync-check` → `/ship release` tag+Release `v0.21.0` → borrar rama.

### No repetir / no ampliar
- No construir un segundo scheduler: ERPNext es el único propagador FS; SNET solo normaliza la Task que se
  guarda; FNLT es solo diagnóstico (no mueve fechas, no bloquea).
- No interceptar escrituras fuera de `Task.save()` (Gantt nativo `set_value`): se detectan read-only.
- El frente **Capacity** (default global en PMO Settings) NO entra en este release; vive aparte en
  `feat/pmo-capacity-default-settings`.

---

## Decisiones vigentes
- **SNET write-path acotado**: mutación in-memory en `before_validate` sobre `exp_start_date`/`exp_end_date`
  de la propia Task; nunca `save()` en cadena; días naturales; preserva la hora original.
- **FNLT = diagnóstico**: `exp_end > constraint_date` ⇒ finding `fnlt_violation`; no reprograma ni bloquea.
- **SSOT de clasificación en dominio** (`constraints.py`): estados/severidad/labels se deciden en backend;
  templates/JS solo presentan.
- **Deadline y FNLT son findings separados** (pueden coexistir sobre la misma Task).

---

## Archivos relevantes ahora
### Leer primero
- `pmo/constraints.py` — write-path SNET + clasificador SSOT + endpoint read-only.
- `pmo/scheduling.py` — `analyze_schedule_integrity` con `fnlt_violation`/`snet_violation`.
- `pmo/public/js/task_pmo.js` — indicador derivado en el form de Task.
- `docs/adr/0018-schedule-constraints.md`.
### Fuera de git (no commitear)
- `one_offs/qa_fnlt_dataset.py` — dataset QA II.2 (gitignored).
- `one_offs/capacity_paso1_backup/` — respaldo del frente Capacity (se restaura en su propia rama).

---

## Riesgos / cuidados
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- CI usa `ruff check` + `prettier@2.7.1` exactos; linters solo sobre `.py`/`.js`, nunca `.json`.
- `pyproject.toml` deriva la versión vía flit (`dynamic`); tocar solo `pmo/__init__.py::__version__`.
- El merge lo ejecuta el usuario en GitHub (Squash & Merge); Claude no llama a la API de merge.

## Información faltante
- Ninguna para continuar; PR contra `version-16`, merge por el usuario, luego release v0.21.0 + limpieza.
