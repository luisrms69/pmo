# Baselines de proyecto (PMO Project Baseline)

Una **baseline** es una foto **aprobada y congelada** del plan de un Project: sirve como referencia
estable contra la cual medir cambios y desempeño más adelante. No modifica el proyecto; solo lo
fotografía.

> Es una baseline de **cronograma / plan operativo** (tareas, jerarquía, fechas, horas, asignaciones,
> dependencias). No pretende ser una "scope baseline" contractual completa.

## Cómo se crea

1. Nuevo **PMO Project Baseline** y elige el **Project**.
2. Indica:
   - **Revision** (etiqueta legible, p. ej. `BL-001`), única dentro del proyecto.
   - **Baseline Type**: `Original`, `Approved Change` o `Replan`.
   - **Supersedes Baseline**: obligatorio salvo en la `Original` (debe apuntar a la baseline vigente que
     reemplaza).
   - **Effective Date**: fecha de vigencia (no puede ser futura).
   - **Reason** (motivo).
3. **Guarda** (borrador) y, cuando el plan esté listo, **Submit**.

Al hacer **Submit** se congela todo automáticamente: se captura el **snapshot** del proyecto, se calcula
su huella (`snapshot_hash`) y se registran **quién aprueba** (`Approved By`) y **cuándo** (`Approved
At`). El Submit **es** la aprobación.

## Cadena de baselines (trazabilidad)

Las baselines de un proyecto forman una **cadena lineal**:

```
BL-001 Original  →  BL-002 Approved Change  →  BL-003 Replan
```

- Solo puede haber **una `Original`** por proyecto.
- Cada nueva baseline **reemplaza la vigente** (no se permiten ramificaciones).
- La **baseline vigente** en una fecha se deduce de la cadena y de la `Effective Date` (la más reciente
  ya efectiva). Puedes aprobar una nueva baseline hoy con vigencia anterior a hoy, pero **no** a futuro.

## Antes de congelar (revisión)

Al congelar se ejecuta una **revisión ligera** que muestra *avisos* (no bloquean): tareas hoja sin
fechas, fases (`is_group`) con esfuerzo u horas asignadas, fechas de fase desactualizadas respecto de sus
hijas, asignaciones sin Employee, etc. Solo se **impide** congelar si el reparto de horas de alguna tarea
es matemáticamente inconsistente (no se puede fijar un plan de recursos inequívoco).

## Quién puede qué (privacidad)

- **Ver** una baseline: quien puede ver el Project (owner, miembro, acceso ejecutivo). Nunca verás
  baselines de proyectos que no te corresponden.
- **Crear / editar / aprobar (Submit) / cancelar**: el **dueño del Project**.
- **Acceso ejecutivo**: solo lectura.

La aprobación por autoridades adicionales (Sponsor / comité de cambios) llegará en una fase posterior.

## Notas

- Una baseline nueva es un **documento nuevo** (no un "Amend" de la anterior). Cancelar solo sirve para
  anular una baseline creada por error.
- La **comparación** entre baselines (o baseline vs plan actual) aún no está disponible; el snapshot ya se
  guarda con el detalle necesario para incorporarla más adelante.
