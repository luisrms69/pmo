# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Projects Without Governance — proyectos ACTIVOS explícitamente excluidos de la gobernanza PMO.

Superficie de supervisión secundaria (Bloque 6): permite a la PMO revisar periódicamente qué proyectos
activos fueron excluidos, con su justificación y trazabilidad (motivo · autorizado por · fecha). NO es
protagonista de la Home. Solo lectura; P4 vía `frappe.get_list` (impone permission_query_conditions de
Project). "Activo" = estado no terminal (ni Completed ni Cancelled)."""

import frappe
from frappe import _

from pmo.governance import TERMINAL_STATUSES


def execute(filters=None):
	columns = [
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 160,
		},
		{"label": _("Project name"), "fieldname": "project_name", "fieldtype": "Data", "width": 220},
		{
			"label": _("Project Manager"),
			"fieldname": "project_manager",
			"fieldtype": "Link",
			"options": "User",
			"width": 180,
		},
		{"label": _("Exclusion reason"), "fieldname": "reason", "fieldtype": "Data", "width": 280},
		{
			"label": _("Authorized by"),
			"fieldname": "exempt_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 180,
		},
		{"label": _("Exclusion date"), "fieldname": "exempt_on", "fieldtype": "Datetime", "width": 170},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]
	rows = frappe.get_list(
		"Project",
		filters={"pmo_governance_exempt": 1, "status": ["not in", TERMINAL_STATUSES]},
		fields=[
			"name as project",
			"project_name",
			"pmo_project_manager as project_manager",
			"pmo_exempt_reason as reason",
			"pmo_exempt_by as exempt_by",
			"pmo_exempt_on as exempt_on",
			"status",
		],
		order_by="pmo_exempt_on desc",
		limit=0,
	)
	return columns, rows
