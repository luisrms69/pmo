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
from frappe import N_
from frappe.utils import flt, getdate, today

from pmo.pmo.report.pmo_portfolio.pmo_portfolio import HEALTH_LABELS, _effort_totals, _health
from pmo.status_date import build_status_report

_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")

# Strings visibles del Print Format `PMO Project Status`. El flujo gettext NO extrae plantillas de Print
# Format (no hay extractor de print_format en babel_extractors.csv), así que se marcan aquí con N_() (no-op)
# para que entren al POT; la plantilla las traduce en render con {{ _("...") }} usando el catálogo es.po.
_PRINT_FORMAT_STRINGS = (
	N_("Cutoff date (Status Date):"),
	N_("Executive summary"),
	N_("Progress"),
	N_("Baseline"),
	N_("no baseline"),
	N_("Slip vs Baseline:"),
	N_("Current forecast (plan)"),
	N_("Project planned end (ERPNext)"),
	N_("Committed date"),
	N_("Slip vs commitment:"),
	N_("Overdue tasks at cutoff"),
	N_("Forecast exceeds commitment"),
	N_("Effort (hours)"),
	N_("% consumed:"),
	N_("Tasks:"),
	N_("completed"),
	N_("active"),
	N_("overdue at cutoff"),
	N_("Milestones"),
	N_("Milestone"),
	N_("End (Baseline)"),
	N_("End (Forecast)"),
	N_("Slip"),
	N_("Overdue at cutoff"),
	N_("Yes"),
	N_("Tasks to evaluate (with deviation)"),
	N_("Task"),
	N_("Commitment"),
	N_("Overdue"),
	N_("No tasks with relevant deviation at the cutoff date."),
	N_("{0} task(s) with baseline but without relevant deviation are not listed (of {1} with baseline)."),
	N_("Schedule (Gantt)"),
	N_("No dated tasks to draw a schedule."),
	N_("Milestone"),
)


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

	health_key = _health(slip_baseline, slip_committed, overdue, exceeds)
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
		"health_key": health_key,  # valor interno estable (color/lógica)
		"health": HEALTH_LABELS[health_key],  # etiqueta fuente (inglés); se traduce en el template con _()
		"counts": counts,
		"milestones": milestones,
		"relevant_tasks": relevant,
		"omitted_tasks": len(rows) - len(relevant),  # con baseline pero sin desviación → no listadas
		"total_baseline_tasks": len(rows),
		"gantt": _gantt(project),  # cronograma estático para el Print Format (barras en Jinja)
	}


def _gantt(project: str) -> dict:
	"""Cronograma del proyecto para el Gantt estático del Print Format. Reutiliza las Tasks reales
	(orden WBS por `lft`), sin motor nuevo. P4: el READ del Project ya lo impuso `build_status_report`;
	se listan las Tasks del proyecto con `frappe.get_list` (respeta la pqc de Task, sin `get_all`).
	Precomputa offset/ancho en % relativo al rango [min_start, max_end] para dibujar barras en HTML/CSS
	compatible con wkhtmltopdf (sin JS)."""
	tasks = frappe.get_list(
		"Task",
		filters={"project": project},
		fields=[
			"name",
			"subject",
			"exp_start_date",
			"exp_end_date",
			"progress",
			"is_group",
			"is_milestone",
			"lft",
			"parent_task",
		],
		order_by="lft asc",
		limit=0,
	)
	# profundidad WBS por cadena de parent_task (para indentación)
	parent = {t.name: t.parent_task for t in tasks}

	def depth(name, _guard=0):
		p = parent.get(name)
		return 0 if not p or _guard > 50 else 1 + depth(p, _guard + 1)

	starts = [getdate(t.exp_start_date) for t in tasks if t.exp_start_date]
	ends = [getdate(t.exp_end_date) for t in tasks if t.exp_end_date]
	if not starts or not ends:
		return {"tasks": [], "min_start": None, "max_end": None}
	min_start, max_end = min(starts), max(ends)
	span = max((max_end - min_start).days, 1)

	out = []
	for t in tasks:
		row = {
			"name": t.name,
			"subject": t.subject or t.name,
			"depth": depth(t.name),
			"is_group": int(t.is_group or 0),
			"is_milestone": int(t.is_milestone or 0),
			"progress": int(flt(t.progress)),
			"start": str(t.exp_start_date)[:10] if t.exp_start_date else None,
			"end": str(t.exp_end_date)[:10] if t.exp_end_date else None,
			"offset_pct": None,
			"width_pct": None,
		}
		if t.exp_start_date and t.exp_end_date:
			s, e = getdate(t.exp_start_date), getdate(t.exp_end_date)
			row["offset_pct"] = round((s - min_start).days / span * 100, 2)
			row["width_pct"] = round(max(((e - s).days + 1) / span * 100, 1.5), 2)
		out.append(row)
	return {"tasks": out, "min_start": str(min_start), "max_end": str(max_end)}


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
