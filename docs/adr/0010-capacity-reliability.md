# ADR-0010: Confiabilidad de Capacity Planning — señal honesta y cobertura

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Accepted · **Ciclo:** v0.11.0 (último funcional antes de la revisión global)

## Aceptación (2026-09-09)

Implementado en v0.11.0 sin desviaciones respecto de D1–D3. **A:** `PMO Capacity Planning` marca `has_cap` por
fila; sin capacidad vigente → `capacity/availability/free/overallocation/util_*` = `None` (no 0), no cuenta
como sobreasignado y conserva `status="capacidad faltante"`; chart blindado ante `None`. **B:** KPI "Recursos
sin capacidad vigente" (recursos con actividad sin capacidad) y *Sobreasignados* ignora `None`. Solo capa de
reporte: sin DocTypes/Custom Fields/fixtures, sin cambios a `capacity.py`/`availability.py`/`planned_load.py`,
ADR-0003 sin modificar; no requiere `bench migrate`. C (Tentativo/Confirmado) y demás pendientes quedan en
`docs/roadmap.md` para la revisión global. Verificado: capacity report 17/17, suite 237/237.

## Contexto

Capacity Planning (ADR-0003) ya deriva capacity/availability/planned/actual y el reporte `PMO Capacity
Planning` calcula Libre, **Sobreasignación**, utilizaciones y un KPI *Sobreasignados*. La auditoría v0.11.0
encontró que el modelo es sólido, pero **la señal de sobreasignación es engañosa cuando falta capacidad
configurada** y **no hay visibilidad de esa carencia**.

## Problema

1. Si un recurso no tiene `PMO Capacity` vigente, el reporte agrega `availability = 0`; entonces
   `overallocation = max(0, planned − 0) = planned` y el recurso aparece **"sobreasignado"** y suma al KPI
   *Sobreasignados*, cuando la causa real es **capacidad sin configurar** → falsos positivos.
2. **No existe** visibilidad de cuántos recursos con actividad en el periodo **carecen** de `PMO Capacity`
   vigente → el hueco pasa inadvertido y el plan queda incompleto en silencio.

## Decisiones

### D1 — `None` (no derivable) ≠ `0` para recursos sin capacidad (A)
En `PMO Capacity Planning`, por cada fila Employee×periodo se marca `has_cap` = si **algún** día del periodo
tiene capacidad resoluble (`get_capacity` ≠ None). Si `has_cap` es **falso**:
- `capacity`, `availability`, `free`, `overallocation`, `util_planned`, `util_actual` = **`None`** (no `0`).
- La fila **no** cuenta como sobreasignada ni entra en la utilización media.
- Se mantiene el marcador explícito `status = "capacidad faltante"`.

Si `has_cap` es verdadero, se conserva el cálculo actual (los días sin capacidad aportan 0 de disponibilidad,
que es una ausencia **real** de ese día). **No** se modifica `capacity.py`/`availability.py` (ya devuelven
None correctamente); el ajuste es **capa de reporte**.

### D2 — KPI de cobertura de capacidad (B)
El resumen agrega **"Recursos sin capacidad vigente"** = nº de Employees **con actividad en el periodo**
(los que aparecen en el plan) cuya capacidad es no resoluble en todas sus filas (Naranja si > 0). Reutiliza
el `data` ya construido con el scope/permisos del observador (no crea modelo ni segunda consulta de scope).
Esos recursos siguen visibles como filas con `status = "capacidad faltante"` y métricas `None` (D1).

**Alcance del conteo (decisión explícita):** se cuentan los recursos **con actividad** sin capacidad (los que
generan el hueco real y los falsos positivos que D1 corrige). Los Employees del alcance **sin actividad y sin
capacidad** no aparecen en el plan y quedan fuera de este conteo (no afectan la planificación); promoverlos a
un conteo de "cobertura total del alcance" es un posible refinamiento posterior, no de v0.11.0.

### D3 — Sin modelo nuevo ni esquema
Cambios **solo** en `pmo/pmo/report/pmo_capacity_planning/` (+ tests). **Sin** DocTypes, Custom Fields,
fixtures ni cambios a `capacity.py`/`availability.py`/`planned_load.py`. No requiere `bench migrate`. El KPI
*Sobreasignados* pasa a contar solo sobreasignación **real** (con capacidad presente).

## Fuera de alcance (diferido — ver `docs/roadmap.md`)
- **C — Tentativo/Confirmado** y `ToDo.pmo_commitment` (revisión global; `roadmap.md` #1).
- Cualquier **Custom Field** nuevo.
- Reservas de capacidad (**#10**), CPM/ruta crítica (**#9**), constraints tipados SNET/FNLT/MSO/MFO
  (`roadmap.md` #4).
- UX de `pmo_planned_hours` (`roadmap.md` #5) y UX de captura de `PMO Capacity` (`roadmap.md` #6).
- Cambios al modelo derivado de ADR-0003 y al diálogo nativo "Assign To".

## Consecuencias
- *Sobreasignación* y *Sobreasignados* reflejan solo sobreasignación real; sin falsos positivos por capacidad
  faltante.
- Los managers ven cuántos recursos necesitan configuración de capacidad.
- Cambio de presentación acotado, sin esquema ni migración; riesgo bajo.

## Riesgos
- **Cambio de semántica de salida:** columnas antes `0` ahora pueden ser `None` (se muestran vacías/"N/D")
  para recursos sin capacidad → tests actualizados y documentado.
- Periodo **parcialmente** configurado (algunos días con capacidad, otros no) → `has_cap` verdadero y se usa
  la disponibilidad de los días configurados; documentado para evitar confusión.

## Alternativas descartadas
- **Dejar `0`** (statu quo) → mantiene los falsos positivos.
- **Ocultar** del reporte a los recursos sin capacidad → se prefiere mostrarlos con `None` + `status`.
- **DocType/Custom Field de cobertura** → innecesario; se deriva de `get_capacity` + `data` ya scoped.

## Criterios de aceptación
- Recurso sin `PMO Capacity` vigente en el periodo → `availability`/`free`/`overallocation`/`util_*` = `None`;
  **no** cuenta en *Sobreasignados*; `status` incluye "capacidad faltante".
- Recurso con capacidad y `planned > availability` → sigue reportando `overallocation > 0` y cuenta en
  *Sobreasignados* (sin regresión).
- Resumen incluye **"Recursos sin capacidad vigente"** con conteo correcto.
- Sin DocTypes/Custom Fields/fixtures; sin cambios a `capacity.py`/`availability.py`/`planned_load.py`;
  ADR-0003 sin modificar. Tests de la lógica pura (None vs 0, conteo de cobertura, no-regresión de
  sobreasignación real).
