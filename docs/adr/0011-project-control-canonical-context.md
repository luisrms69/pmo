# ADR-0011: Contexto canónico de Project Control — una fuente, muchas vistas

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Ciclo:** previo al Reporte Ejecutivo de Proyecto (post v0.15.0)

## Contexto

Project Control está por crecer con Capacity, RRHH, costos, Change Requests y Project Updates. La
auditoría del código actual encontró **duplicación incipiente**: `build_status_report()` (motor central
de estado/cronograma, impone P4), `pmo_project_status()` (contexto para el Print Format) y el nuevo
`get_header()` (Control Center B1) **componen KPIs parcialmente repetidos desde la misma fuente**;
además la Page `pmo_project_control` (arma HTML en JS desde Script Reports) y el Print Format
`PMO Project Status` (Jinja server-side) **renderizan por caminos distintos**. Sin una frontera
explícita, en pocos meses habrá varios reportes calculando lo mismo de maneras distintas.

Este ADR **fija la frontera de reporting** antes de agregar más dominios; no diseña el Reporte Ejecutivo
ni su implementación (eso irá en su PR).

## Problema

No existe un **contexto canónico** de Project Control. Cada vista nueva (Page, HTML, PDF, Portal) tiende
a recomponer o recalcular métricas por su cuenta → divergencia de fórmulas, doble mantenimiento y el
riesgo de que dos superficies muestren números distintos para el mismo proyecto y la misma fecha de corte.

## Decisiones

### D1 — Contexto canónico único: `build_project_control()`
Todo reporte **integral** de un Project consume un único compositor:

```python
build_project_control(project, cutoff=None, sections=None, audience="internal") -> dict
```

- Devuelve una **estructura estable** de secciones:
  `project · executive · schedule · baseline · exceptions · planning · resources · scope_changes ·
  hours · costs · freshness · updates`.
- `cutoff=None` → fecha de corte del Project o **hoy** (ADR-0006). `sections=None` → **contexto completo**;
  una **lista** explícita → subconjunto (performance / secciones bajo demanda). `audience` ∈
  `{internal, portal}`.
- **Compone, no recalcula.** Cada sección se llena llamando al motor de dominio correspondiente. Un KPI
  nuevo se agrega **aquí una sola vez**.

### D2 — Una fuente de verdad por dominio (los motores no se tocan)
`build_project_control()` **no** reimplementa dominios; los **orquesta**:

| Dominio | Fuente de verdad |
|---|---|
| Estado / cronograma / forecast | `build_status_report()` (ADR-0006/0009; **impone P4**) |
| Salud (semáforo) | `pmo/health.py` (fuente única; confirmada por este ADR) |
| Baseline / comparación | motor de Baseline (ADR-0004) |
| Capacity | motor de Capacity (ADR-0003) |
| Change Requests | lógica de CR (ADR-0005) |
| Horas | nativo (`Σ Task.expected_time` de hojas / `Project.actual_time`, ADR-0008) |
| Costos | ERPNext + agregador propio **solo si** no hay nativo (se define al abordar la sección) |

Si una métrica **ya existe** en un motor, se **consume**; **no se copia**.

### D3 — P4 es obligatorio y es independiente de `audience`
- La **privacidad P4** (ADR-0002) la sigue imponiendo el motor de dominio (p. ej. `build_status_report`
  hace `has_permission("Project","read", throw=True)`). `build_project_control()` **no** relaja ni
  sustituye P4.
- `audience` controla **qué se compone y qué se expone** (nivel de detalle, ocultamiento de datos
  internos para cliente), **no** los permisos. `audience="portal"` **nunca** amplía visibilidad: primero
  se aplica P4 (y, en portal, los permisos de Portal User), y sobre lo permitido se recorta la exposición.

### D4 — Vistas = consumidores (reglas normativas)
1. El **frontend** no calcula KPIs de negocio.
2. Un **template** no calcula lógica de negocio.
3. Ningún **PDF** reimplementa fórmulas.
4. Ningún **Portal** consulta y reconstruye el proyecto por su cuenta.
5. Si una métrica ya existe en un motor, **se consume; no se copia**.
6. **Page, HTML, PDF y Portal son consumidores, no fuentes de verdad.**
7. Los **wrappers existentes convergen** hacia el builder canónico: idealmente
   `pmo_project_status()` → `build_project_control()`, no cálculos propios paralelos. La convergencia es
   **progresiva** (no exige reescribir todo de golpe), pero no se admiten nuevas fórmulas duplicadas.

### D5 — Template canónico del Reporte Ejecutivo (representación ≠ norma global)
Lo único verdaderamente único es **lógica + métricas + contexto**. El **Reporte Ejecutivo** usa **un**
template reutilizado en `Page → HTML → PDF → Portal`, con diferencias mínimas de impresión/permisos.
Esto **no** obliga a toda PMO a usar ese mismo HTML: otros reportes pueden tener su propia representación,
pero **consumen las mismas fuentes**. Frontera de carpetas (se establece, no se llena entera hoy):

```
pmo/
 ├─ project_control.py            ← composición canónica (build_project_control)
 ├─ health.py                     ← health canónico
 ├─ ... motores (status_date, baseline, capacity, change requests)
 └─ templates/project_control/
        executive.html · macros.html · print.css
```

### D6 — Reportes especializados pueden consumir su motor directamente
No todo reporte necesita el contexto integral. Un reporte especializado (p. ej. `PMO Capacity Planning`,
`PMO Portfolio`) **puede consumir directamente su motor de dominio** cuando no requiere todas las
secciones. La regla es "**una fuente por dominio + composición compartida**", no "todo pasa por
`build_project_control()`". Ejemplos: Portfolio = status engine + *summaries* de project-control;
Capacidad = capacity engine; Ejecutivo = `build_project_control()`.

### D7 — Sin sobre-ingeniería por el ADR
No se crean módulos, capas ni abstracciones nuevas **solo** para satisfacer este ADR. El ADR **fija la
frontera**; la estructura de `templates/project_control/` y las secciones se materializan cuando su
reporte las necesite, no antes.

## Fuera de alcance (de este ADR)
- Diseño e implementación del Reporte Ejecutivo y su migración desde el Control Center B1 (`26c7dbb`) —
  irá en su PR sobre `feat/pmo-reporting-architecture`.
- Portal (fase posterior). El ADR solo garantiza que `audience="portal"` + template compartido lo hacen
  posible sin duplicar; no define su implementación.
- Definición del agregador de **costos** (se decide al abordar esa sección).
- Cualquier cambio a los motores de dominio existentes (ADR-0002/0003/0004/0005/0006/0008/0009).

## Consecuencias
- Un solo lugar donde vive y evoluciona el contexto de Project Control; Page/HTML/PDF/Portal muestran
  siempre lo mismo para el mismo `(project, cutoff)`.
- `get_header()` (B1) se absorbe como **semilla de la sección `executive`**; `pmo_project_status()` pasa
  a **wrapper delgado** del builder.
- Coste inicial: un refactor de consolidación **antes** de seguir agregando dominios (se paga una vez).
- Los reportes futuros nacen con una regla clara: consumir motores/contexto, no reimplementar.

## Alternativas descartadas
- **Dejar que cada vista componga** (statu quo) → varios reportes duplicando lógica en pocos meses.
- **Un mega-motor que recalcule todo** → monstruo que duplica los motores de dominio; se rechaza
  (D2: componer, no recalcular).
- **Un HTML único obligatorio para toda PMO** → se rechaza; lo único único es el contexto, no la
  representación (D5/D6).
- **`audience` como mecanismo de permisos** → se rechaza; P4 es obligatorio e independiente (D3).

## Criterios de aceptación
- Existe (al implementarse) `build_project_control(project, cutoff, sections, audience)` con la estructura
  estable de D1, que **compone** (no recalcula) los motores de D2.
- `pmo_project_status()` y toda vista nueva **consumen** el builder / los motores; no hay una segunda
  implementación de las mismas fórmulas.
- P4 sigue impuesto por los motores de dominio y **no** es sustituido por `audience` (D3).
- El Reporte Ejecutivo se representa con el template de D5, reutilizable en Page/HTML/PDF y preparado para
  Portal.
- `pmo/health.py` sigue siendo la única fuente de salud.
- No se introducen módulos/abstracciones nuevos que no tengan un consumidor real (D7).
