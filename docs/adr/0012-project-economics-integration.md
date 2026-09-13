# ADR-0012: Economía de Project Control — contrato de `erpnext_proposals`, sin recálculo

**App:** pmo · **Rama protegida:** version-16 · **Estado:** Proposed · **Ciclo:** sección económica del Reporte Ejecutivo (sobre ADR-0011)

## Contexto

ADR-0011 fijó el contexto canónico de Project Control y dejó explícitamente **pendiente** la definición
del agregador de **costos** ("se define al abordar la sección"; D2 y "Fuera de alcance"). Esta sección la
define ahora, para **añadir información económica** (costos/margen) al Reporte Ejecutivo **existente** sin
rediseñarlo.

La valuación económica autoritativa de un proyecto **ya existe** fuera de pmo: la Quotation ganada
(congelada) de `erpnext_proposals`, que expone el contrato canónico
`get_project_authorized_economics(project)` (v0.23.0). ERPNext, por su parte, mantiene los **reales**
nativos del Project (`total_sales_amount`, `total_billed_amount`, `total_costing_amount`,
`total_purchase_cost`, `total_consumed_material_cost`, `gross_margin`, `per_gross_margin`), todos en
moneda base de la Company.

## Problema

Si pmo recalcula economía (horas×tarifa, costo externo, márgenes, addendas, FX), en pocos meses habrá una
**segunda fórmula económica** divergente de la de `erpnext_proposals` y de los reales de ERPNext → números
distintos para el mismo proyecto, doble mantenimiento y riesgo fiscal/comercial. Además, la economía es
**sensible**: no puede exponerse a cualquiera con acceso operativo al proyecto, ni filtrarse a superficies
no controladas (PDF, Portal, DocShare).

## Decisiones

### D1 — SSOT económico = contrato de `erpnext_proposals` (pmo compone, no recalcula)
La fuente de verdad del **autorizado** es la Quotation congelada, consumida **solo** vía
`get_project_authorized_economics(project)`. pmo **no** reimplementa `horas×tarifa`, costo externo,
márgenes, addendas ni FX; **no** usa `impact_amount` del Change Request (estimación no vinculante) ni
`Project.estimated_costing` como fuente (es un espejo que sincroniza `erpnext_proposals`). Cierra ADR-0011
D2 fila "Costos".

### D2 — Frontera opcional y acoplamiento perezoso
`pmo/project_economics.py` es la **única** frontera hacia `erpnext_proposals`. El import es **lazy**;
`required_apps` sigue siendo `["erpnext"]` (erpnext_proposals es opcional). La sección `costs` **no** está
en `DEFAULT_SECTIONS`: se compone solo cuando se pide y el gate lo permite.

### D3 — Tres estados diferenciados; nunca degradar inconsistencia a ausencia
`get_authorized_economics` distingue: `app_absent` (erpnext_proposals no instalada) · `no_proposal`
(ninguna Quotation con `proposal_project==project`, en **cualquier** estado) · `inconsistent` (hay
propuesta vinculada pero el contrato falla → mensaje **estable y traducible**, detalle técnico solo en
`frappe.logger("pmo")`, **nunca** `frappe.log_error` para no ensuciar el suite) · **ok**. Prohibido
capturar excepciones genéricas para convertir `inconsistent` en ausencia.

### D4 — Gate económico único, server-side, previo a componer
`can_see_project_economics(project)` = rol económico ∈ {PMO Manager, PMO Executive Access, System Manager}
**AND** `has_permission("Project","read")`. Se evalúa **antes** de componer `costs`; si no pasa, la sección
**no existe** en el payload (no llega a template, JS ni PDF). No basta READ ni DocShare; Task/Portal no
reciben economía. Es una **sola** decisión server-side (no en JS/template/Print Format).

### D5 — Costo comparable vs base del margen bruto (no contaminar la comparación)
El costo registrado se expone en dos magnitudes distintas:
- **`comparable_cost` = `total_costing_amount` + `total_purchase_cost`** — comparable contra el costo
  autorizado del contrato.
- **`gross_margin_cost_basis` = comparable_cost + `total_consumed_material_cost`** — base del `gross_margin`
  nativo de ERPNext.

El **material consumido** se muestra aparte; **no** entra en la comparación con el autorizado. El
`gross_margin`/`per_gross_margin` nativo se muestra **tal cual** (sin renombrar ni recalcular); el margen
autorizado y el bruto registrado van **lado a lado**, sin interpretarse como "desviación" durante la
ejecución.

### D6 — Economía solo en Page; excluida de PDF/Print Format (decisión estructural)
El resumen económico aparece en la Page (Reporte Ejecutivo, bloque compacto) y en la **pestaña Financiera**
(`financial.html`, endpoint `get_financial_html`, mismo builder + gate). El **Print Format/PDF** usa
`DEFAULT_SECTIONS` y **no** incluye economía en v1. No depende de "acordarse de ocultarla": la sección
`costs` no se compone para esa superficie.

### D7 — Moneda v1: fail-closed
El autorizado viene en moneda de la Quotation y los nativos en moneda base de la Company. v1 compara
**solo** con base única; ante moneda incompatible, el contrato es **fail-closed** (no se inventa FX).

## Fuera de alcance (de este ADR)
- EAC/ETC/forecast económico, cash flow, EVM, economía por Task, Portfolio/Dashboard financiero.
- Conversión de divisas (FX) y multi-moneda real.
- Economía en Portal, Print Format/PDF (excluida por D6).
- Cualquier cambio a `erpnext_proposals` o a su contrato.

## Consecuencias
- Un solo lugar de acoplamiento (`project_economics.py`); Page y Financiera muestran lo mismo; el PDF nunca
  filtra economía.
- La economía autorizada evoluciona en `erpnext_proposals`; pmo la **consume** y se mantiene alineado sin
  fórmulas paralelas.
- El gate concentra la decisión de acceso en un punto auditable; ampliar/restringir roles es un cambio local.
- Si `erpnext_proposals` no está o falla, pmo sigue mostrando los reales nativos con un estado claro, sin
  romper el Reporte Ejecutivo.

## Alternativas descartadas
- **Recalcular economía en pmo** → segunda fórmula divergente del contrato y de los reales; se rechaza (D1).
- **Gate en template/JS o basado solo en READ/DocShare** → filtra economía sensible; se rechaza (D4).
- **Degradar `inconsistent` a "sin propuesta"** → oculta datos rotos como si no existieran; se rechaza (D3).
- **Incluir material en el costo comparable** → contamina la comparación con el autorizado; se rechaza (D5).
- **Mostrar economía en el PDF** → superficie no controlada; se rechaza en v1 (D6).

## Criterios de aceptación
- La sección `costs` se compone **solo** vía `build_project_control` con gate previo, fuera de
  `DEFAULT_SECTIONS`, y consume el contrato; no hay segunda fórmula económica en pmo.
- `get_authorized_economics` devuelve los 3 estados + ok, sin degradar `inconsistent` a ausencia y sin
  `frappe.log_error`.
- El gate exige rol económico **AND** READ; sin él, `pc.costs` no existe en el payload (verificado en tests
  de seguridad).
- `comparable_cost` y `gross_margin_cost_basis` están separados; el material no entra en el comparable.
- El Print Format/PDF no incluye economía; Page y Financiera sí, tras el gate.
- Validado end-to-end con una cadena real (root + addenda aplicada + addenda pendiente), no solo mocks.
