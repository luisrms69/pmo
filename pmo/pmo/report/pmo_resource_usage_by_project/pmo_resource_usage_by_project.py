# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Reporte PMO Resource Usage by Project (ADR-0003 vistas / ADR-0002 P4).

Árbol Employee -> Project (indent) con Planned y Actual por proyecto, derivado del motor v0.3.0
(`get_planned_load_by_project` + `get_actual_by_project`). No recalcula nada.

Enmascarado P4 SERVER-SIDE por observador:
- Proyecto visible (boundary P0) -> nombre real + identificador auxiliar (`project_id`) para el link.
- Proyecto NO visible -> se consolida en UNA sola fila "Comprometido (confidencial)": solo etiqueta,
  SIN project_id/name/customer/task/conteo. El cliente nunca recibe identidad confidencial.
- Trabajo sin Project -> bucket separado "Sin proyecto" (no revela identidad porque no existe).

Confidencialidad afecta identidad, NUNCA el cálculo:
    Total Employee (Planned) = Σ visibles + Sin proyecto + Comprometido (confidencial)   (idem Actual)

No incluye % utilización: Capacity/Availability son del Employee, no están distribuidas por Project;
usarlas como denominador por proyecto sería engañoso.
"""

import frappe
from frappe.utils import add_days, flt, getdate

from pmo.actual import get_actual_by_project
from pmo.permissions import is_project_visible
from pmo.planned_load import get_planned_load_by_project
from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import (
	_bucket_key,
	_period_label,
	_scope_employees,
)

CONFIDENTIAL_LABEL = "Comprometido (confidencial)"
NO_PROJECT_LABEL = "Sin proyecto"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if to_date < from_date:
		frappe.throw(frappe._("To Date no puede ser anterior a From Date."))
	observer = frappe.session.user

	# Vista temporal (Page "Uso de recursos por proyecto"): matriz Proyecto x periodo, SOLO Planned.
	# Reusa el motor (`get_planned_load_by_project`) y el MISMO P4 (`is_project_visible`); no recalcula.
	granularity = filters.get("granularity")
	if granularity in ("Day", "Week", "Month"):
		return _execute_temporal(filters, observer, from_date, to_date, granularity)

	# Vista por defecto (Desk / tree Employee->Project con Planned + Actual). Inalterada.
	data = []
	for emp in _scope_employees(observer, filters, from_date, to_date):
		data.extend(_employee_subtree(emp, observer, from_date, to_date))
	return _columns(), data


def _employee_subtree(emp, observer, from_date, to_date):
	planned = get_planned_load_by_project(emp, from_date, to_date)["days_by_project"]
	actual = get_actual_by_project(emp, from_date, to_date)

	planned_by_project = {p: flt(sum(days.values()), 2) for p, days in planned.items()}
	actual_by_project = {p: flt(sum(days.values()), 2) for p, days in actual.items()}

	visible = {}  # project_name -> [planned, actual]
	no_project = [0.0, 0.0]
	confidential = [0.0, 0.0]

	for project in set(planned_by_project) | set(actual_by_project):
		pl = planned_by_project.get(project, 0.0)
		ac = actual_by_project.get(project, 0.0)
		if not project:
			no_project[0] += pl
			no_project[1] += ac
		elif is_project_visible(project, observer):
			bucket = visible.setdefault(project, [0.0, 0.0])
			bucket[0] += pl
			bucket[1] += ac
		else:
			confidential[0] += pl
			confidential[1] += ac

	total_planned = flt(sum(v[0] for v in visible.values()) + no_project[0] + confidential[0], 2)
	total_actual = flt(sum(v[1] for v in visible.values()) + no_project[1] + confidential[1], 2)

	rows = [
		{
			"employee": emp,
			"project": None,  # la fila padre lleva la identidad en la columna Employee
			"planned": total_planned,
			"actual": total_actual,
			"indent": 0,
		}
	]

	# Proyectos visibles: etiqueta legible + project_id auxiliar (SOLO visibles) para el link.
	for project in sorted(visible):
		label = frappe.db.get_value("Project", project, "project_name") or project
		rows.append(
			{
				"employee": None,
				"project": label,
				"project_id": project,  # identificador auxiliar — solo proyectos visibles
				"planned": flt(visible[project][0], 2),
				"actual": flt(visible[project][1], 2),
				"indent": 1,
			}
		)

	# Sin proyecto (dimensión Project vacía): sin identidad porque no existe; participa en el total.
	if no_project[0] or no_project[1]:
		rows.append(
			{
				"employee": None,
				"project": frappe._(NO_PROJECT_LABEL),
				"planned": flt(no_project[0], 2),
				"actual": flt(no_project[1], 2),
				"indent": 1,
			}
		)

	# Comprometido (confidencial): UNA sola fila; SIN project_id ni identidad alguna.
	if confidential[0] or confidential[1]:
		rows.append(
			{
				"employee": None,
				"project": frappe._(CONFIDENTIAL_LABEL),
				"planned": flt(confidential[0], 2),
				"actual": flt(confidential[1], 2),
				"indent": 1,
			}
		)

	return rows


def _columns():
	return [
		{
			"fieldname": "employee",
			"label": frappe._("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 200,
		},
		{"fieldname": "project", "label": frappe._("Project / bucket"), "fieldtype": "Data", "width": 280},
		{"fieldname": "planned", "label": frappe._("Planned"), "fieldtype": "Float", "width": 120},
		{"fieldname": "actual", "label": frappe._("Actual"), "fieldtype": "Float", "width": 120},
	]


# --- vista temporal (Proyecto x periodo, solo Planned; P4 server-side) -----------------


def _period_keys(from_date, to_date, granularity):
	"""Claves de periodo en orden cronologico que cubren el rango (mismo bucketing que Capacity)."""
	keys, seen = [], set()
	day = from_date
	while day <= to_date:
		k = _bucket_key(day, granularity)
		if k not in seen:
			seen.add(k)
			keys.append(k)
		day = add_days(day, 1)
	return keys


def _temporal_columns(keys, granularity, period_fields):
	cols = [
		{
			"fieldname": "employee",
			"label": frappe._("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 180,
		},
		{"fieldname": "project", "label": frappe._("Project / bucket"), "fieldtype": "Data", "width": 240},
	]
	for i, k in enumerate(keys):
		cols.append(
			{
				"fieldname": period_fields[i],
				"label": _period_label(k, granularity),
				"fieldtype": "Float",
				"width": 100,
			}
		)
	cols.append({"fieldname": "total", "label": frappe._("Total"), "fieldtype": "Float", "width": 110})
	return cols


def _execute_temporal(filters, observer, from_date, to_date, granularity):
	keys = _period_keys(from_date, to_date, granularity)
	period_fields = [f"period_{i}" for i in range(len(keys))]

	data = []
	for emp in _scope_employees(observer, filters, from_date, to_date):
		data.extend(_employee_temporal(emp, observer, from_date, to_date, granularity, keys, period_fields))
	return _temporal_columns(keys, granularity, period_fields), data


def _employee_temporal(emp, observer, from_date, to_date, granularity, keys, period_fields):
	"""Filas Proyecto x periodo (Planned) para un Employee. P4: visibles identificados; ocultos en UN
	unico bucket "Comprometido (confidencial)" por periodo (sin id/nombre/conteo); "Sin proyecto" aparte.
	"""
	planned = get_planned_load_by_project(emp, from_date, to_date)["days_by_project"]

	# label/id -> {period_key: horas}; buckets no identificables agregados por periodo
	visible = {}  # project(name real) -> {"id":..., "by":{key:horas}}
	no_project = {}  # key -> horas
	confidential = {}  # key -> horas
	for project, days in planned.items():
		for d, hours in days.items():
			if not hours:
				continue
			k = _bucket_key(d, granularity)
			if not project:
				no_project[k] = no_project.get(k, 0.0) + hours
			elif is_project_visible(project, observer):
				b = visible.setdefault(project, {"by": {}})
				b["by"][k] = b["by"].get(k, 0.0) + hours
			else:
				confidential[k] = confidential.get(k, 0.0) + hours

	def _mk(project_label, by, project_id=None):
		row = {"employee": None, "project": project_label, "indent": 1}
		if project_id:
			row["project_id"] = project_id  # SOLO proyectos visibles
		total = 0.0
		for i, k in enumerate(keys):
			v = flt(by.get(k, 0.0), 2)
			row[period_fields[i]] = v
			total += v
		row["total"] = flt(total, 2)
		return row

	children = []
	for project in sorted(visible):
		label = frappe.db.get_value("Project", project, "project_name") or project
		children.append(_mk(label, visible[project]["by"], project_id=project))
	if any(no_project.values()):
		children.append(_mk(frappe._(NO_PROJECT_LABEL), no_project))
	if any(confidential.values()):
		children.append(_mk(frappe._(CONFIDENTIAL_LABEL), confidential))

	# Fila padre (Total planificado del Employee) = suma de los hijos por periodo -> parent = Σ hijos,
	# y total de cada fila = Σ de sus periodos (consistencia interna garantizada).
	parent = {"employee": emp, "project": None, "indent": 0}
	ptotal = 0.0
	for field in period_fields:
		v = flt(sum(c[field] for c in children), 2)
		parent[field] = v
		ptotal += v
	parent["total"] = flt(ptotal, 2)

	return [parent, *children]
