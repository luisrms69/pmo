# Native-first UI policy (PMO)

Regla técnica para la interfaz de PMO en el Desk de Frappe/ERPNext.

## Principio

**Frappe nativo por defecto → extensión PMO donde haga falta → custom solo como excepción justificada.**

El producto debe sentirse como **ERPNext/Frappe extendido por PMO**, no como una app web distinta
incrustada. Por defecto se usan componentes nativos del Workspace:

- Number Cards (incl. `type=Custom` con `method=` server-side P4 para métricas derivadas),
- Dashboard Charts **solo `Report-type`** (ver Seguridad),
- Quick Lists, Shortcuts, Cards, Sidebar, layout de Workspace.

## Cuándo se permite un componente custom

Un **Custom HTML Block** (u otra pieza propia) solo se justifica ante una **limitación funcional
demostrable**: la información es **derivada** por un motor PMO y **ningún componente nativo** puede
presentarla adecuadamente (p. ej. tabla multi-columna con `health`/`slip`/`motivo` y navegación a una
Page). Cada excepción debe documentarse con:

- qué necesidad resuelve;
- por qué el nativo no alcanza;
- fuente server-side (motor/consulta) y cómo impone **P4** por usuario;
- riesgo de compatibilidad futura.

## Excepciones vigentes

| Custom Block | Necesidad | Por qué no nativo | Fuente / P4 |
|---|---|---|---|
| `PMO Attention` | Proyectos que requieren atención + tareas más atrasadas | Quick List solo muestra título+fecha+estado; no `health`/`slip`/`delay`/`motivo` ni columnas | `pmo.dashboard.attention_block` → `pmo_portfolio.execute` (READ por proyecto) + `get_list("Task")` (pqc); caché por-usuario |
| `PMO Customers` | Cartera por cliente (agregación group-by con at-risk/plan-real) | Ningún widget nativo agrupa por cliente con esas señales | `pmo.dashboard.customers_block` → deriva del portafolio (P4); caché por-usuario |

## Seguridad (obligatorio)

- **Prohibido** `frappe.get_all` para datos sujetos a P4, `ignore_permissions`, y **cachés globales**
  para información dependiente del usuario.
- Los **Dashboard Charts `Count/Sum/Average/Group By/Heatmap`** usan `dashboard_chart.get` con
  `@cache_source` de **clave global** (`chart-data:{name}`) → **fuga de agregados entre usuarios**;
  **no usarlos** para datos P4. Solo se permiten **`Report-type`** (usan `query_report.run`, sin
  `cache_source`) alimentados por un Script Report P4-safe.
- Todo agregador nuevo es server-side, respeta pqc/motores PMO y, si cachea, lo hace **por usuario**.

## Regresión en upgrades

Cada excepción custom es un **punto explícito de regresión** durante upgrades de Frappe (shadow DOM,
`create_shadow_element`, clases de widget). **Si una versión futura de Frappe incorpora una capacidad
equivalente** (p. ej. un widget de tabla-lista con columnas derivadas), **evaluar retirar el custom**
y volver a nativo.
