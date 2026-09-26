# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Risk Register (ADR-0016 R1, modelo corregido) — vista del registro VIVO de riesgos.

Lee `PMO Project Risk` (el estado vigente de cada riesgo), NO los items del Assessment. Es la superficie de
seguimiento durante la ejecución.

P4: se resuelve vía `frappe.get_list` sobre `PMO Project Risk`, que aplica
`get_permission_query_conditions_risk` (visibilidad heredada del Project). Administrator/Executive son global
readers. `ignore_permissions=False` fail-closed.
"""

import frappe
from frappe import _
from frappe.utils import strip_html

RISK_DT = "PMO Project Risk"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 150,
		},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 140},
		{"label": _("Risk"), "fieldname": "risk", "fieldtype": "Data", "width": 300},
		{"label": _("Probability"), "fieldname": "probability", "fieldtype": "Data", "width": 90},
		{"label": _("Impact"), "fieldname": "impact", "fieldtype": "Data", "width": 80},
		{"label": _("Exposure"), "fieldname": "exposure", "fieldtype": "Data", "width": 90},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{
			"label": _("Risk owner"),
			"fieldname": "owner",
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{
			"label": _("May affect controlled condition"),
			"fieldname": "may_affect_controlled",
			"fieldtype": "Data",
			"width": 110,
		},
		{"label": _("Manual"), "fieldname": "is_manual", "fieldtype": "Check", "width": 70},
		{"label": _("Identified on"), "fieldname": "identified_on", "fieldtype": "Date", "width": 110},
		{
			"label": _("Risk"),
			"fieldname": "risk_id",
			"fieldtype": "Link",
			"options": RISK_DT,
			"width": 120,
		},
	]


def get_data(filters):
	risk_filters = {}
	if filters.get("project"):
		risk_filters["project"] = filters.project
	if filters.get("status"):
		risk_filters["status"] = filters.status
	if filters.get("exposure"):
		risk_filters["exposure"] = filters.exposure
	try:
		risks = frappe.get_list(
			RISK_DT,
			filters=risk_filters,
			fields=[
				"name",
				"project",
				"source_section",
				"description",
				"probability",
				"impact",
				"exposure",
				"status",
				"risk_owner",
				"may_affect_controlled",
				"is_manual",
				"identified_on",
			],
			order_by="project asc, exposure desc, identified_on asc",
			limit_page_length=0,
			ignore_permissions=False,
		)
	except frappe.PermissionError:
		return []

	def t(value):
		# Traduce el token al idioma del usuario (cada campo usa tokens propios → género correcto).
		return _(value) if value else value

	rows = []
	for r in risks:
		rows.append(
			{
				"project": r.project,
				"section": r.source_section,
				"risk": strip_html(r.description or "").strip(),
				"probability": t(r.probability),
				"impact": t(r.impact),
				"exposure": t(r.exposure),
				"status": t(r.status),
				"owner": r.risk_owner,
				"may_affect_controlled": t(r.may_affect_controlled),
				"is_manual": r.is_manual,
				"identified_on": r.identified_on,
				"risk_id": r.name,
			}
		)
	return rows
