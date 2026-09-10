# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Contexto para el Print Format `PMO Project Status` (salida presentable a stakeholder).

Expuesto como **método Jinja** (ver hooks `jinja.methods`): el Print Format lo llama una vez con el
Project y arma resumen + evaluación de tareas. **No** duplica motor: reutiliza
`pmo.status_date.build_status_report` (ADR-0006/0009, que ya impone P4 READ del Project) y los helpers de
salud/esfuerzo del reporte de portafolio. La tabla lista SOLO tareas **relevantes** para evaluación
(vencidas al corte / slip != 0 / forecast que excede su `pmo_deadline` / hitos) e informa cuántas se
omiten, para no ocultar información.
"""

import frappe
from frappe.utils import flt, getdate, today

from pmo.pmo.report.pmo_portfolio.pmo_portfolio import _effort_totals, _health
from pmo.status_date import build_status_report

_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")


def pmo_project_status(project: str, status_date=None) -> dict:
	"""Contexto PMO del proyecto para el Print Format. P4 lo impone `build_status_report`."""
	sd = str(status_date) if status_date else _resolve_status_date(project)
	report = build_status_report(project, sd)
	ind = report["indicators"]

	planned, actual = _effort_totals(project)
	slip_baseline = ind.get("final_date_slip_days")
	slip_committed = ind.get("slip_vs_committed_days")
	overdue = ind["tasks_overdue_at_cutoff"]["count"]
	exceeds = ind.get("forecast_exceeds_commitment", {}).get("count", 0)

	rows = _annotate(project, ind.get("tasks_vs_baseline", []))
	relevant = _relevant(rows)
	relevant.sort(key=lambda r: (r["slip_days"] is None, -(r["slip_days"] or 0)))
	milestones = [r for r in rows if r["is_milestone"]]

	counts = _status_counts(project)
	counts["overdue_at_cutoff"] = overdue

	return {
		"status_date": report["status_date"],
		"baseline": report.get("baseline"),  # {name, expected_end_date} o None
		"forecast_end": (report.get("current") or {}).get("expected_end_date"),
		"committed_end": report.get("committed_end_date"),
		"slip_baseline": slip_baseline,
		"slip_committed": slip_committed,
		"overdue": overdue,
		"forecast_exceeds": exceeds,
		"planned_hours": planned,
		"actual_hours": actual,
		"pct_consumed": flt(actual / planned * 100, 1) if planned > 0 else None,
		"health": _health(slip_baseline, slip_committed, overdue, exceeds),
		"counts": counts,
		"milestones": milestones,
		"relevant_tasks": relevant,
		"omitted_tasks": len(rows) - len(relevant),  # con baseline pero sin desviación → no listadas
		"total_baseline_tasks": len(rows),
	}


def _resolve_status_date(project: str) -> str:
	sd = frappe.db.get_value("Project", project, "pmo_status_date")
	return str(sd) if sd else today()


def _annotate(project: str, rows: list) -> list:
	"""Agrega `is_milestone` y `exceeds_deadline` (forecast > pmo_deadline) a cada fila de la tabla ADR-0009."""
	names = [r["name"] for r in rows]
	milestone = {}
	if names:
		milestone = {
			t.name: int(t.is_milestone or 0)
			for t in frappe.get_all("Task", filters={"name": ("in", names)}, fields=["name", "is_milestone"])
		}
	for r in rows:
		r["is_milestone"] = milestone.get(r["name"], 0)
		fc, dl = r.get("current_exp_end_date"), r.get("pmo_deadline")
		r["exceeds_deadline"] = bool(fc and dl and getdate(fc) > getdate(dl))
	return rows


def _relevant(rows: list) -> list:
	"""Relevantes para evaluación: vencida al corte, slip != 0, forecast excede deadline, o hito."""
	out = []
	for r in rows:
		slip = r.get("slip_days")
		if (
			r.get("overdue_at_status_date")
			or (slip is not None and slip != 0)
			or r.get("exceeds_deadline")
			or r.get("is_milestone")
		):
			out.append(r)
	return out


def _status_counts(project: str) -> dict:
	"""Conteos compactos de Tasks hoja por macro-estado (para la línea de resumen)."""
	tasks = frappe.get_all("Task", filters={"project": project, "is_group": 0}, fields=["status"])
	total = len(tasks)
	completed = sum(1 for t in tasks if t.status == "Completed")
	active = sum(1 for t in tasks if t.status in _ACTIVE_STATUSES)
	return {"total": total, "completed": completed, "active": active}
