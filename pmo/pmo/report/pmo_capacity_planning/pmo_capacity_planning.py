# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Reporte PMO Capacity Planning (ADR-0003 D6 / ADR-0002 P4).

Fila primaria = Employee x periodo. Deriva Capacity/Availability/PlannedLoad/Actual y aplica el
enmascarado P4 SERVER-SIDE por observador antes de devolver datos:

- Executive -> todas las personas + identidades permitidas completas.
- PMO Manager -> todas las personas cuantitativamente + P4.
- Employee normal -> únicamente su propio Employee + P4.

P4: las horas de Projects que el observador NO puede ver (boundary P0) se agregan en un único bucket
"Comprometido (confidencial)" = total - Sigma(visibles); nunca se enumeran ni se envían al cliente los
Projects/Tasks confidenciales. Planned y Actual nunca se suman; dos utilizaciones separadas.
"""

import frappe
from frappe.utils import add_days, flt, formatdate, get_first_day, getdate

from pmo.actual import get_actual_by_project
from pmo.availability import get_availability
from pmo.capacity import get_capacity
from pmo.permissions import _is_global_reader, is_project_visible
from pmo.planned_load import get_planned_load_by_project

MANAGER_ROLE = "PMO Manager"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if to_date < from_date:
		frappe.throw(frappe._("To Date no puede ser anterior a From Date."))
	granularity = filters.get("granularity") or "Day"
	observer = frappe.session.user

	data = []
	for emp in _scope_employees(observer, filters, from_date, to_date):
		data.extend(_employee_rows(emp, observer, from_date, to_date, granularity))
	return _columns(), data


# --- alcance de filas (por observador) -----------------------------------------


def _tier(observer):
	if observer == "Administrator" or _is_global_reader(observer):
		return "executive"
	if MANAGER_ROLE in frappe.get_roles(observer):
		return "manager"
	return "normal"


def _scope_employees(observer, filters, from_date, to_date):
	if _tier(observer) == "normal":
		own = frappe.db.get_value("Employee", {"user_id": observer, "status": "Active"}, "name")
		return [own] if own else []

	if filters.get("employee"):
		candidates = [filters.employee]
	else:
		candidates = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")

	scoped = []
	for emp in candidates:
		if get_capacity(emp, to_date) is not None or _has_activity(emp, from_date, to_date):
			scoped.append(emp)
	return scoped


def _has_activity(emp, from_date, to_date):
	planned = get_planned_load_by_project(emp, from_date, to_date)
	if planned["days_by_project"] or planned["unscheduled"] or planned["issues"]:
		return True
	return bool(get_actual_by_project(emp, from_date, to_date))


# --- filas por Employee ---------------------------------------------------------


def _bucket_key(date, granularity):
	if granularity == "Week":
		return add_days(date, -date.weekday())  # lunes de la semana
	if granularity == "Month":
		return get_first_day(date)
	return date


def _period_label(key, granularity):
	if granularity == "Week":
		return frappe._("Semana de {0}").format(formatdate(key))
	if granularity == "Month":
		return key.strftime("%Y-%m")
	return formatdate(key)


def _employee_rows(emp, observer, from_date, to_date, granularity):
	planned = get_planned_load_by_project(emp, from_date, to_date)
	actual = get_actual_by_project(emp, from_date, to_date)
	planned_days = planned["days_by_project"]

	buckets = {}
	day = from_date
	while day <= to_date:
		pv = pc = av = ac = 0.0
		for project, days in planned_days.items():
			hours = days.get(day, 0)
			if hours:
				if is_project_visible(project, observer):
					pv += hours
				else:
					pc += hours
		for project, days in actual.items():
			hours = days.get(day, 0)
			if hours:
				if is_project_visible(project, observer):
					av += hours
				else:
					ac += hours

		cap = get_capacity(emp, day)
		avail = get_availability(emp, day)
		bucket = buckets.setdefault(
			_bucket_key(day, granularity),
			{"cap": 0.0, "avail": 0.0, "pv": 0.0, "pc": 0.0, "av": 0.0, "ac": 0.0},
		)
		bucket["cap"] += flt(cap) if cap is not None else 0
		bucket["avail"] += flt(avail) if avail is not None else 0
		bucket["pv"] += pv
		bucket["pc"] += pc
		bucket["av"] += av
		bucket["ac"] += ac
		day = add_days(day, 1)

	status = _status(emp, to_date, planned)
	rows = []
	for key in sorted(buckets):
		b = buckets[key]
		planned_total = flt(b["pv"] + b["pc"], 2)
		actual_total = flt(b["av"] + b["ac"], 2)
		avail = flt(b["avail"], 2)
		rows.append(
			{
				"employee": emp,
				"period": _period_label(key, granularity),
				"capacity": flt(b["cap"], 2),
				"availability": avail,
				"planned_visible": flt(b["pv"], 2),
				"confidential": flt(b["pc"], 2),
				"planned_total": planned_total,
				"actual_visible": flt(b["av"], 2),
				"actual_confidential": flt(b["ac"], 2),
				"actual_total": actual_total,
				"free": flt(avail - planned_total, 2),
				"overallocation": flt(max(0.0, planned_total - avail), 2),
				"util_planned": flt(planned_total / avail * 100, 1) if avail > 0 else None,
				"util_actual": flt(actual_total / avail * 100, 1) if avail > 0 else None,
				"status": status,
			}
		)
	return rows


def _status(emp, to_date, planned):
	"""Flags de integridad SIN identidad (P4-safe): solo presencia de categorías, no nombres ni conteos."""
	flags = []
	if get_capacity(emp, to_date) is None:
		flags.append(frappe._("capacidad faltante"))
	if planned["issues"]:
		flags.append(frappe._("inconsistencias"))
	if planned["unscheduled"]:
		flags.append(frappe._("sin fechas"))
	if planned["unmapped"]:
		flags.append(frappe._("mapeo"))
	return " · ".join(flags)


# --- columnas -------------------------------------------------------------------


def _columns():
	def col(field, label, ftype="Float", width=110, options=None):
		c = {"fieldname": field, "label": frappe._(label), "fieldtype": ftype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("employee", "Employee", "Link", 140, "Employee"),
		col("period", "Periodo", "Data", 130),
		col("capacity", "Capacity"),
		col("availability", "Availability"),
		col("planned_visible", "Planned visible"),
		col("confidential", "Comprometido (confidencial)", "Float", 180),
		col("planned_total", "Planned total"),
		col("actual_visible", "Actual visible"),
		col("actual_confidential", "Actual confidencial", "Float", 150),
		col("actual_total", "Actual total"),
		col("free", "Libre"),
		col("overallocation", "Sobreasignación", "Float", 130),
		col("util_planned", "Util. planificada %", "Float", 140),
		col("util_actual", "Util. real %", "Float", 120),
		col("status", "Estado", "Data", 200),
	]
