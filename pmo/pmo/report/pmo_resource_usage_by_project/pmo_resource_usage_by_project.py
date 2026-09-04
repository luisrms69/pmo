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
from frappe.utils import flt, getdate

from pmo.actual import get_actual_by_project
from pmo.permissions import is_project_visible
from pmo.planned_load import get_planned_load_by_project
from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import _scope_employees

CONFIDENTIAL_LABEL = "Comprometido (confidencial)"
NO_PROJECT_LABEL = "Sin proyecto"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if to_date < from_date:
		frappe.throw(frappe._("To Date no puede ser anterior a From Date."))
	observer = frappe.session.user

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
