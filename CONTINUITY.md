# CONTINUITY.md — pmo

**Fecha:** 2026-09-08
**Rama activa:** `feat/change-control` (base `version-16` @ v0.5.0).
**Estado:** **v0.6.0 — Integrated Change Control (ADR-0005) VALIDADO.** Commit del bloque + bump
`__version__ → 0.6.0`; se procede a `/ship push` + `/ship pr` (PR hacia `version-16`). **No merge/tag/release.**

## Plan que estoy siguiendo
`docs/adr/0005-integrated-change-control.md` (Accepted) + revisión funcional v0.6.0. Bloques 1–5 + UX 5.1/5.2
✅. Punto 1 (retiro `PMO Project Member`) ✅. Integración con contrato publicado de `erpnext_proposals
v0.22.0` ✅. E2E formal en `proposals-acti.dev` **PASS**.

## Qué se implementó en este bloque
- **Integración Change Control ↔ `erpnext_proposals v0.22.0`** por delegación (`pmo/change_control.py`,
  `frappe.get_attr` feature-detection): `create_addendum_quotation` + `apply_addendum_to_project`. Sin elevar
  permisos, sin duplicar lógica. Precondición: `erpnext_proposals >= 0.22.0`.
- **Acción `crear_addenda`** en `PMO Change Request` (autoría comercial la impone `erpnext_proposals`;
  P4 exige `write` sobre el CR editable) + botón "Crear addenda comercial". `Ganada ≠ Aplicada`.
- **Retiro definitivo de `PMO Project Member` SIN patch** (regla del proyecto: no migration patches):
  eliminada la línea de `patches.txt` y borrado `pmo/patches/v0_6_0/`. Membresía derivada nativa
  `owner + DocShare(Project) + ToDo` (ya vigente desde `319ad00`).
- Docs: ADR-0002 (retiro sin patch), ADR-0005 (contrato v0.22.0 + doble autoridad + precondición),
  `arquitectura.md`, `usuario/change-control.md`. Tests cruzados en `test_change_request.py`.
- Bump `__version__` 0.5.0 → **0.6.0** (MINOR).

## Evidencia de validación
- Suite completa PMO: **191/191** (`test-pmo.localhost`).
- `ruff` + `prettier@2.7.1` + `mkdocs build --strict`: verdes.
- **E2E formal v0.6.0 en `proposals-acti.dev`: PASS** (exit 0). ROOT `SAL-QTN-2026-00040` → `PROJ-0071`
  (3 Tasks) → CR `PMO-CR-00004` → addenda `SAL-QTN-2026-00041` (`…-ADD-01`) → aplica solo el delta (2 Tasks:
  `TASK-2026-00027/00028`), `proposal_project`/`applied_*` correctos, idempotencia, guard Project incorrecto,
  rollback transaccional. Evidencia documental verificada 1×1.

## Decisión operativa importante (no está en código)
- **`proposals-acti.dev`** requirió una **limpieza one-off manual** de metadata legacy (`Custom Field
  Project-pmo_members` + DocType `PMO Project Member`, 0 filas) para que `Project` cargara. Se hizo con APIs
  Frappe (sin SQL destructivo), **no** como patch. Vive en `one_offs/` (gitignored).
- **`pmo-v16.dev` tiene 3 filas** en `PMO Project Member`: su limpieza está **bloqueada** (el guard aborta si
  hay filas) hasta decidir qué hacer con esas membresías. Pendiente del usuario.
- Los sitios `test-pmo.localhost` ya está limpio (el patch, ahora retirado, corrió ahí antes).

## Siguiente paso
Crear el PR `feat/change-control → version-16` (v0.6.0, MINOR) y detenerse. No merge/tag/release.

## Cuidados / no repetir
- Git solo vía `/ship`. Nunca trabajar en `version-16`. **En pmo NO se usan migration patches.**
- `erpnext_proposals` tiene ruta anidada `apps/erpnext_proposals/erpnext_proposals/erpnext_proposals/…`;
  contrato en `utils/addendum.py` (`create_addendum_quotation`) y `utils/project.py` (`apply_addendum_to_project`).
- `one_offs/` ignorado (E2E, cleanup, inspector). Linters solo `.py`/`.js`, nunca `.json`.
- BD / `bench migrate`: autorización explícita. Tests en `test-pmo.localhost`. Rutas Desk v16 = `/desk/...`.
