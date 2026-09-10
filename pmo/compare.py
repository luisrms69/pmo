# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Comparator Baseline ↔ Baseline (ADR-0005 D11).

Explica qué cambió entre dos `PMO Project Baseline` del mismo Project operando **solo sobre los snapshots
v1 ya almacenados** (no reconstruye ni consulta el Current Plan). Es una diferencia **entre baselines**:
no atribuye el diff a un único Change Request (varios CR pueden consolidarse en una misma `baseline_after`).

P4: el endpoint whitelisted verifica lectura sobre **ambas** baselines (= `is_project_visible`) y exige
mismo Project → sin fuga cross-project.
"""

import json

import frappe
from frappe import _

# Campos de Task comparados (identidad de Task = `name` del snapshot v1).
_TASK_FIELDS = (
	"exp_start_date",
	"exp_end_date",
	"expected_time",
	"status",
	"parent_task",
	"wbs_order",
)
# Campos de Project comparados (los que viven en el snapshot v1).
_PROJECT_FIELDS = ("expected_start_date", "expected_end_date", "status")
# Campos de assignment comparados por usuario.
_ASSIGNMENT_FIELDS = ("override_hours", "effective_hours")


def _index(snapshot: dict) -> dict:
	return {t["name"]: t for t in (snapshot.get("tasks") or [])}


def _task_brief(t: dict) -> dict:
	"""Resumen legible de una Task para las secciones added/removed."""
	return {
		"name": t.get("name"),
		"subject": t.get("subject"),
		"parent_task": t.get("parent_task"),
		"wbs_order": t.get("wbs_order"),
		"exp_start_date": t.get("exp_start_date"),
		"exp_end_date": t.get("exp_end_date"),
		"expected_time": t.get("expected_time"),
		"status": t.get("status"),
	}


def _assignment_diff(before: list, after: list) -> dict:
	b = {a["user"]: a for a in (before or [])}
	a = {a["user"]: a for a in (after or [])}
	added = [
		{"user": u, "employee": a[u].get("employee"), "effective_hours": a[u].get("effective_hours")}
		for u in sorted(set(a) - set(b))
	]
	removed = [{"user": u} for u in sorted(set(b) - set(a))]
	changed = []
	for u in sorted(set(a) & set(b)):
		deltas = {
			f: {"from": b[u].get(f), "to": a[u].get(f)}
			for f in _ASSIGNMENT_FIELDS
			if b[u].get(f) != a[u].get(f)
		}
		if deltas:
			changed.append({"user": u, "changes": deltas})
	return {"added": added, "removed": removed, "changed": changed}


def _has_assignment_change(adiff: dict) -> bool:
	return bool(adiff["added"] or adiff["removed"] or adiff["changed"])


def compare_snapshots(before: dict, after: dict) -> dict:
	"""Diff determinista entre dos snapshots v1. Función pura (sin BD)."""
	b_tasks, a_tasks = _index(before), _index(after)

	tasks_added = [_task_brief(a_tasks[n]) for n in sorted(set(a_tasks) - set(b_tasks))]
	tasks_removed = [_task_brief(b_tasks[n]) for n in sorted(set(b_tasks) - set(a_tasks))]

	tasks_changed = []
	for n in sorted(set(a_tasks) & set(b_tasks)):
		bt, at = b_tasks[n], a_tasks[n]
		field_changes = {
			f: {"from": bt.get(f), "to": at.get(f)} for f in _TASK_FIELDS if bt.get(f) != at.get(f)
		}
		adiff = _assignment_diff(bt.get("assignments"), at.get("assignments"))
		if field_changes or _has_assignment_change(adiff):
			tasks_changed.append(
				{
					"name": n,
					"subject": at.get("subject") or bt.get("subject"),
					"fields": field_changes,
					"assignments": adiff,
				}
			)

	bp, ap = before.get("project") or {}, after.get("project") or {}
	project_changes = {
		f: {"from": bp.get(f), "to": ap.get(f)} for f in _PROJECT_FIELDS if bp.get(f) != ap.get(f)
	}

	return {
		"project_changes": project_changes,
		"tasks_added": tasks_added,
		"tasks_removed": tasks_removed,
		"tasks_changed": tasks_changed,
		"has_changes": bool(project_changes or tasks_added or tasks_removed or tasks_changed),
	}


def _load_snapshot(doc) -> dict:
	if not doc.snapshot:
		frappe.throw(
			_("Baseline {0} has no snapshot (it is not frozen/Submitted).").format(frappe.bold(doc.name))
		)
	return json.loads(doc.snapshot)


@frappe.whitelist()
def compare_baselines(baseline_before: str, baseline_after: str) -> dict:
	"""Compara dos `PMO Project Baseline` (before → after). Verifica lectura P4 sobre AMBAS y exige mismo
	Project. Devuelve el diff de `compare_snapshots` + metadatos de encabezado. El orden de argumentos define
	la dirección (from = before, to = after); no se reordena automáticamente."""
	a = frappe.get_doc("PMO Project Baseline", baseline_before)
	b = frappe.get_doc("PMO Project Baseline", baseline_after)
	a.check_permission("read")
	b.check_permission("read")
	if a.project != b.project:
		frappe.throw(_("Only baselines from the same Project can be compared."))

	result = compare_snapshots(_load_snapshot(a), _load_snapshot(b))
	result["meta"] = {
		"project": a.project,
		"before": {"name": a.name, "revision": a.revision, "effective_date": str(a.effective_date or "")},
		"after": {"name": b.name, "revision": b.revision, "effective_date": str(b.effective_date or "")},
	}
	return result
