# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Reporte PMO Work by Resource (ADR-0003 vistas / ADR-0002 P0-P4).

Tareas activas por recurso, con **doble evaluación de visibilidad independiente** (Task vs Project):

- Task visible + Project visible  -> Task y Project identificados (con links).
- Task visible + Project no visible -> Task identificada; Project = "Confidencial" (sin project_id).
- Task visible + sin Project       -> Task identificada; Project = "Sin proyecto".
- Task NO visible                  -> su identidad NUNCA llega al cliente; sus horas se consolidan en
                                      UNA fila "Comprometido (confidencial)" (sin task/subject/project/
                                      fechas/customer/conteo/ID auxiliar).

`planned_hours` = horas del asignado **dentro del rango** (misma distribución diaria del motor, vía
`get_planned_load_by_task`). Tareas visibles sin fechas se muestran con fechas vacías (no ubicables).
NO incluye Actual por Task (diferido). Confidencialidad afecta identidad, nunca el cálculo.
"""

import frappe
from frappe.utils import flt, getdate

from pmo.permissions import is_project_visible, is_task_visible
from pmo.planned_load import get_planned_load_by_task
from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import _scope_employees

CONFIDENTIAL_LABEL = frappe.N_("Committed (confidential)")
PROJECT_CONFIDENTIAL_LABEL = frappe.N_("Confidential")
NO_PROJECT_LABEL = frappe.N_("No project")
SCHEDULED_LABEL = frappe.N_("Scheduled")
UNSCHEDULED_LABEL = frappe.N_("Unscheduled")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if to_date < from_date:
		frappe.throw(frappe._("To Date cannot be earlier than From Date."))
	observer = frappe.session.user

	data = []
	for emp in _scope_employees(observer, filters, from_date, to_date):
		data.extend(_employee_tasks(emp, observer, from_date, to_date))
	return _columns(), data


def _employee_tasks(emp, observer, from_date, to_date):
	load = get_planned_load_by_task(emp, from_date, to_date)
	hours_by_task = load["hours_by_task"]  # {task: horas_en_rango} (con fechas → PROGRAMADO)
	unscheduled = {u["task"]: flt(u["hours"], 2) for u in load["unscheduled"]}  # sin fechas → SIN PROGRAMAR

	# La distinción programado/sin-programar se resuelve AQUÍ (server), no en el cliente: una Task sin
	# fechas y la fila confidencial consolidada ambas carecen de fechas, así que el JS no podría
	# separarlas sin esta marca. `scheduled` es un booleano de categoría (no identidad) → P4-safe.
	rows = []
	confidential = {True: 0.0, False: 0.0}  # {scheduled: horas} — sin identidad, solo horas por categoría
	tasks = [(t, True) for t in hours_by_task] + [(t, False) for t in unscheduled]
	for task, scheduled in tasks:
		hours = hours_by_task.get(task, unscheduled.get(task, 0.0))

		if not is_task_visible(task, observer):
			confidential[scheduled] += hours  # sin identidad; solo horas, separadas por categoría
			continue

		meta = frappe.db.get_value(
			"Task",
			task,
			["subject", "project", "exp_start_date", "exp_end_date", "status", "expected_time"],
			as_dict=True,
		)
		project_label, project_id = _project_cell(meta.project, observer)
		row = {
			"employee": emp,
			"task": meta.subject or task,
			"task_id": task,  # identificador auxiliar — solo Tasks visibles
			"project": project_label,
			"exp_start_date": meta.exp_start_date,
			"exp_end_date": meta.exp_end_date,
			"expected_time": flt(meta.expected_time, 2),
			"planned_hours": flt(hours, 2),
			"scheduled": scheduled,
			"scheduling": frappe._(SCHEDULED_LABEL) if scheduled else frappe._(UNSCHEDULED_LABEL),
			"status": meta.status,
		}
		if project_id:
			row["project_id"] = project_id  # solo si el Project es visible
		rows.append(row)

	# Hasta dos filas confidenciales consolidadas (programada / sin programar), cada una solo con horas:
	# nunca task/subject/project/fechas/ID. Separar por categoría permite subtotales correctos sin P4-leak.
	for scheduled, amount in confidential.items():
		if amount:
			rows.append(
				{
					"employee": emp,
					"task": frappe._(CONFIDENTIAL_LABEL),
					"project": None,
					"planned_hours": flt(amount, 2),
					"scheduled": scheduled,
					"scheduling": frappe._(SCHEDULED_LABEL) if scheduled else frappe._(UNSCHEDULED_LABEL),
				}
			)
	return rows


def _project_cell(project, observer):
	"""Devuelve (etiqueta, project_id|None) para la columna Project, aplicando P4 independiente."""
	if not project:
		return frappe._(NO_PROJECT_LABEL), None
	if is_project_visible(project, observer):
		label = frappe.db.get_value("Project", project, "project_name") or project
		return label, project
	return frappe._(PROJECT_CONFIDENTIAL_LABEL), None  # Project oculto: sin project_id


def _columns():
	return [
		{
			"fieldname": "employee",
			"label": frappe._("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 170,
		},
		{"fieldname": "task", "label": frappe._("Task"), "fieldtype": "Data", "width": 240},
		{"fieldname": "project", "label": frappe._("Project"), "fieldtype": "Data", "width": 200},
		{"fieldname": "exp_start_date", "label": frappe._("Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "exp_end_date", "label": frappe._("End"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "expected_time",
			"label": frappe._("Expected Time"),
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "planned_hours",
			"label": frappe._("Planned (period)"),
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"fieldname": "scheduling",
			"label": frappe._("Scheduling"),
			"fieldtype": "Data",
			"width": 120,
		},
		{"fieldname": "status", "label": frappe._("Status"), "fieldtype": "Data", "width": 110},
	]
