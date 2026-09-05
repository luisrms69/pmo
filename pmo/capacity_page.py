# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Endpoints server-side para la Page 'Capacity Planning' (ADR-0003 vistas / ADR-0002 P4).

Solo metadata de recursos (Employee). NO devuelve Project/Task ni introduce una segunda política de
permisos: reutiliza EXACTAMENTE el mismo alcance de observador que los reportes (`_scope_employees`).
Los datos de carga/capacidad los obtiene la Page llamando a los Script Reports P4-safe existentes
(`frappe.desk.query_report.run`), no aquí.
"""

import frappe
from frappe.utils import getdate

from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import _scope_employees


@frappe.whitelist()
def get_resources(from_date: str, to_date: str) -> list[dict]:
	"""Resource Center: Employees en el alcance del observador (mismo scope que los reportes).

	Devuelve solo identidad organizacional del recurso (nombre, email, departamento, cargo, sucursal).
	Interna al Page; NO expone Project/Task. Normal -> solo su Employee; Manager/Executive -> todos
	(cuantitativo). `branch` es el campo nativo real de Employee (sucursal); se devuelve tal cual y la
	Page solo lo muestra si tiene valor (nunca se renombra ni se inventa una jerarquia tipo "Tower").
	"""
	observer = frappe.session.user
	filters = frappe._dict({"from_date": from_date, "to_date": to_date})
	employees = _scope_employees(observer, filters, getdate(from_date), getdate(to_date))

	resources = []
	for emp in employees:
		meta = (
			frappe.db.get_value(
				"Employee",
				emp,
				["employee_name", "user_id", "department", "designation", "branch"],
				as_dict=True,
			)
			or {}
		)
		resources.append(
			{
				"employee": emp,
				"employee_name": meta.get("employee_name"),
				"email": meta.get("user_id"),
				"department": meta.get("department"),
				"designation": meta.get("designation"),
				"branch": meta.get("branch"),
			}
		)
	return resources
