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

## BLOQUE — Project Control > Estado / Cronograma (nueva pestaña)

Responsabilidad: **¿cumplimos el cronograma y dónde se separa el plan vigente de la línea base?** Solo
lectura/drill-down. Template/endpoint dedicados (`estado.html` + `get_schedule_html`); `executive.html`
intacto (Print Format). Reutiliza `build_status_report`, `get_effective_baseline` (baseline **efectiva al
corte**), `build_snapshot`, `compare_snapshots`, `_annotate/_relevant`; **sin segundo motor**.
- 4 bloques: Estado del cronograma · Gantt **línea base vs plan vigente** (barras + progreso + línea de
  corte + hitos) · Estado de ejecución (Completadas/En curso/Pendientes/Vencidas) · Excepciones.
- **Semántica final de desviaciones (2.1):** cada excepción indica su **referencia** — `+N d vs línea base`
  (slip) o `+N d vs compromiso` (`current_exp_end − pmo_deadline` para «Excede compromiso»). Se eliminó el
  «0 d» ambiguo.
- **Añadida vs Retirada (2.2):** diferenciadas por **identidad de Task (ID estable)**, nunca por subject/
  posición: **«Fuera de línea base»** (en plan vigente, no en baseline) vs **«Retirada del plan»** (en
  baseline, no en plan vigente) — leyenda, Gantt y excepciones. Detección fiable vía `compare_snapshots`.
- **Fin plan vigente** ≠ pronóstico calculado (no hay forecast predictivo): es el plan vivo (`exp_end_date`).
- Fuera de esta pestaña: horas/esfuerzo (→ Planificado vs Real, sin tocar), economía, riesgos, CR,
  gobernanza. No hay ruta crítica ni bitácora de salud (no existen).

## BLOQUE — Operación de Línea Base desde Project (native-first)

El PM opera la baseline desde el **form nativo de Project** (menú «PMO»), sin abrir el DocType.
- Endpoints (reutilizan el controlador `PMO Project Baseline`: snapshot + submit): `get_baseline_state`,
  `establish_baseline` (Original), `new_baseline` (Replan / Approved Change). Inmutable; sin overwrite;
  conserva la cadena; sin rebaseline parcial.
- Estado compacto en Project: «Sin línea base» o «Línea base: {revisión} · {fecha}».
- **Autoridad de Replan (gap corregido):** un PM normal (owner) **no** puede rebaselinar libremente. El
  tipo **Replan** (excepción PMO sin CR) exige rol **PMO Manager** (guard server-side en el controlador,
  aplica a endpoint y a creación manual del DocType). **Approved Change** (owner + CR **Implemented**) y
  **Original** siguen gobernados por el owner. Sin ampliar Change Control ni inventar estados de CR.
- **Gap pendiente reportado:** el write/submit de baseline sigue **owner-bound** (`has_permission_baseline`);
  un PMO Manager que **no** es owner del Project no puede escribir baselines. Si el PMO debe replanear
  proyectos ajenos, requeriría extender `has_permission_baseline`/permisos del DocType — **no** hecho en
  este bloque (cambio de modelo de permisos).

## BLOQUE — Correcciones QA (Baseline UX + Desviaciones del cronograma)

Correcciones puntuales tras QA; **sin rediseño** (el menú PMO no se rediseña en este bloque).

**1. Baseline UX (form nativo de Project):**
- **Estado visible (causa + fix).** El estado se intentaba pintar con `frm.dashboard.add_indicator`,
  pero el dashboard del Project se **vacía** en cada `dashboard.refresh()` (`reset()`), por lo que un
  indicador añadido de forma asíncrona (tras el `xcall`) desaparecía en re-renders. Se cambió a
  **`frm.set_intro`** (banner nativo del form que **persiste** a través de esos refrescos): naranja
  «Sin línea base» / azul «Línea base: {revisión} · {fecha}». No es una superficie nueva: es el
  mecanismo nativo correcto para estado a nivel form.
- **Motivo OBLIGATORIO.** Ahora obligatorio para **toda** baseline (incl. Original): `reqd:1` en el
  diálogo, `reqd:1` en el DocType, y **enforcement server-side** — `establish_baseline` rechaza la
  primera baseline sin motivo (`ValidationError` antes de crear) y `_validate_reason` exige motivo en
  todos los tipos. Semántica de Replan/Approved Change intacta (ya lo exigían).
- **Historial condicionado.** `get_baseline_state` expone `baseline_count`; el botón «Historial de
  líneas base» solo aparece si `baseline_count > 0`. No se elimina ni modifica el historial.

**2. Project Control > Estado / Cronograma — bloque «Desviaciones del cronograma»:**
- **Renombrado** «Excepciones del cronograma» → **«Desviaciones del cronograma»**. Responde solo
  **¿dónde está desviado el cronograma?**.
- **Filtro desviación-only.** Aparecen únicamente desviaciones temporales reales: **Vencida** al corte,
  **Excede compromiso** (vs fecha comprometida) y **diferencia material vs línea base** (`slip≠0`).
  **NO** aparecen por su sola clasificación: hito sin desviación, «Fuera de línea base» solo por ser
  nueva, ni «Retirada del plan» solo por retirarse (viven en el **Gantt**). Una añadida entra solo si
  **excede el compromiso**, etiquetada por ESA razón. No se toca `_relevant` (lo usa la vista Resumen /
  Print Format): el filtro vive en `_schedule_deviations`.
- **Detección intacta.** El Gantt sigue diferenciando añadidas/retiradas/hitos (leyenda + barras).
- **Validado en PROJ-0008 (corte 2026-09-11, baseline R1-replan):** DESVIACIONES = exactamente
  `Despliegue — Excede compromiso (+42 d vs compromiso)` y `Pruebas — Vencida`. Desaparecen el hito
  «Entrega a cliente» (0 d) y «Soporte extra» (fuera de LB); el Gantt conserva `added=1`.

## Estado global del rescate (a la fecha)
| Bloque | Estado |
|---|---|
| PMO Home | APROBADO (cerrado) |
| Portafolio (mejora puntual) | APROBADO |
| Project Control > Resumen | APROBADO (cierre visual/funcional/técnico) |
| Project Control > Estado / Cronograma | Implementado + semántica (2.1 · 2.2) + **QA: rename «Desviaciones» y filtro desviación-only** — validado en PROJ-0008 |
| Operación de Línea Base desde Project | Implementado + guard Replan PMO + **QA: estado visible (set_intro), motivo obligatorio server-side, historial condicionado** — validado en 8412 |
| Otras pestañas de Project Control (Planificado vs Real, Comparación baseline, Control de cambios, Financiera) | **Intactas** — no tocadas |
| Governance PMO (Gobernanza V1) | **Implementado** — modelo Project + contrato de desviaciones + exclusión gobernada + tablero + reporte + UX Project; 562 tests OK. Ver bloque abajo |
| Menú PMO (rediseño) | **Pendiente** — no rediseñado; Gobernanza V1 añadió solo acciones condicionales |
| Trabajo git | **Sin commit/push** (rama `feat/pmo-home-rescate`) |

## BLOQUE — Gobernanza V1 (contrato + tablero + exclusión)

Gobernanza ligera native-first: `Project → Acta/Handoff → Baseline → Ejecución+Riesgos → Cambios/rebaseline →
Cierre → Revisión`. Sin DocType/policy/scheduler/SLA/stage-gates nuevos. La antigua Governance (Workspace,
`governance.py.governance_flags`, expediente en Resumen, bloque previo) **se conserva**; el nuevo motor la
complementa como fuente del tablero.

- **Modelo en Project (Custom Fields, fixtures):** `pmo_project_manager` (Link User — ERPNext v16 no trae PM
  nativo); exclusión gobernada `pmo_governance_exempt` + `pmo_exempt_reason`/`_by`/`_on`. Enforcement
  server-side en `pmo.governance_project.guard_governance_exemption` (Project `validate`): el PM **no** puede
  autoexcluir (exige PMO Manager/System Manager), motivo obligatorio, auditoría sellada server-side; al
  re-incluir se limpia y Version conserva el histórico.
- **`is_project_started(project)`** (fuente única, `pmo.governance`): terminal ∨ `actual_start_date` ∨
  `percent_complete>0`. Determinista, sin fases.
- **Motor único read-only `pmo.governance_inbox`:** `_evaluate(project)` → estado por control
  (completo/pendiente/no_aplica) del que se derivan **bandeja** (`compute_deviations`/`governance_board`) y
  **resumen de cumplimiento** (misma regla). `get_project_governance` para el form. Reutiliza
  `governance_flags`-adyacentes, `risk_signals`, workflow del CR, `get_effective_baseline`. Exentos fuera de
  numerador/denominador.
- **Riesgos:** desviación **solo** por deficiencia de gestión (`no_owner`/`no_response`), y **solo tras la
  primera baseline**. Riesgo alto bien gestionado NO es desviación.
- **Cambios:** In Review → PMO; Draft/Approved/Implemented(sin `baseline_after`) → PM. Implemented con
  `baseline_after` = rebaseline hecho ⇒ sin desviación.
- **Responsable siguiente acción (convención semántica; el workflow del CR no separa por rol):** PMO = CR In
  Review + Revisión posterior; PM = el resto.
- **Tablero:** Custom Block "PMO Governance" reconstruido (KPIs Requiere PMO/PM/Excluidos + bandeja + resumen
  + link al reporte). "Revisar" → contexto (form del CR / Project Control / new del artefacto); **no** aprueba
  inline. es-MX.
- **Reporte:** Script Report `PMO Projects Without Governance` (activos excluidos: Proyecto·PM·Motivo·
  Autorizado por·Fecha). P4 vía `get_list`.
- **UX Project:** `pmo_governance_menu` añade **solo cuando aplica** «Acta de inicio» (crea Handoff) y
  «Gobernanza (n)» (resumen). Sin reorganizar baseline/riesgo/control.

**Correcciones post-revisión (4 puntos del usuario):**
1. **Riesgos:** con la primera baseline, la evaluación de riesgos es obligatoria → **baseline sin ningún
   Risk Assessment = desviación** («Proyecto con línea base sin evaluación de riesgos», PM), además de los
   riesgos activos con carencia (sin responsable/respuesta). Reutiliza `risk_signals.assessment_exists`.
2. **Revisión posterior = PMO (resuelto):** se añadió el rol **PMO Manager** a los permisos del DocType
   `PMO Post-Project Review` **y** `has_permission_review` ahora permite WRITE/CREATE/SUBMIT/CANCEL a la
   autoridad PMO (`_has_pmo_authority`) en cualquier proyecto, manteniendo P4 de **lectura**. El owner del
   Project conserva su capacidad previa.
3. **Rebaseline solo si afecta el compromiso:** un CR `Implemented` exige nueva baseline **solo** si declara
   `impacts_scope`/`impacts_schedule`/`impacts_effort` (el plan congelado del snapshot ADR-0004). Un cambio
   solo comercial/riesgo **no** exige rebaseline. Reutiliza flags de impacto existentes del CR.
4. **PM canónico:** `pmo_project_manager` es la única fuente de PM en motor/tablero/reporte; **ningún**
   código de gobernanza usa `owner` como sustituto (owner/membresía solo gobierna P4 de visibilidad,
   ADR-0002). No se migran proyectos históricos.

**Gaps de fecha deliberados:** antigüedad de CR *In Review* usa `request_date` (edad del cambio, no de la
entrada a revisión); Cierre de proyecto *Cancelled* puede no tener fecha de terminal (`actual_end_date`
vacío) → antigüedad "—"; carencia de Riesgo sin fecha canónica → "—".

**Definición APROBADA de «proyecto iniciado» (DEFINITIVA):** `is_project_started(project) := Project.status
in {"Open", "On hold"}` (valor nativo ERPNext «On hold», h minúscula; constante `STARTED_STATUSES`). Punto.
NO depende de `actual_start_date`, `percent_complete`, Baseline ni Handoff (el Handoff es un control, no
puede decidir su propia exigibilidad). Reemplaza la inferencia previa (fechas/%) introducida sin fundamento.
`On hold` = proyecto ya iniciado y **pausado**; la pausa NO exime de obligaciones → sigue sujeto a Acta/Línea
base. Consecuencia en `_evaluate` (único cambio en el motor, sin tocar los otros 4 controles): `Open`/`On
hold` sin Handoff → **Acta pendiente (PM)**; sin baseline → **Línea base pendiente (PM)** (independientes).
`Completed`/`Cancelled` (terminales) no son «iniciados» → Acta/Baseline `not_applicable` (se gobiernan por
Cierre/Revisión). `not_applicable` sigue en el motor pero **no** se muestra en tarjetas. Indicadores 8412:
Acta 11/19/1, Línea base 24/6/1 (sin proyectos On hold actualmente → sin cambio respecto al paso anterior).

**PENDIENTE (registrado, NO implementado):** *Reporte / señal de Proyectos On Hold* → destinado a **Portafolio
PMO** (no a Gobernanza). Debe permitir revisar proyectos pausados y **cuánto tiempo** llevan en ese estado.

**Presentación V2 del dashboard (según `gobernanzapmo.png`):** el tablero pasó a: encabezado *Gobernanza PMO* +
**ciclo de 6 etapas** (Acta→Baseline→Riesgos→Cambios→Cierre→Revisión, cada una con descripción breve +
Completos/Pendientes/No aplica) + **KPIs** (Requiere PMO rojo · Requiere PM azul · Excluidos gris) + bandeja
**Requieren atención (N)** completa + tabla **Proyectos no sujetos a gobernanza (N)** en la misma página. Se
retiró la *tabla de cumplimiento por control* (dato interno preservado en el payload) y el *shell legacy* del
workspace (documentos/expediente/riesgo/mejora continua) — capacidades intactas, solo fuera de esta composición.
Números 100 % del motor (`governance_board.stages` = agregación pura de `_evaluate`: `completo+pendiente+no_aplica
= gobernados`, nunca `total−completos`). **Gobernanza PMO** volvió al **sidebar PMO** (2º ítem). Botón PMO en
Project: añadidos accesos faltantes (Cierre y Revisión contextuales por lifecycle; *Solicitudes de cambio*
persistente). 572 tests OK.

**Tests (`test_governance_contract`, 20):** iniciado; sin/ con Acta; baseline; riesgo (n/a antes de baseline,
bien vs mal gestionado); CR PM/PMO/rebaseline; cierre; revisión; gobernanza limpia; exento; PM no autoexcluye;
PMO sí; motivo obligatorio; resumen==bandeja. Suite completa **562 OK**.

## BLOQUE — Panel PMO del Project (consola única en pmo_project_control)

La Page existente `pmo_project_control` evoluciona a **Panel PMO** del Project (una sola superficie; sin
Dialog/Page/DocType nuevos). Separación conceptual mantenida: **Gobernanza transversal/portafolio**
(`governance_inbox.governance_board`, dashboard `/desk/pmo-governance` — INTACTO) vs **estado PMO contextual
de UN Project** (nuevo).

- **Contrato contextual** `pmo.project_control.project_governance_state(project)` (backend natural de la Page):
  reutiliza por import el motor único `_evaluate`/`_facts`; expone por control label/description/state/
  situation/action_owner + doc existente + conteos (Riesgos/Cambios) + `na_reason` (microcopy) + `can_create`
  (gates reales `has_permission_*`). NO duplica reglas ni toca `governance_board`.
- **Pestaña Gobernanza** (primera/landing) en la Page: ciclo de 6 etapas compacto (número, icono/color por
  etapa, descripción, estado, responsable PM/PMO, microcopy + siguiente paso) con acciones contextuales que
  nacen **siempre vinculadas al Project actual**: Acta (crear/abrir), Línea base (establecer/nueva/historial,
  reusando los endpoints reales), Riesgos (evaluar/gestionar), Cambios (ver/nueva), Cierre y Revisión (crear/
  abrir según lifecycle). Habilitación por `can_create`; el backend sigue siendo la autoridad. Las pestañas de
  control existentes (Resumen/Estado/PvA/Baseline/Cambios/Financiera) **intactas**.
- **Botón PMO del Project** simplificado a un **acceso único "Panel PMO · N"** (N = desviaciones del mismo
  motor; señal discreta, sin mini-dashboard). Se retiró el dropdown saturado; cada capacidad quedó verificada
  como accesible desde el Panel antes de eliminar redundancias.
- **Higiene Git:** el trabajo previo (Estado/Cronograma, Baseline, Gobernanza V1 motor + dashboard) se cortó
  en commits locales coherentes ANTES del Panel; el Panel se implementó en commits propios. Sin push.
