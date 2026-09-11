# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO dashboard — agregador de presentación para los Number Cards del Workspace PMO.

NO es un motor ni una métrica nueva: reutiliza íntegramente `pmo_portfolio.execute` (que ya impone
P4 vía `build_status_report` / `pmo.permissions`) y expone los MISMOS conteos que su `_summary`
(Projects / Deviated / At risk / Without baseline) más sumas de columnas que el reporte ya calcula
(overdue, forecast > commitment). Cada Number Card `Custom` llama a `portfolio_kpi` pasando el
`metric` en su `filters_json`. Se cachea el cómputo por (usuario, filtros) unos segundos para no
recomputar el portafolio una vez por card en la misma carga del dashboard.
"""

import frappe
from frappe.utils import flt

# Métricas expuestas → todas derivadas del resultado de pmo_portfolio.execute (mismas señales).
_METRICS = (
	"projects",
	"deviated",
	"at_risk",
	"without_baseline",
	"overdue_tasks",
	"forecast_exceeds",
)


@frappe.whitelist()
def portfolio_kpi(filters=None):
	"""Devuelve {"value": N} para el `metric` indicado en filters. P4 lo impone pmo_portfolio.execute.

	`filters` llega desde el Number Card `Custom` (filters_json). Claves soportadas:
	  - metric: una de _METRICS (obligatoria)
	  - company / include_completed: se pasan al portafolio (opcionales)
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	metric = filters.get("metric")
	if metric not in _METRICS:
		frappe.throw(frappe._("Unknown PMO KPI metric: {0}").format(metric))
	kpis = _portfolio_kpis(
		company=filters.get("company"),
		include_completed=filters.get("include_completed"),
	)
	return {"value": kpis.get(metric)}


def _portfolio_kpis(company=None, include_completed=None):
	"""Ejecuta el portafolio UNA vez (P4-safe) y agrega los conteos. Cache corto por usuario+filtros."""
	cache = frappe.cache()
	key = f"pmo:portfolio_kpis:{frappe.session.user}:{company or ''}:{1 if include_completed else 0}"
	cached = cache.get_value(key)
	if cached is not None:
		return frappe.parse_json(cached)

	from pmo.pmo.report.pmo_portfolio.pmo_portfolio import (
		HEALTH_AT_RISK,
		HEALTH_OFF_TRACK,
		execute,
	)

	exec_filters = {}
	if company:
		exec_filters["company"] = company
	if include_completed:
		exec_filters["include_completed"] = 1

	_columns, data, _msg, _chart, _summary = execute(exec_filters)

	kpis = {
		"projects": len(data),
		"deviated": sum(1 for r in data if r.get("health_key") == HEALTH_OFF_TRACK),
		"at_risk": sum(1 for r in data if r.get("health_key") == HEALTH_AT_RISK),
		"without_baseline": sum(1 for r in data if not r.get("has_baseline")),
		"overdue_tasks": sum(int(r.get("overdue") or 0) for r in data),
		"forecast_exceeds": sum(int(r.get("forecast_exceeds") or 0) for r in data),
		"planned_hours": flt(sum(flt(r.get("planned_hours")) for r in data), 1),
		"actual_hours": flt(sum(flt(r.get("actual_hours")) for r in data), 1),
	}
	cache.set_value(key, frappe.as_json(kpis), expires_in_sec=90)
	return kpis
