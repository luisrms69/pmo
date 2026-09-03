# CONTINUITY.md — pmo

**Fecha:** 2026-09-02
**Rama activa:** `docs/adr-0002-project-task-privacy` (base `version-16`) — es la rama del bloque **P0 privacidad** (el nombre se ajusta al abrir el PR).
**Tarea actual:** Implementación incremental de ADR-0002 (privacidad Project/Task). Incremento 1 (READ) cerrado.

---

## Recuperación rápida

Estoy trabajando en:
P0 privacidad por incrementos en una sola rama; **un solo PR** al cerrar el bloque completo.
Incremento 1 (READ) commiteado como checkpoint local. Sigue Incremento 2 (WRITE).

Plan que estoy siguiendo:
`docs/adr/0002-project-task-privacy.md` (+ `0003` para capacity, diferido).

Objetivo inmediato:
Incremento 2 — WRITE (owner escribe Project; member escribe Tasks no Project; assignee solo su Task; executive read-only), refinando `has_permission` para no diferir write.

Criterio de avance:
READ y WRITE en commits **separados** (capas de seguridad distintas, revertibles por separado). Sin push ni PR hasta cerrar el bloque.

---

## Estado actual

### Ya cerrado
- ADRs 0002/0003 (commit `ff9d2a2`, checkpoint local).
- **Incremento 1 — READ:** `PMO Project Member`, roles PMO, `pqc`+`has_permission` READ (Project/Task), fixtures. Tests 5; suite **24/24 OK**. Verificado en `test-pmo.localhost` (migrado).
  - Confirmado: `assign_to` NO crea auto-share (visibilidad por ToDo activo) → D8/ADR-0002.

### En progreso / pendiente
1. **Incremento 2 — WRITE.**
2. **Incremento 3 — SHARE/Assignment** (incl. verificación P0 `has_permission(ptype="share")` grant-vs-restrict; si no concede → fallback Custom DocPerm completo).
3. **Incremento 4 — auditoría de vectores** (query reports, `create_duplicate_project`, Global Search, attachments).
4. **Antes del PR final de P0 — gate documental ampliado:** además de `docs/tecnico/arquitectura.md`, incluir **`docs/usuario/`** (comportamiento visible): Project/Task privados por defecto; diferencia miembro de Project vs asignado a una Task; qué ve cada caso; acceso ejecutivo; restricciones de Share.
5. **Bump de versión** del bloque privacidad → **0.2.0** (MINOR) antes del PR (recalcular contra upstream 0.1.0).

### No repetir / cuidados
- Fixtures del app en `apps/pmo/pmo/fixtures/` (nivel paquete), no en el módulo.
- Warning `limit_page_length` en tests es **interno de Frappe** (no accionable).
- Rutas Desk v16 = `/desk/...`. Git solo vía `/ship`. No trabajar en `version-16`.
- No agrupar READ+WRITE en un commit.
- No empezar Capacity (ADR-0003) hasta cerrar P0.

---

## Decisiones vigentes
- ADR-0002: aislamiento fail-closed (owner/PMO Project Member/Task assignee-ToDo/Executive/Share); enforcement `pqc`+`has_permission` sin tocar DocPerms de read/write; SHARE manual solo `PMO Executive Access`/`Administrator` (hook `ptype=share`, con fallback DocPerm).
- Nota config: `PMO Executive Access` da alcance global (pqc vacío) pero necesita además un rol con read (p.ej. `Projects User`).

---

## Archivos relevantes ahora
- `pmo/permissions.py` (pqc + has_permission), `pmo/hooks.py` (wiring), `pmo/pmo/doctype/pmo_project_member/`, `pmo/fixtures/{custom_field,role}.json`, `pmo/pmo/tests/test_privacy_read.py`.
- Para WRITE: refinar `has_permission_project`/`has_permission_task` (write) en `pmo/permissions.py` + tests nuevos.

---

## Riesgos / cuidados
- `pqc` no cubre query reports ni `get_all`/whitelisted (`create_duplicate_project`) → Incremento 4.
- Pruebas funcionales completas con Company/Stock requieren otro site (test-pmo mínimo → se usa `ignore_mandatory`).
