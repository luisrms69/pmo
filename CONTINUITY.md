# CONTINUITY.md — pmo

**Fecha:** 2026-09-09
**Rama activa:** `feat/capacity-reliability` (base `version-16` @ v0.10.0, commit `8218a31`).
**Ciclo:** v0.11.0 — Confiabilidad de Capacity Planning (ADR-0010, **Accepted**). Bump a 0.11.0 incluido.
**Último ciclo funcional** de la ronda; después → **revisión global de producto** (no otro ciclo automático).

## Plan que estoy siguiendo
ADR-0010 (A+B), solo capa de reporte, sin esquema:
- **A** — señal honesta: sin capacidad vigente → `capacity/availability/free/overallocation/util_*` = `None`
  (no 0); no cuenta como sobreasignado; `status="capacidad faltante"`.
- **B** — KPI "Recursos sin capacidad vigente" (recursos **con actividad** en el periodo sin capacidad).
Entrega en 2 bloques → PR único a `version-16`.

## Estado por bloques
- **Bloque 1 — motor de presentación + tests + backlog. ✅ (commit en curso)**
  - `pmo_capacity_planning.py`: `has_cap` por bucket (A) + KPI cobertura y *Sobreasignados* ignora None (B);
    chart blindado ante `None`.
  - `docs/roadmap.md`: backlog durable (6 pendientes + revisión global; referencia #9/#10).
  - ADR-0010 Proposed. Tests: +1 integración (sin capacidad → None) + clase pura (3). **Suite 237/237**;
    capacity report 17/17.
- **Bloque 2 — docs + bump + ADR Accepted. ✅ (commit en curso)**
  - ADR-0010 → Accepted; docs usuario (N/D + KPI cobertura) + arquitectura (subsección ADR-0010) + CHANGELOG
    `[0.11.0]`; bump 0.10.0 → 0.11.0. Sin funcionalidad nueva. Suite 237/237.

## Backlog diferido (docs/roadmap.md) — para la revisión global
1. Tentativo/Confirmado (posible `ToDo.pmo_commitment`) — sin issue, decidir forma en revisión global.
2. Reservas de capacidad — **issue #10**. 3. CPM/ruta crítica — **issue #9**.
4. Constraints tipados SNET/FNLT/MSO/MFO — sin issue. 5. UX `pmo_planned_hours`. 6. UX captura `PMO Capacity`.

## Alcance / límites (ADR-0010)
- Solo `pmo/pmo/report/pmo_capacity_planning/` + tests. Sin DocTypes/Custom Fields/fixtures. Sin cambios a
  `capacity.py`/`availability.py`/`planned_load.py`. ADR-0003 sin modificar. No requiere migrate. C diferido.

## Siguiente paso
Bloques 1 y 2 commiteados. Falta: `/ship push` → `/ship pr` (base `version-16`) → CI. Tras merge (usuario):
`/sync-check` → `/ship release` v0.11.0. **Tras liberar: DETENER — revisión global de producto** (priorizar
`docs/roadmap.md`), no iniciar otro ciclo automáticamente.

## Cuidados / no repetir
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Para forzar "sin capacidad" en tests con capacidad global 2026, consultar un periodo 2025 (get_capacity None).
- Git solo vía `/ship`. Nunca trabajar en `version-16`. pmo NO usa migration patches ni MkDocs.
