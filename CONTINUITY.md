# CONTINUITY.md — pmo

**Fecha:** 2026-09-02
**Rama activa:** `docs/adr-0002-project-task-privacy` (base `version-16`)
**Tarea actual:** Versionar ADR-0002 y ADR-0003 (decisiones arquitectónicas base). Luego iniciar P0 (privacidad).

---

## Recuperación rápida

Estoy trabajando en:
Commit de **ADR-0002** (Project/Task Privacy) y **ADR-0003** (Resource Capacity), estado *Propuesto*,
en `docs/adr-0002-project-task-privacy`. Bump 0.1.1 (docs).

Plan que estoy siguiendo:
Diseño cerrado en `docs/adr/0002-project-task-privacy.md` y `docs/adr/0003-resource-capacity.md`.

Objetivo inmediato:
Tras el commit: `/ship push` → `/ship pr` (base `version-16`). Después **iniciar P0 — privacidad**.

Criterio de avance:
Cada paso git con autorización separada; los ADR son base, no inmutables (cambios materiales vuelven al ADR).

---

## Estado actual

### Ya cerrado
- ADR-0002 y ADR-0003 consolidados como candidatos *Propuesto* (READ/WRITE/SHARE, P4, capacity mínimo).
- pmo 0.1.0 en producción (Gantt por lft + importador de Tags); CI con required_status_checks.

### En progreso
- Commit/push/PR de los dos ADR.

### Pendiente inmediato
1. `/ship push` + `/ship pr` a `version-16` (con autorización).
2. **P0 — privacidad Project/Task** (desde ADR-0002), en incrementos: READ mínimo → WRITE → SHARE/Assignment → auditoría de vectores.
3. Verificación P0 bloqueante: `has_permission(ptype="share")` grant vs restrict (ADR-0002 D7); si no concede → fallback Custom DocPerm completo.

### No repetir / cuidados
- No implementar Capacity (ADR-0003) hasta cerrar P0.
- No resolver toda la seguridad en un solo cambio; incrementos comprobables.
- Rutas Desk v16 = `/desk/...`. Git solo vía `/ship`. No trabajar en `version-16`.

---

## Decisiones vigentes
- **ADR-0002:** aislamiento fail-closed (owner/PMO Project Member/Task assignee vía ToDo/Executive/Share); enforcement `pqc`+`has_permission` sin tocar DocPerms de read/write; SHARE manual solo `PMO Executive Access`/`Administrator` (vía hook `ptype=share`, con fallback DocPerm); membresía `PMO Project Member` simple (sin `pmo_role`).
- **ADR-0003:** `PMO Capacity` (efectivo-datado, global+override), `PMO Resource Allocation` (Project req/Task opc, sin conceder acceso) + `PMO Allocation Day` (child, días materializados en Confirmed); Availability/Actual derivados (no reproducibles retroactivamente); P4 enmascara identidad de proyecto.

---

## Archivos relevantes ahora
- `docs/adr/0002-project-task-privacy.md`, `docs/adr/0003-resource-capacity.md` (decisiones base).
- Para P0: `pmo/hooks.py` (registrar `permission_query_conditions`/`has_permission`), nuevo `PMO Project Member`, roles `PMO Manager`/`PMO Executive Access`.

---

## Riesgos / cuidados
- `pqc` no cubre query reports ni `get_all`/whitelisted (ej. `create_duplicate_project`) → auditar en P0.
- P0 requiere site con Company/Stock para pruebas funcionales completas (no `test-pmo.localhost` mínimo).
