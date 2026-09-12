# Panel PMO (workspace de entrada)

Tablero operativo de la oficina de proyectos, con política **native-first**
(`docs/tecnico/native-first-ui.md`). Primero dimensiona la PMO, luego lleva a los problemas.

## Secciones

1. **PMO at a glance** — Number Cards nativas de tamaño/estado: Active projects · Active tasks ·
   People involved · **Requiring attention** (proyectos At risk/Deviated) · **Overdue tasks**.
   (No se muestran horas sin periodo aquí.)
2. **Health & capacity** — Dashboard Charts nativos Report-type: donut **Portfolio health** +
   **Capacity — current month** (Capacity / Available / Planned / Actual / Free del **mes actual**,
   agregado del reporte PMO Capacity Planning).
3. **Top projects by effort** — chart Report-type **Top 5 by planned hours** (reutiliza PMO Portfolio).
4. **Requires attention** — bloque PMO (jerárquico): por proyecto, cabecera (Project · Health ·
   Customer) + chips (forecast, slip BL, slip commit, overdue, plan/real) + **motivo** legible;
   clic → Project Control. Debajo, **Most overdue tasks** (clic → Task).
5. **Portfolio** — bloque PMO **Portfolio by customer** (Customer · Active projects · At risk/Deviated ·
   Planned/Actual) + Number Card **Active clients**.
6. **PMO governance** — Number Card **Projects without baseline** (señal accionable) + Quick List de
   **Open change requests** + card de links (PMO Project Baseline · PMO Change Request · PMO Capacity ·
   Import Tags).
7. **Explore** — Shortcuts (Portfolio · Project Control · Capacity Planning) + card **Reports** (9).

## KPIs — definición y periodo
- **Active projects / Active tasks / People involved / Requiring attention / Overdue tasks / Projects
  without baseline / Active clients:** derivados de PMO Portfolio (proyecto/tarea, sin periodo — son
  conteos de estado) y del motor de capacidad (People involved = recursos con capacidad o actividad en
  el **mes actual**).
- **Capacity chart:** **mes actual** (título explícito). **Top 5:** horas planificadas totales del
  proyecto (esfuerzo, no periodo).

## Privacidad (P4)
Todo server-side (PMO Portfolio, get_list con pqc, Capacity Planning con enmascarado). Charts
Report-type (sin caché global). Number Cards Custom con caché **por-usuario**. Sin `get_all`.
