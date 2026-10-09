# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Resource Capacity - cobertura de jornada por recurso (Capacity Paso 4). Script Report.

Responde "¿qué capacidad neta tiene hoy cada recurso, de qué **origen** (Shift de HRMS vs default de PMO
Settings), y quién NO tiene turno asignado?". Reutiliza la resolución única
`pmo.capacity.get_employee_daily_capacity` (no reimplementa la regla) y el tiering de observador: normal →
solo su Employee; PMO Manager / Executive / Administrator → todos los Employees activos.

El estado `missing_shift` (sin turno resoluble, aunque haya fallback a default) se muestra **en rojo** vía
el formatter del `.js` - es informativo, no bloqueante: señala falta de jornada en HRMS, no que la
capacidad sea 0.
"""

import frappe
from frappe import N_, _
from frappe.utils import getdate, today

from pmo.capacity import get_employee_daily_capacity
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

	Objetivo = cobertura de jornada: incluye recursos SIN turno (para que salten en rojo)."""
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
		cap = get_employee_daily_capacity(emp, as_of)
		rows.append(
			{
				"employee": emp,
				"employee_name": meta.get("employee_name"),
				"department": meta.get("department"),
				"capacity_hours_per_day": cap["hours"],
				# origin_key: estable e independiente del idioma (shift/default/missing)
				"origin_key": cap["origin"],
				"origin": _origin_label(cap["origin"]),  # presentación traducida
				"shift_type": cap["shift_type"],
				# consumido por el formatter del .js para pintar en rojo
				"missing_shift": 1 if cap["missing_shift"] else 0,
				"status": _status_label(cap),
			}
		)
	return rows


# ORIGIN internos estables → etiqueta de presentación (se traduce con `_()`).
ORIGIN_LABELS = {"shift": N_("Shift"), "default": N_("Default"), "missing": N_("Missing")}


def _origin_label(origin_key):
	return _(ORIGIN_LABELS.get(origin_key, ORIGIN_LABELS["missing"]))


def _status_label(cap):
	"""Texto de estado operativo (se pinta en rojo cuando `missing_shift`)."""
	if cap["origin"] == "shift":
		return _("Shift")
	if cap["origin"] == "default":
		return _("No shift assigned - using default")
	return _("No shift assigned / no capacity")


def _columns():
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 160,
		},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "capacity_hours_per_day",
			"label": _("Net capacity h/day"),
			"fieldtype": "Float",
			"width": 140,
		},
		{"fieldname": "origin", "label": _("Origin"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "shift_type",
			"label": _("Shift Type"),
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 150,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 240},
		# oculto: lo consume el formatter del .js para pintar la fila en rojo
		{
			"fieldname": "missing_shift",
			"label": _("Missing shift"),
			"fieldtype": "Check",
			"width": 1,
			"hidden": 1,
		},
	]


def _summary(data):
	if not data:
		return []
	total = len(data)
	missing_shift = sum(1 for r in data if r.get("missing_shift"))
	no_capacity = sum(1 for r in data if r["capacity_hours_per_day"] is None)
	return [
		{"label": _("Resources"), "value": total, "datatype": "Int"},
		{
			"label": _("Without assigned shift"),
			"value": missing_shift,
			"datatype": "Int",
			"indicator": "Red" if missing_shift else "Green",
		},
		{
			"label": _("Without resolvable capacity"),
			"value": no_capacity,
			"datatype": "Int",
			"indicator": "Red" if no_capacity else "Green",
		},
	]
