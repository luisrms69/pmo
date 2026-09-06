# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Engine de Baselines (ADR-0004 D5/D6). Construye el snapshot canonico inmutable de un Project, su hash
determinista, el preflight ligero y la derivacion de la baseline vigente as-of.

NO persiste nada: funciones puras de lectura reutilizables por el controlador `PMO Project Baseline` (que
las llama en `before_submit`) y por tests. La identidad Project/Task del snapshot se protege via los
permisos del propio DocType (ADR-0004 D7), no aqui.
"""

import hashlib
import json

import frappe
from frappe.utils import flt, getdate, today

from pmo.planned_load import get_planned_hours_per_assignee

SNAPSHOT_SCHEMA_VERSION = 1


# --- snapshot canonico -----------------------------------------------------------------


def _iso(d):
	return getdate(d).isoformat() if d else None


def _task_assignments(task: str) -> list:
	"""Assignments congelados por Task: {user, employee, override_hours, effective_hours} (ADR-0004 D5).

	`override_hours` = `ToDo.pmo_planned_hours` explicito (o None). `effective_hours` = horas efectivas de
	la regla PMO (reparto de `Task.expected_time`) al momento de congelar; None si el reparto es
	inconsistente (lo detecta el preflight y bloquea).
	"""
	load = get_planned_hours_per_assignee(task)
	per = load["per_assignee"]  # efectivas (vacio si inconsistente)
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "reference_name": task, "status": "Open"},
		fields=["allocated_to", "pmo_planned_hours"],
	)
	rows, seen = [], set()
	for td in todos:
		u = td.allocated_to
		if not u or u in seen:
			continue
		seen.add(u)
		emp = frappe.db.get_value("Employee", {"user_id": u, "status": "Active"}, "name")
		# Coherente con el motor (planned_load): pmo_planned_hours > 0 es override; <= 0/vacio = sin override.
		override = flt(td.pmo_planned_hours)
		rows.append(
			{
				"user": u,
				"employee": emp or None,
				"override_hours": flt(override, 2) if override > 0 else None,
				"effective_hours": flt(per[u], 2) if per.get(u) is not None else None,
			}
		)
	rows.sort(key=lambda r: r["user"])
	return rows


def build_snapshot(project: str) -> dict:
	"""Representacion canonica e inmutable del plan del Project (ADR-0004 D5). WBS por identidad estable
	(`name` + `parent_task` + `wbs_order` derivado del orden nativo `lft`), NO por `lft`/`rgt` directos.
	"""
	proj = frappe.db.get_value(
		"Project",
		project,
		["name", "expected_start_date", "expected_end_date", "status"],
		as_dict=True,
	)

	tasks = frappe.get_all(
		"Task",
		filters={"project": project},
		fields=[
			"name",
			"subject",
			"description",
			"parent_task",
			"is_group",
			"is_milestone",
			"exp_start_date",
			"exp_end_date",
			"expected_time",
			"duration",
			"status",
			"lft",
		],
		order_by="lft asc",
	)

	# wbs_order: ordinal estable por grupo de hermanos, derivado del orden nativo (lft) al congelar.
	sibling_counter: dict = {}
	rows = []
	for t in tasks:
		parent_key = t.parent_task or ""
		sibling_counter[parent_key] = sibling_counter.get(parent_key, 0) + 1
		deps = sorted(
			d for d in frappe.get_all("Task Depends On", filters={"parent": t.name}, pluck="task") if d
		)
		rows.append(
			{
				"name": t.name,
				"subject": t.subject,
				"description": t.description or "",
				"parent_task": t.parent_task or None,
				"wbs_order": sibling_counter[parent_key],
				"is_group": int(t.is_group or 0),
				"is_milestone": int(t.is_milestone or 0),
				"exp_start_date": _iso(t.exp_start_date),
				"exp_end_date": _iso(t.exp_end_date),
				"expected_time": flt(t.expected_time, 2),
				"duration": int(t.duration or 0),
				"status": t.status,
				"depends_on": deps,
				"assignments": _task_assignments(t.name),
			}
		)
	rows.sort(key=lambda r: r["name"])  # orden determinista para el hash

	return {
		"snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
		"project": {
			"name": proj.name,
			"expected_start_date": _iso(proj.expected_start_date),
			"expected_end_date": _iso(proj.expected_end_date),
			"status": proj.status,
		},
		"tasks": rows,
	}


def canonical_json(snapshot: dict) -> str:
	"""Serializacion determinista (claves ordenadas, sin espacios) para el hash reproducible."""
	return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_hash(snapshot: dict) -> str:
	return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


# --- preflight ligero (ADR-0004 D6) ----------------------------------------------------


def run_preflight(project: str) -> dict:
	"""Revision ligera previa a congelar. `warnings` no bloquean; `blocking` impide un snapshot coherente
	(reparto de horas inconsistente que impide determinar `effective_hours`).
	"""
	warnings, blocking = [], []
	tasks = frappe.get_all(
		"Task",
		filters={"project": project},
		fields=["name", "is_group", "expected_time", "exp_start_date", "exp_end_date"],
	)
	for t in tasks:
		if not t.is_group and not (t.exp_start_date and t.exp_end_date):
			warnings.append({"code": "leaf_no_dates", "task": t.name})
		if t.is_group and flt(t.expected_time) > 0:
			warnings.append({"code": "group_has_effort", "task": t.name})
		if t.is_group:
			if frappe.db.exists(
				"ToDo", {"reference_type": "Task", "reference_name": t.name, "status": "Open"}
			):
				warnings.append({"code": "group_has_assignments", "task": t.name})
			# summary dates desactualizadas vs envelope de hijas
			children = frappe.get_all(
				"Task",
				filters={"parent_task": t.name},
				fields=["exp_start_date", "exp_end_date"],
			)
			starts = [c.exp_start_date for c in children if c.exp_start_date]
			ends = [c.exp_end_date for c in children if c.exp_end_date]
			if starts and ends:
				env_start, env_end = min(starts), max(ends)
				if (t.exp_start_date and getdate(t.exp_start_date) != getdate(env_start)) or (
					t.exp_end_date and getdate(t.exp_end_date) != getdate(env_end)
				):
					warnings.append({"code": "summary_dates_stale", "task": t.name})
		load = get_planned_hours_per_assignee(t.name)
		if load["issues"]:
			warnings.append({"code": "planned_issue", "task": t.name, "issues": load["issues"]})
		if not load["consistent"]:
			blocking.append({"code": "inconsistent_distribution", "task": t.name})
		for u in load["unmapped"]:
			warnings.append({"code": "assignment_no_employee", "task": t.name, "user": u})
	return {"warnings": warnings, "blocking": blocking}


# --- baseline vigente as-of (ADR-0004 D4, Opcion B: sin future-effective) ---------------


def get_effective_baseline(project: str, as_of=None) -> str | None:
	"""Baseline vigente del Project a una fecha: la Submitted (docstatus=1) no cancelada con mayor
	`effective_date <= as_of` (cabeza de la cadena; sin sucesores futuros por Opcion B).
	"""
	as_of = getdate(as_of or today())
	rows = frappe.get_all(
		"PMO Project Baseline",
		filters={"project": project, "docstatus": 1, "effective_date": ["<=", as_of]},
		fields=["name"],
		order_by="effective_date desc, creation desc",
		limit=1,
	)
	return rows[0].name if rows else None
