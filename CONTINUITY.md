# CONTINUITY.md — pmo

**Fecha:** 2026-10-07
**Rama activa:** `feat/pmo-capacity-default-settings` (base `version-16` @ v0.21.0 → objetivo PR **v0.22.0**, MINOR)
**Tarea actual:** `/ship pr` de cierre **v0.22.0** — **Capacity / HRMS** (Pasos 1–4): la capacidad pasa a
derivarse de **HRMS Shift** (dependencia requerida) con fallback a **PMO Settings**; el calendario laboral
se resuelve por **Holiday List Assignment**. `PMO Capacity` queda **deprecado y sin consultar**.

---

## Recuperación rápida

Estoy trabajando en:
El **cierre `/ship pr` de la rama `feat/pmo-capacity-default-settings`** hacia `version-16` (objetivo
v0.22.0, MINOR). Capacity Pasos 1–4 implementados y validados; suite **614 + 122 OK** (Redis estable);
QA funcional en `pmo-v16.dev` ✅ (Shift neto, fallback sin turno + rojo, Holiday List Assignment).

Plan que estoy siguiendo:
`/ship pr`: bump 0.21.0→0.22.0 + CONTINUITY → gate `pr-ready` (DETENER para autorización) → push + PR hacia
`version-16`. **Sin merge** (lo autoriza el usuario con `/ship merge`); luego `/ship release` v0.22.0.

Objetivo inmediato:
PR OPEN contra `version-16` con el frente Capacity/HRMS, listo para merge (CI en verde).

Criterio de avance:
PR OPEN, working tree limpio, versión 0.22.0 en la rama; luego merge + release.

---

## Estado actual

### Modelo vigente (Capacity Paso 4)
- **Capacidad = jornada neta desde HRMS Shift** (HRMS **requerido**): `get_shifts_for_date` (Shift
  Assignment submitted/Active) → `Employee.default_shift`; neta = span `(end−start)` −
  `Shift Type.pmo_unpaid_break_minutes` (Custom Field; cruce de medianoche +24 h).
- **Fallback:** `PMO Settings.default_capacity_hours_per_day` (patch idempotente lo inicializa en 8) → None.
- **Availability** = Capacity − festivos (Holiday List resuelta por **`Holiday List Assignment`**) − Leave.
- **Reporte `PMO Resource Capacity`**: origen `Turno`/`Predeterminado`/`Faltante`; **rojo** cuando falta
  turno (informativo). `PMO Capacity` **deprecado, no consultado** (DocType presente; retiro posterior).

### Ya cerrado (en la rama)
- **Paso 1** (`4e23359`): default global en PMO Settings + patch `init_default_capacity_hours`.
- **Paso 2** (`b2e7fe3`): normalización conceptual del default global.
- **Paso 3**: investigación HRMS (sin código).
- **Paso 4** (working tree de este PR): resolver por Shift, `required_apps=["erpnext","hrms"]`, Custom
  Field `Shift Type-pmo_unpaid_break_minutes`, reporte de cobertura + rojo, Holiday List Assignment en
  tests, CI instala hrms, traducciones, y reconciliación de ADR-0003/0010/arquitectura/roadmap/usuario.

### Pendiente inmediato
1. Gate `pr-ready` → autorización → push + PR hacia `version-16`.
2. CI del PR en verde (CI ahora instala hrms).
3. Merge (`/ship merge`) → `/ship release` tag+Release `v0.22.0`.

### No repetir / no ampliar
- No retirar todavía el DocType `PMO Capacity` (decisión: ciclo posterior).
- No reintroducir `PMO Capacity` en el resolver (fuente = Shift → Settings → None).
- No tocar core/ERPNext/HRMS; sin Property Setters.

---

## Decisiones vigentes
- **HRMS dependencia requerida** (`required_apps=["erpnext","hrms"]`); fuente de jornada = Shift; calendario
  por `Holiday List Assignment`.
- **Jornada neta** = span del Shift − descanso (`pmo_unpaid_break_minutes`); nunca negativa.
- **Custom Field de Shift Type** por **fixture** (HRMS requerido → `Shift Type` siempre existe).
- `missing_shift` (sin turno, aun con default) se muestra en **rojo**: informativo, no bloqueante.

---

## Archivos relevantes ahora
### Leer primero
- `pmo/capacity.py` — resolver SSOT `get_employee_daily_capacity` (Shift → Settings → None).
- `pmo/availability.py` — Availability sobre Capacity, holidays por Holiday List Assignment.
- `pmo/pmo/report/pmo_resource_capacity/` — cobertura + formatter rojo.
- `docs/adr/0003-resource-capacity.md`, `docs/adr/0010-capacity-reliability.md`.
### Fuera de git (no commitear)
- `one_offs/qa_capacity_shift.py`, `one_offs/qa_capacity_cleanup.py` — QA dev-only (gitignored).

---

## Riesgos / cuidados
- La suite corre en dos lotes (integración + unitarios); no leer solo el último "Ran N".
- Redis del bench v16 (13001/11001) ha sido inestable; requiere `bench start` para correr tests.
- CI usa `ruff` + `prettier@2.7.1`; linters solo `.py`/`.js`, nunca `.json`.
- `pyproject.toml` deriva la versión vía flit; tocar solo `pmo/__init__.py::__version__`.
- Instalación: `required_apps` ahora incluye **hrms**; todo sitio con PMO debe tener HRMS.

## Información faltante
- Ninguna para continuar; PR contra `version-16`, merge por el usuario, luego release v0.22.0.
