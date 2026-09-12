# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Capacity Snapshot — reporte MINIMO de presentacion (no motor nuevo).

Agrega el resultado de `pmo_capacity_planning.execute` del PERIODO ACTUAL (mes) en 5 totales
(Capacity/Available/Planned/Actual/Free) y devuelve un chart de barras para el Dashboard Chart
Report-type del Workspace PMO. P4: la agregacion opera sobre el output del reporte de capacidad,
que ya impone permisos y enmascarado. No introduce logica analitica nueva."""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = filters.get("from_date") or get_first_day(today()).isoformat()
	to_date = filters.get("to_date") or get_last_day(today()).isoformat()

	from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import execute as cap_execute

	_cols, data, _msg, _chart, _summary = cap_execute(
		{"from_date": from_date, "to_date": to_date, "granularity": "Month"}
	)

	agg = {"capacity": 0.0, "availability": 0.0, "planned_total": 0.0, "actual_total": 0.0, "free": 0.0}
	for r in data or []:
		for k in agg:
			agg[k] += flt(r.get(k))

	values = [round(agg[k], 1) for k in ("capacity", "availability", "planned_total", "actual_total", "free")]
	labels = [_("Capacity"), _("Available"), _("Planned"), _("Actual"), _("Free")]
	chart = {
		"data": {"labels": labels, "datasets": [{"values": values}]},
		"type": "bar",
		"colors": ["#8a93ad", "#449CF0", "#F8814F", "#2ECC71", "#7574C9"],
	}
	columns = [
		{"label": _("Metric"), "fieldname": "metric", "fieldtype": "Data", "width": 160},
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "width": 120},
	]
	rows = [{"metric": lbl, "hours": val} for lbl, val in zip(labels, values, strict=False)]
	return columns, rows, None, chart, None
