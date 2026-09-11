# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Planned vs Actual (ADR-0008) — reporte de esfuerzo Planificado vs Real por Project/Task.

Capacidad de **reporting** (no una capa de planificación): pone lado a lado datos ya nativos.
- **Planned** = `Task.expected_time`.
- **Actual**: sin `status_date` → `Task.actual_time` (acumulado nativo alimentado por Timesheet); con
  `status_date` → Σ `Timesheet Detail.hours` submitted hasta la fecha (`pmo.actual`, semántica ADR-0003).
- **Variance Hours** = Actual - Planned; **% Consumed** = Actual / Planned (guarda de división por 0).
- Detalle por **Task hoja**; total de Project excluyendo `is_group` del rollup.

P4-safe por delegación: los Script Report NO aplican `permission_query_conditions`, así que `execute` exige
que el Project sea visible para el usuario (`pmo.permissions.is_project_visible`), como el resto de reports
P4 de la app. Sin motor nuevo, sin DocTypes/Custom Fields; ADR-0004/0006/0007 y Baseline sin cambios.
"""

import frappe
from frappe import _
from frappe.utils import flt

from pmo.actual import get_actual_hours_asof, get_actual_hours_by_task_asof
from pmo.permissions import is_project_visible


def execute(filters=None):
	filters = frappe._dict(filters or {})
	project = filters.get("project")
	if not project:
		frappe.throw(_("Select a Project."))
	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} does not exist.").format(project))

	# P4: los Script Report no aplican pqc → exigir visibilidad del Project (owner/DocShare/executive).
	if not is_project_visible(project, frappe.session.user):
		raise frappe.PermissionError(_("You do not have access to this Project."))

	status_date = filters.get("status_date")

	# Tareas del Project (planned nativo + actual nativo acumulado).
	tasks = frappe.get_all(
		"Task",
		filters={"project": project},
		fields=["name", "subject", "expected_time", "actual_time", "is_group"],
		order_by="lft asc",
	)

	# Actual: as-of por Timesheet si hay fecha de corte; si no, el acumulado nativo de la Task.
	actual_by_task = get_actual_hours_by_task_asof(project, status_date) if status_date else None

	data, tot_planned, tot_actual = _rows(tasks, actual_by_task)
	return _columns(), data, None, None, _summary(project, status_date, tot_planned, tot_actual)


def _rows(tasks, actual_by_task):
	"""Filas por Task hoja + totales (puro, testeable). Excluye `is_group` del rollup (envelope, evita doble
	conteo). Actual = map as-of (`actual_by_task`) si se pasó; si es None, el `actual_time` nativo de la Task."""
	data = []
	tot_planned = tot_actual = 0.0
	for t in tasks:
		if t.get("is_group"):
			continue
		planned = flt(t.get("expected_time"), 2)
		if actual_by_task is not None:
			actual = flt(actual_by_task.get(t.get("name"), 0), 2)
		else:
			actual = flt(t.get("actual_time"), 2)
		tot_planned += planned
		tot_actual += actual
		data.append(
			{
				"task": t.get("name"),
				"subject": t.get("subject"),
				"planned_hours": planned,
				"actual_hours": actual,
				"variance_hours": flt(actual - planned, 2),
				"pct_consumed": _pct(actual, planned),
			}
		)
	return data, flt(tot_planned, 2), flt(tot_actual, 2)


def _pct(actual, planned):
	"""% consumido = actual/planned*100; None si no hay plan (evita división por 0)."""
	return flt(actual / planned * 100, 1) if planned else None


def _columns():
	return [
		{"fieldname": "task", "label": _("Task"), "fieldtype": "Link", "options": "Task", "width": 200},
		{"fieldname": "subject", "label": _("Description"), "fieldtype": "Data", "width": 300},
		{"fieldname": "planned_hours", "label": _("Planned Hours"), "fieldtype": "Float", "width": 130},
		{"fieldname": "actual_hours", "label": _("Actual Hours"), "fieldtype": "Float", "width": 130},
		{"fieldname": "variance_hours", "label": _("Variance Hours"), "fieldtype": "Float", "width": 130},
		{"fieldname": "pct_consumed", "label": _("% Consumed"), "fieldtype": "Percent", "width": 110},
	]


def _summary(project, status_date, planned, actual):
	# Total de Project a nivel esfuerzo. El Actual total respeta la fecha de corte si se indicó.
	project_actual = get_actual_hours_asof(project, status_date) if status_date else flt(actual, 2)
	variance = flt(project_actual - planned, 2)
	return [
		{
			"label": _("Cutoff (Status Date)"),
			"value": str(status_date) if status_date else _("Total (native)"),
			"datatype": "Data",
		},
		{"label": _("Planned Hours (Project)"), "value": flt(planned, 2), "datatype": "Float"},
		{"label": _("Actual Hours (Project)"), "value": flt(project_actual, 2), "datatype": "Float"},
		{
			"label": _("Variance Hours"),
			"value": variance,
			"datatype": "Float",
			"indicator": "Red" if variance > 0 else "Green",
		},
		{"label": _("% Consumed"), "value": _pct(project_actual, planned) or 0, "datatype": "Percent"},
	]
