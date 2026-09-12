# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Top Projects by Effort — reporte MINIMO de presentacion (no motor nuevo).

Reordena el resultado de `pmo_portfolio.execute` por horas planificadas y toma el top-5, devolviendo
un chart de barras (Project vs Planned Hours) para el Dashboard Chart Report-type del Workspace PMO.
P4: opera sobre el output de PMO Portfolio, que ya impone READ por proyecto. Sin logica analitica nueva.
Nota: frappe-charts no soporta barras horizontales nativas; se usa barra vertical."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	from pmo.pmo.report.pmo_portfolio.pmo_portfolio import execute as pf_execute

	_cols, rows, _msg, _chart, _summary = pf_execute(frappe._dict(filters or {}))
	top = sorted(rows or [], key=lambda r: flt(r.get("planned_hours")), reverse=True)[:5]

	chart = {
		"data": {
			"labels": [r.get("project_name") or r.get("project") for r in top],
			"datasets": [{"values": [round(flt(r.get("planned_hours")), 1) for r in top]}],
		},
		"type": "bar",
		"colors": ["#449CF0"],
	}
	columns = [
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 220,
		},
		{"label": _("Planned hours"), "fieldname": "planned_hours", "fieldtype": "Float", "width": 140},
	]
	data = [{"project": r.get("project"), "planned_hours": r.get("planned_hours")} for r in top]
	return columns, data, None, chart, None
