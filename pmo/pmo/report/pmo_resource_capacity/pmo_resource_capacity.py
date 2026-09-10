# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Resource Capacity — vista de mantenimiento/cobertura de `PMO Capacity` (ADR-0003 D1). Script Report.

Responde "¿qué capacidad efectiva tiene hoy cada recurso y quién NO la tiene configurada?" para poder
mantener `PMO Capacity`. Reutiliza la resolución única `pmo.capacity.get_capacity_detail` (no reimplementa
la regla override/global) y el tiering de observador de la app: normal → solo su Employee; PMO Manager /
Executive / Administrator → todos los Employees activos (con filtros opcionales). No expone Project/Task
(solo identidad organizacional + capacidad), por lo que no introduce una segunda política P4.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from pmo.capacity import get_capacity_detail
from pmo.permissions import _is_global_reader

MANAGER_ROLE = "PMO Manager"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.get("as_of") or today())
	data = _rows(_scope_employees(frappe.session.user, filters), as_of)
	return _columns(), data, None, None, _summary(data)


def _tier(observer):
	if observer == "Administrator" or _is_global_reader(observer):
		return "executive"
	if MANAGER_ROLE in frappe.get_roles(observer):
		return "manager"
	return "normal"


def _scope_employees(observer, filters):
	"""Alcance de recursos por observador. Normal → su propio Employee; manager/executive → activos.

	A diferencia de `PMO Capacity Planning`, aquí NO se filtra por actividad: el objetivo es la cobertura
	de configuración (incluye recursos aún sin capacidad ni carga)."""
	if _tier(observer) == "normal":
		own = frappe.db.get_value("Employee", {"user_id": observer, "status": "Active"}, "name")
		return [own] if own else []

	emp_filters = {"status": "Active"}
	if filters.get("employee"):
		emp_filters["name"] = filters.employee
	if filters.get("department"):
		emp_filters["department"] = filters.department
	return frappe.get_all("Employee", filters=emp_filters, pluck="name")


def _rows(employees, as_of):
	rows = []
	for emp in employees:
		meta = frappe.db.get_value("Employee", emp, ["employee_name", "department"], as_dict=True) or {}
		detail = get_capacity_detail(emp, as_of)
		rows.append(
			{
				"employee": emp,
				"employee_name": meta.get("employee_name"),
				"department": meta.get("department"),
				"capacity_hours_per_day": detail["hours"] if detail else None,
				# origen legible; "Faltante" cuando no hay ni override ni global vigente al corte.
				"origin": _origin_label(detail),
				"effective_from": str(detail["from_date"]) if detail else None,
			}
		)
	return rows


def _origin_label(detail):
	if not detail:
		return _("Faltante")
	return _("Override") if detail["origin"] == "override" else _("Global")


def _columns():
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 160,
		},
		{"fieldname": "employee_name", "label": _("Nombre"), "fieldtype": "Data", "width": 200},
		{"fieldname": "department", "label": _("Departamento"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "capacity_hours_per_day",
			"label": _("Capacidad h/día"),
			"fieldtype": "Float",
			"width": 130,
		},
		{"fieldname": "origin", "label": _("Origen"), "fieldtype": "Data", "width": 110},
		{"fieldname": "effective_from", "label": _("Vigente desde"), "fieldtype": "Date", "width": 120},
	]


def _summary(data):
	if not data:
		return []
	total = len(data)
	missing = sum(1 for r in data if r["capacity_hours_per_day"] is None)
	overrides = sum(1 for r in data if r["origin"] == _("Override"))
	return [
		{"label": _("Recursos"), "value": total, "datatype": "Int"},
		{
			"label": _("Sin capacidad configurada"),
			"value": missing,
			"datatype": "Int",
			"indicator": "Orange" if missing else "Green",
		},
		{"label": _("Con override individual"), "value": overrides, "datatype": "Int"},
	]
