# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Carga planificada (Planned Load) derivada de Task + Assignment (ADR-0003 D2/D3/D4).

Fuente de verdad NATIVA (sin captura paralela):
    - Task: `expected_time` (esfuerzo), `exp_start_date`/`exp_end_date` (rango), `status`.
    - Assignment: `ToDo` activo (`status="Open"`, `reference_type="Task"`) → persona (User).
    - Horas por asignado: Custom Field opcional `ToDo.pmo_planned_hours` (vacío = reparto uniforme).

Principio de integridad: Capacity Planning sigue funcionando aunque una Task esté mal configurada, pero
NUNCA oculta que parte del esfuerzo quedó fuera. Por eso los retornos son ESTRUCTURADOS: además de las
horas calculables, devuelven `issues` (Tasks inconsistentes + motivo), `unscheduled` (horas conocidas sin
fechas) y `unmapped` (problemas de mapeo User↔Employee). Ningún float suelto que subestime carga.

Funciones INTERNAS server-side (no whitelisted): el enmascarado P4 se aplica en la capa de reportes.
"""

import frappe
from frappe.utils import flt, getdate

from pmo.allocation import build_allocation_days

# Estados de Task que representan carga planificada PENDIENTE (Completed lo cubre Actual; Cancelled/
# Template no son trabajo real).
TASK_STATUSES_IN = ("Open", "Working", "Pending Review", "Overdue")
_TOL = 0.01


def _active_employees_for_user(user: str) -> list[str]:
	return frappe.get_all("Employee", filters={"user_id": user, "status": "Active"}, pluck="name")


def _maps_to_single_employee(user: str) -> bool:
	return len(_active_employees_for_user(user)) == 1


def get_planned_hours_per_assignee(task: str) -> dict:
	"""Reparte `Task.expected_time` entre los asignados activos (ToDo Open) según D3.

	Devuelve {task, expected_time, per_assignee: {user: hours}, unmapped: [user], consistent, issues}.
	Si es inconsistente, `per_assignee` queda vacío (no se emiten horas inválidas) y `issues` explica.
	"""
	expected = flt(frappe.db.get_value("Task", task, "expected_time"))
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "reference_name": task, "status": "Open"},
		fields=["allocated_to", "pmo_planned_hours"],
	)
	# Nativo impide ToDo Open duplicado por user+task; deduplicamos por seguridad.
	assignees = {t.allocated_to: flt(t.pmo_planned_hours) for t in todos}

	result = {
		"task": task,
		"expected_time": expected,
		"per_assignee": {},
		"unmapped": [u for u in assignees if not _maps_to_single_employee(u)],
		"consistent": True,
		"issues": [],
	}

	if not assignees:
		return result  # sin asignados activos: nada que repartir

	if expected <= 0:
		result["consistent"] = False
		result["issues"].append("no_expected_time")
		return result

	overrides = {u: h for u, h in assignees.items() if h > 0}
	non_override = [u for u, h in assignees.items() if h <= 0]
	sum_overrides = sum(overrides.values())

	if sum_overrides - expected > _TOL:
		result["consistent"] = False
		result["issues"].append("overrides_exceed_expected")
		return result

	if not non_override:
		# todos con override → Σ debe ser exactamente expected_time (menor o mayor = inconsistente)
		if abs(sum_overrides - expected) > _TOL:
			result["consistent"] = False
			result["issues"].append("all_overrides_mismatch")
			return result
		result["per_assignee"] = {u: flt(h, 2) for u, h in overrides.items()}
		return result

	# overrides parciales (o ninguno): repartir el remanente uniformemente entre los sin override
	per = flt((expected - sum_overrides) / len(non_override), 2)
	result["per_assignee"] = {u: flt(h, 2) for u, h in overrides.items()}
	for u in non_override:
		result["per_assignee"][u] = per
	return result


def _compute(employee: str, from_date, to_date) -> dict:
	"""Núcleo: distribuye por día la carga del `employee` en [from_date, to_date] + integridad."""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(frappe._("To Date no puede ser anterior a From Date."))

	# days_by_project: {project|None: {date: hours}}; days_by_task: {task: {date: hours}}; days (total)
	# se deriva sumando. Todos restringidos al rango [from_date, to_date].
	out = {
		"days": {},
		"days_by_project": {},
		"days_by_task": {},
		"issues": [],
		"unscheduled": [],
		"unmapped": [],
	}

	user = frappe.db.get_value("Employee", employee, "user_id")
	if not user:
		out["unmapped"].append({"employee": employee, "reason": "no_user_id"})
		return out
	active = _active_employees_for_user(user)
	if len(active) > 1:
		out["unmapped"].append({"user": user, "reason": "ambiguous_user_mapping", "employees": active})
		return out

	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "allocated_to": user, "status": "Open"},
		pluck="reference_name",
	)
	task_names = list(set(todos))
	if not task_names:
		return out

	tasks = frappe.get_all(
		"Task",
		filters={"name": ("in", task_names), "status": ("in", list(TASK_STATUSES_IN))},
		fields=["name", "project", "exp_start_date", "exp_end_date"],
	)
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)

	for task in tasks:
		res = get_planned_hours_per_assignee(task.name)
		if not res["consistent"]:
			out["issues"].append({"task": task.name, "project": task.project, "reasons": res["issues"]})
			continue
		hours = res["per_assignee"].get(user)
		if not hours:
			continue  # el user no es asignado efectivo o le tocan 0 horas

		if not (task.exp_start_date and task.exp_end_date):
			out["unscheduled"].append({"task": task.name, "project": task.project, "hours": flt(hours, 2)})
			continue
		s, e = getdate(task.exp_start_date), getdate(task.exp_end_date)
		if e < s:
			out["issues"].append({"task": task.name, "project": task.project, "reasons": ["invalid_dates"]})
			continue
		if not holiday_list:
			out["issues"].append({"task": task.name, "project": task.project, "reasons": ["no_holiday_list"]})
			continue
		try:
			rows = build_allocation_days(s, e, hours, holiday_list)
		except frappe.ValidationError:
			out["issues"].append({"task": task.name, "project": task.project, "reasons": ["no_working_days"]})
			continue
		per_project = out["days_by_project"].setdefault(task.project, {})
		per_task = out["days_by_task"].setdefault(task.name, {})
		for row in rows:
			if start <= row["date"] <= end:
				out["days"][row["date"]] = flt(out["days"].get(row["date"], 0) + row["hours"], 2)
				per_project[row["date"]] = flt(per_project.get(row["date"], 0) + row["hours"], 2)
				per_task[row["date"]] = flt(per_task.get(row["date"], 0) + row["hours"], 2)

	return out


def get_planned_load(employee: str, date=None) -> dict:
	"""Carga planificada del `employee` en `date`. {hours, issues, unscheduled, unmapped}. Interna."""
	on_date = getdate(date)
	computed = _compute(employee, on_date, on_date)
	return {
		"hours": flt(computed["days"].get(on_date, 0), 2),
		"issues": computed["issues"],
		"unscheduled": computed["unscheduled"],
		"unmapped": computed["unmapped"],
	}


def get_planned_load_range(employee: str, from_date, to_date) -> dict:
	"""Carga planificada por día en [from_date, to_date]. {days, issues, unscheduled, unmapped}. Interna."""
	computed = _compute(employee, from_date, to_date)
	return {
		"days": computed["days"],
		"issues": computed["issues"],
		"unscheduled": computed["unscheduled"],
		"unmapped": computed["unmapped"],
	}


def get_planned_load_by_project(employee: str, from_date, to_date) -> dict:
	"""Carga planificada desglosada por Project (infraestructura para el split P4 del reporte).

	{days_by_project: {project|None: {date: hours}}, issues, unscheduled, unmapped}. Interna, no
	whitelisted. El reporte clasifica cada Project en visible/confidencial según el observador y calcula
	el bucket confidencial como total - Sigma(visibles), sin enumerar proyectos confidenciales.
	"""
	computed = _compute(employee, from_date, to_date)
	return {
		"days_by_project": computed["days_by_project"],
		"issues": computed["issues"],
		"unscheduled": computed["unscheduled"],
		"unmapped": computed["unmapped"],
	}


def get_planned_load_by_task(employee: str, from_date, to_date) -> dict:
	"""Horas planificadas del `employee` por Task, restringidas al rango (misma distribución diaria).

	{hours_by_task: {task: horas_en_rango}, unscheduled: [{task, project, hours}], issues, unmapped}.
	`hours_by_task` solo incluye Tasks con fechas (repartidas por día dentro del rango); las Tasks sin
	fechas van en `unscheduled` con su total (no ubicables temporalmente). Interna, no whitelisted.
	"""
	computed = _compute(employee, from_date, to_date)
	hours_by_task = {task: flt(sum(days.values()), 2) for task, days in computed["days_by_task"].items()}
	return {
		"hours_by_task": hours_by_task,
		"unscheduled": computed["unscheduled"],
		"issues": computed["issues"],
		"unmapped": computed["unmapped"],
	}
