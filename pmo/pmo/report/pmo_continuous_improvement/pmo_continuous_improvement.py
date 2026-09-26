# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Continuous Improvement — seguimiento operativo de las acciones nacidas de Lessons Learned.

Capacidad SEPARADA de Governance (ver docstring de PMO Post-Project Review). La unidad es la ACCIÓN,
materializada como ToDo NATIVO (reference_type = "PMO Post-Project Review"). No hay DocType de acciones,
ni estados custom, ni workflow: el estado/cierre viven en el ToDo.

P4: la visibilidad se resuelve PRIMERO sobre los Post-Project Review visibles para el usuario
(`frappe.get_list` aplica `get_permission_query_conditions_review`), y los ToDo se limitan a esas
referencias. Que ToDo tenga permisos amplios NO permite descubrir un Review/Project oculto.
Administrator/Executive conservan su comportamiento normal (global readers).
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, strip_html

REVIEW_DT = "PMO Post-Project Review"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 300},
		{
			"label": _("Responsible"),
			"fieldname": "responsible",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": _("Target date"), "fieldname": "target_date", "fieldtype": "Date", "width": 110},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Check", "width": 80},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 160,
		},
		{
			"label": _("Post-Project Review"),
			"fieldname": "review",
			"fieldtype": "Link",
			"options": "PMO Post-Project Review",
			"width": 150,
		},
		{"label": _("ToDo"), "fieldname": "todo", "fieldtype": "Link", "options": "ToDo", "width": 110},
	]


def get_data(filters):
	# P4: Reviews VISIBLES para el usuario actual (respeta permission_query_conditions del Review).
	review_filters = {}
	if filters.get("project"):
		review_filters["project"] = filters.project
	try:
		reviews = frappe.get_list(
			REVIEW_DT,
			filters=review_filters,
			fields=["name", "project"],
			limit_page_length=0,
			ignore_permissions=False,
		)
	except frappe.PermissionError:
		# Usuario sin permiso de lectura sobre el Review → no ve ninguna acción (fail-closed).
		return []
	if not reviews:
		return []
	review_project = {r.name: r.project for r in reviews}

	# ToDo limitados a esas referencias visibles (nunca se descubre un Review/Project oculto).
	todo_filters = {
		"reference_type": REVIEW_DT,
		"reference_name": ["in", list(review_project.keys())],
	}
	status = filters.get("status") or "Open"
	if status and status != "All":
		todo_filters["status"] = status
	if filters.get("responsible"):
		todo_filters["allocated_to"] = filters.responsible

	todos = frappe.get_all(
		"ToDo",
		filters=todo_filters,
		fields=["name", "description", "allocated_to", "date", "status", "reference_name"],
		order_by="date asc",
	)

	today = getdate(nowdate())
	rows = []
	for t in todos:
		is_overdue = 1 if (t.status == "Open" and t.date and getdate(t.date) < today) else 0
		if filters.get("overdue") and not is_overdue:
			continue
		rows.append(
			{
				"action": strip_html(t.description or "").strip(),
				"responsible": t.allocated_to,
				"target_date": t.date,
				"overdue": is_overdue,
				"status": t.status,
				"project": review_project.get(t.reference_name),
				"review": t.reference_name,
				"todo": t.name,
			}
		)
	return rows
