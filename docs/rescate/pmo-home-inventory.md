# Inventario de preservación — Home PMO (rescate)

> **Control de preservación del rescate de PMO Home.** Nada listado aquí puede eliminarse sin
> decisión explícita posterior. Este documento se actualiza durante todo el rescate (`origen →
> destino provisional → estado`) para demostrar al cierre que no se perdió ninguna capacidad.
>
> - **Rama:** `feat/pmo-home-rescate` (base `version-16` @ v0.17.0, commit `c3490ca`).
> - **Fecha de levantamiento:** 2026-09-26.
> - **Estado inicial de todo:** `Preservado` (nada retirado ni marcado eliminable).
>
> Destinos provisionales posibles (TBD, no decididos): (1) Portafolio · (2) Project Control ·
> (3) Capacity · (4) Reportes · (5) redundante → eliminable.

## Leyenda de estado
- **Preservado** — sigue existiendo y disponible; aún sin decisión de destino.
- **Reubicado** — retirado solo de la composición/navegación visible; definición y backend intactos.
- **Sustituido (versionado)** — definición previa preservada de forma versionable antes de reemplazar.
- **Eliminado** — solo tras decisión explícita y demostración de no pérdida de capacidad.

---

## A. Workspaces (composición/navegación visible)

| Workspace | seq | Contenido | Estado |
|---|---|---|---|
| **PMO** (Home) | 10 | 3 shortcuts, 3 charts, 7 number cards, 2 custom blocks, 1 quick list, 2 card breaks | Preservado — Home a reorganizar |
| **PMO Governance** | 20 | 1 custom block, 1 quick list, 5 card breaks | Preservado |
| **PMO Capacity** | 20 | 3 shortcuts | Preservado |
| **PMO Control** | 30 | 4 shortcuts | Preservado |
| **Sidebar PMO** | — | 5 links (PMO, Portfolio, Project Control, Capacity Planning, PMO Governance) | Preservado |

## B. Componentes de la Home "PMO"

### B1. Shortcuts (Pages)
| Origen | Capacidad | Destino provisional (TBD) | Estado |
|---|---|---|---|
| Shortcut → `pmo_portfolio` | Portafolio (Page) | Portafolio | Preservado |
| Shortcut → `pmo_project_control` | Project Control (Page) | Project Control | Preservado |
| Shortcut → `capacity_planning` | Capacity (Page) | Capacity | Preservado |

### B2. Charts (Dashboard Charts, tipo Report)
| Origen | Motor | Destino provisional (TBD) | Estado |
|---|---|---|---|
| `PMO Portfolio Health` | report `pmo_portfolio` | Portafolio | Preservado |
| `PMO Capacity Snapshot` | report `pmo_capacity_snapshot` | Capacity | Preservado |
| `PMO Top Projects by Effort` | report `pmo_top_projects_by_effort` | Portafolio / Reportes | Preservado |

### B3. Number Cards (tipo Custom → `portfolio_kpi`/`resource_kpi`)
| Origen | Métrica backend | Destino provisional (TBD) | Estado |
|---|---|---|---|
| `PMO Active Projects` | `portfolio_kpi(active)` | Portafolio | Preservado |
| `PMO Active Tasks` | task count | Portafolio | Preservado |
| `PMO People Involved` | `resource_kpi(people_involved)` | Capacity | Preservado |
| `PMO Requiring Attention` | `portfolio_kpi(requiring_attention)` | Portafolio | Preservado (crítico) |
| `PMO Overdue Tasks` | `portfolio_kpi(overdue_tasks)` | Portafolio / Project Control | Preservado |
| `PMO Active Clients` | `portfolio_kpi(clients)` | Portafolio | Preservado (crítico) |
| `PMO Projects Without Baseline` | `portfolio_kpi(without_baseline)` | Portafolio / Governance | Preservado (crítico) |

### B4. Custom HTML Blocks (`fixtures/custom_html_block.json`)
| Origen | Endpoint backend | Capacidad | Destino provisional (TBD) | Estado |
|---|---|---|---|---|
| `PMO Attention` | `pmo.dashboard.attention_block()` | proyectos con problemas + tareas atrasadas | Portafolio | Preservado (crítico) |
| `PMO Customers` | `pmo.dashboard.customers_block()` | cartera por cliente | Portafolio | Preservado (crítico) |
| `PMO Governance` | `pmo.dashboard.governance_block()` | conteos + acciones de gobierno | Governance | Preservado (crítico) |

### B5. Quick Lists / Card Breaks de la Home
| Origen | Apunta a | Destino provisional (TBD) | Estado |
|---|---|---|---|
| Quick List "Open change requests" | `PMO Change Request` (Draft/In Review) | Project Control / Governance | Preservado (crítico) |
| Card "PMO Governance" → Baseline / Change Request / Capacity / Import Tags | DocTypes + Page | Governance / Capacity | Preservado |
| Card "Reports" → 9 reportes | reportes | Reportes | Preservado |

## C. Reportes (13) y sus motores
| Reporte | ref_doctype | Motor / fuente | Destino provisional (TBD) | Estado |
|---|---|---|---|---|
| `PMO Portfolio` | Project | `build_status_report` + `_health` | Portafolio | Preservado |
| `PMO Status Report` | Project | `build_status_report` | Project Control | Preservado (crítico) |
| `PMO Planned vs Actual` | Project | Task expected/actual | Project Control | Preservado (crítico) |
| `PMO Baseline Comparison` | PMO Project Baseline | `compare_baselines` | Project Control | Preservado |
| `PMO Change Register` | PMO Change Request | Report Builder | Project Control / Reportes | Preservado (crítico) |
| `PMO Continuous Improvement` | PMO Post-Project Review | ToDo de lessons | Reportes / Governance | Preservado |
| `PMO Project Risk Register` | PMO Project Risk Assessment | `PMO Project Risk` (vivo) | Reportes / Governance | Preservado |
| `PMO Capacity Planning` | PMO Capacity | motor capacity P4 | Capacity | Preservado (crítico) |
| `PMO Capacity Snapshot` | PMO Capacity | agrega capacity_planning | Capacity | Preservado |
| `PMO Resource Capacity` | PMO Capacity | `get_capacity_detail` | Capacity | Preservado |
| `PMO Resource Usage by Project` | PMO Capacity | planned/actual by project | Capacity | Preservado |
| `PMO Top Projects by Effort` | Project | reordena `pmo_portfolio` | Portafolio | Preservado |
| `PMO Work by Resource` | PMO Capacity | tareas activas por recurso | Capacity | Preservado |

## D. Endpoints backend (motores) — no tocar sin decisión
- `dashboard.py`: `portfolio_kpi`, `resource_kpi`, `attention_block`, `customers_block`, `governance_block`, `_build` (secciones: kpis, resources, attention, delayed_tasks, customers, governance).
- `project_control.py`: `get_executive_html`, `get_financial_html`, `build_project_control` (secciones project/executive/schedule/planning/scope_changes/costs/governance/risk).
- `status_date.build_status_report` (chokepoint P4).
- `compare.compare_baselines`.
- `risk_signals.compute_risk_signals` / `get_risk_signals`.
- `governance.governance_flags` / `derive_lifecycle_state` / `build_expediente` / `count_open_change_requests`.
- `capacity_page.get_resources`.
- `health._health` (fuente única de semáforo).
- `project_economics.*` (contrato económico hacia erpnext_proposals; gate económico).
- `tag_import.*`, `overrides.create_duplicate_project`.

Todos **Preservados**.

## E. Fixtures relacionados
- **Custom HTML Block** (3): PMO Attention, PMO Customers, PMO Governance.
- **Number Card** (7, tipo Custom).
- **Dashboard Chart** (3): Portfolio Health, Capacity Snapshot, Top Projects by Effort.
- **Custom Field** (6), **Role** (2), **Custom Role** (3), **Workflow** (1) + **Workflow State** (6).

Todos **Preservados**.

## Cobertura de capacidades críticas exigidas
| Exigido preservar | Cubierto por | Estado |
|---|---|---|
| Atención requerida | Number Card `PMO Requiring Attention` + block `PMO Attention` + `attention_block()` | Preservado |
| Cartera/clientes | Number Card `PMO Active Clients` + block `PMO Customers` + `customers_block()` | Preservado |
| Governance | block `PMO Governance` + `governance_block()` + workspace PMO Governance | Preservado |
| Proyectos sin baseline | Number Card `PMO Projects Without Baseline` + `portfolio_kpi(without_baseline)` | Preservado |
| Solicitudes de cambio | Quick List + `PMO Change Register` + workflow | Preservado |
| Salud actual | `PMO Status Report` + `PMO Portfolio Health` + `_health` | Preservado |
| Capacidad | 4 reportes Capacity + `PMO Capacity Snapshot` + `resource_kpi` | Preservado |
| Esfuerzo | `PMO Planned vs Actual` + `PMO Top Projects by Effort` | Preservado |
| Todos los reportes y motores | 13 reportes + endpoints (sección C/D) | Preservado |

---

## Bitácora de cambios de composición (se llena durante el rescate)
| Fecha | Componente | Origen | Destino | Estado | Decisión / evidencia |
|---|---|---|---|---|---|
| 2026-09-26 | — | — | — | Levantamiento inicial | Inventario base; nada modificado |

### BLOQUE 1 — reconstrucción de PMO Home (rama `feat/pmo-home-rescate`)

**Nuevos componentes de la Home** (native-first):
| Componente | Tipo | Fuente/motor | Nota |
|---|---|---|---|
| PMO Authorized Value | Number Card Custom | `dashboard.economic_kpi(authorized_revenue)` | agregado gateado; None excluido |
| PMO Billed | Number Card Custom | `dashboard.economic_kpi(billed)` | `Project.total_billed_amount` |
| PMO Real Cost | Number Card Custom | `dashboard.economic_kpi(real_cost)` | comparable_cost (labor+externo) |
| PMO Utilization | Number Card Custom | `dashboard.resource_kpi(utilization)` | métrica ya existente, expuesta |
| PMO Economics | Custom HTML Block | `dashboard.economics_block()` | situación económica agregada + traza |
| PMO Customers (ampliado) | Custom HTML Block | `dashboard.customers_block()` | + salud rollup + económicos gateados |

**Componentes ANTIGUOS estacionados** (retirados de la composición de la Home; definiciones/registros/fixtures **intactos**, recuperables):
| Componente | Tipo | Estado | Dónde sigue disponible |
|---|---|---|---|
| PMO Active Tasks | Number Card | Estacionado | registro intacto; sin referencia en Home |
| PMO People Involved | Number Card | Estacionado | registro intacto |
| PMO Active Clients | Number Card | Estacionado | registro intacto (cartera cubre clientes) |
| PMO Projects Without Baseline | Number Card | Estacionado | registro intacto; señal en Governance |
| PMO Capacity Snapshot | Dashboard Chart | Estacionado | Workspace PMO Capacity / registro intacto |
| PMO Top Projects by Effort | Dashboard Chart | Estacionado | registro intacto |
| PMO Attention | Custom HTML Block | Estacionado | fixture intacto; endpoint `attention_block` vivo |
| Quick List "Open change requests" | Quick List (inline) | Retirado de Home | `PMO Change Register` + Governance `open_change_requests` |
| Card Break "PMO Governance" (Baseline / Change Request / Capacity / Import Tags) | Links de Workspace | Estacionado | Workspace **PMO Governance** + **PMO Capacity** (Import Tags → page `tag_import`) |

**Motores/endpoints:** ninguno eliminado. Nuevos: `dashboard._economics`, `_project_native`, `economic_kpi`,
`economics_block` (y `resource_kpi` amplía métrica `utilization`). No se tocó Portfolio, Project Control,
Capacity, Governance, Risk ni los 13 reportes (solo consumo de lectura para la Home).

**Validación (1ª pasada):** suite completa 521 tests OK; validación funcional en `pmo-v16.dev`.
**1ª pasada RECHAZADA en QA visual** (HTML literal, inglés, sin jerarquía, lista de reportes/shortcuts en Home).

### BLOQUE 1 — 2ª pasada de presentación (aprobada; solo presentación, es-MX)

Rediseño de PRESENTACIÓN. **No cambian fuentes, métricas ni semánticas** (endpoints reutilizados tal cual).

**Composición final de la Home** (solo estas 5 secciones, nada más):
| Sección (es-MX) | Componente | Tipo | Motor (sin cambio) |
|---|---|---|---|
| Encabezado | "PMO — Oficina de proyectos" | Workspace header | — |
| Resumen ejecutivo | `PMO Resumen Ejecutivo` (Proyectos activos · Valor autorizado · Facturado · Costo real) | Custom HTML Block | `portfolio_kpi(active)` + `economics_block()` |
| Resumen visual | Salud del portafolio | Dashboard Chart **nativo** `PMO Portfolio Health` | `pmo_portfolio` |
| Resumen visual | `PMO Situación Económica` (Valor autorizado · Facturado · Costo real; **sin margen**) | Custom HTML Block (barras) | `economics_block()` |
| Panorama operativo | `PMO Panorama Operativo` (En riesgo/desviados · Tareas vencidas · Utilización) | Custom HTML Block | `portfolio_kpi` + `resource_kpi(utilization)` |
| Cartera por cliente | `PMO Customers` (Cliente · Proyectos activos · Salud · [Valor autorizado · Facturado gateados]) | Custom HTML Block | `customers_block()` |

**Limpieza de la iteración (deliverable):** ELIMINADOS los 4 Number Cards de la 1ª pasada (`PMO Authorized Value`,
`PMO Billed`, `PMO Real Cost`, `PMO Utilization`) — creados solo en la pasada rechazada; **no requieren estacionarse**.
Bloque `PMO Economics` reemplazado por `PMO Situación Económica`. **Endpoints reutilizables conservados**
(`economic_kpi`, `economics_block`, `_economics`, `_project_native`, `resource_kpi(utilization)`).

**Retirado SOLO de navegación visible (preservado íntegro):**
| Componente | Estado | Preservación |
|---|---|---|
| Lista individual de reportes en Home | Retirado de Home | Reportes intactos (workspaces PMO Control / PMO Capacity) |
| Shortcuts de navegación en Home | Retirado de Home | Navegación en Workspace Sidebar |
| "Gobernanza PMO" en Sidebar | Retirado del sidebar | Workspace `PMO Governance` + capacidades **intactos** |
| Quick List / Number Cards sueltos / card Governance en Home | Retirados de Home | Definiciones/registros intactos |

**Sidebar (es-MX):** `PMO | Portafolio | Control de Proyecto | Planificación de capacidad`. Sin "Reportes"
todavía (se define al final del replanteamiento). Reportes actuales preservados exactamente como están.

**Validación (2ª pasada):** suite completa **519 tests OK**; funcional en `pmo-v16.dev` (18 activos ·
en riesgo/desviados 4 · vencidas 2 · utilización 0% · autorizado 12 700 USD, 8 sin propuesta excluidos ·
gate económico OK · sidebar sin Gobernanza · Workspace Governance preservado).

**Estado: APROBADO por QA visual del usuario.** PMO Home cerrado (visual/funcional).

---

## BLOQUE — Portafolio (mejora puntual; NO rediseño)

Decisión: **conservar** estructura y comportamiento de la Page/report `PMO Portfolio`. Cambios acotados:
- **Columna `Cliente`** en el inventario: `Project.customer` añadido a `_project_row` + columna en el reporte
  y en la tabla de la Page (`pmo_portfolio.py`, `pmo_portfolio.js`).
- **"Proyectos por cliente"** (barras horizontales `Cliente | barra proporcional | N · %`): agrupación
  **client-side** sobre `this.rows` (mismas filas ya filtradas por P4); sin queries/métricas nuevas
  (`_render_customers()` + CSS en `pmo_portfolio.js`). Sin dimensión económica.
- Sin cambios en indicadores superiores, "Requiere atención", excepciones, navegación (clic → Project Control).
- i18n: `Customer→Cliente`, `Projects by customer→Proyectos por cliente`, `No customer→Sin cliente` (es.po).

**Estado: APROBADO por QA visual.**

---

## BLOQUE — Project Control > Resumen (rediseño de presentación)

Objetivo: superficie de **consulta/control/drill-down** compacta. Decisiones:
- **Template/endpoint dedicados**: nuevo `pmo/templates/project_control/resumen.html` + `get_summary_html`.
  **`executive.html`/`get_executive_html` intactos** (Print Format). La pestaña "Resumen" (Page) los repunta.
- **Solo presentación**: reutiliza motores canónicos (`build_status_report`, `pmo.health`, `compute_risk_signals`,
  `build_expediente`, `governance_flags`); **sin** métricas/persistencia/lógica nueva. Único añadido de payload:
  `Project.expected_start_date` (fecha de inicio) en `_project_section`.
- **4 bloques**: (1) Cabecera de control (Proyecto/Cliente/Estado/Salud/Inicio/Compromiso/Fin pronosticado/Desvío);
  (2) Avance hero (Progreso+barra/Horas plan/Horas reales/Tareas vencidas); (3) Excepciones — 3 paneles de control
  (Cronograma/Riesgos/Solicitudes de cambio); (4) Gobernanza — franja compacta (Acta de transferencia/Línea base/
  Cierre/Revisión).
- **Semántica real respetada**: **Acta de transferencia** (no "Charter"); Riesgos = señales de `compute_risk_signals`
  (Abiertos/Alta exposición/Sin responsable/Sin tratamiento; **sin** agregado artificial de "requieren atención");
  Cambios = **Solicitudes totales/abiertas** (`build_expediente`, `OPEN_CHANGE_REQUEST_STATES`).
- **Fuera del Resumen**: economía (Financiera), Gantt, tablas completas de tareas/riesgos/CR, comparación de
  baselines. **No existen** ruta crítica ni bitácora de salud → no se representan.
- **Drill-down** solo a rutas/artefactos existentes (Forms de gobernanza; pestañas Estado/Cronograma y Control
  de cambios; acciones de riesgo). Estrictamente **lectura**; ninguna escritura en la cadena.
- 2ª pasada visual: jerarquía tipo "control center" (cabecera dominante, avance hero, paneles, gobernanza
  secundaria) — solo `resumen.html` + CSS.

**Auditoría final de fuentes (solo lectura): sin problemas materiales.** Sin datos hardcodeados; sin lógica
duplicada; estados `— / Sin evaluar / Pendiente / No requerido` diferenciados (no ocultan errores; `get_summary_html`
sin try/except → los fallos propagan); P4 intacta (`build_status_report` chokepoint); sin economía (gate no invocado).

**PHI (health log / bitácora de salud): FUERA de este bloque** — se revisará en su diseño pendiente.

**Estado: APROBADO — cierre visual, funcional y técnico del Resumen.** No más cambios en esta pestaña.

---

## Estado global del rescate (a la fecha)
| Bloque | Estado |
|---|---|
| PMO Home | APROBADO (cerrado) |
| Portafolio (mejora puntual) | APROBADO |
| Project Control > Resumen | APROBADO (cierre visual/funcional/técnico) |
| Otras pestañas de Project Control (Estado/Cronograma, Planificado vs Real, Comparación baseline, Control de cambios, Financiera) | **Intactas** — no tocadas |
| Trabajo git | **Sin commit/push** (rama `feat/pmo-home-rescate`) |
