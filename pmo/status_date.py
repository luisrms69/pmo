# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Control a fecha de corte / Status Date (ADR-0006).

La Status Date (Data Date, PMI) es la fecha de corte del control del Project. Vive en el Custom Field
`Project.pmo_status_date` (D1) y en v0.7.0 solo puede ser **hoy o pasada** (D2): no se admite fecha futura
porque el Actual (Timesheet) solo existe hasta hoy y una fecha futura mezclaría planos.

Bloque 1: validación del campo (`validate_project_status_date`).
Bloque 2 (este módulo, motor): composición de los tres planos a la fecha de corte + indicadores D5.
Bloque 3 (reporte P4-safe): presentación.

Motor (`build_status_report`, whitelisted, P4):
- **Baseline** = snapshot de `get_effective_baseline(project, as_of=status_date)` (ADR-0004; D3). Si no hay
  baseline efectiva a la fecha, el plano se omite (`note`).
- **Current** = `build_snapshot(project)` (plan vigente HOY, evaluado contra la fecha; NO reconstruye el
  plan histórico).
- **Actual** = horas de Timesheet fechadas hasta la fecha (semántica ADR-0003, docstatus=1) +
  `Task.completed_on <= status_date` (proxy de completadas). Sin % histórico.
- **Indicadores D5**: (1) deslizamiento de fecha final Baseline vs Current (días); (2) tareas que debían
  estar terminadas a la fecha y no lo estaban; (3) Actual hours acumuladas; (4) conteos simples fiables.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from pmo.baseline import build_snapshot, get_effective_baseline


def validate_project_status_date(doc, method=None):
	"""ADR-0006 D2: `Project.pmo_status_date` no puede ser futura en v0.7.0. Vacío es válido (sin corte)."""
	status_date = doc.get("pmo_status_date")
	if not status_date:
		return
	if getdate(status_date) > getdate(today()):
		frappe.throw(
			_(
				"La Status Date ({0}) no puede ser una fecha futura: el control a fecha de corte solo admite hoy o una fecha pasada."
			).format(frappe.format(getdate(status_date), {"fieldtype": "Date"})),
			title=_("Status Date inválida"),
		)


# --- motor (Bloque 2) -------------------------------------------------------------


def _resolve_status_date(project: str, status_date=None):
	"""Resuelve la fecha de corte: parámetro o `Project.pmo_status_date`. Valida `<= today` (D2)."""
	if not status_date:
		status_date = frappe.db.get_value("Project", project, "pmo_status_date")
	if not status_date:
		frappe.throw(
			_(
				"Indica una Status Date (o fija `PMO Status Date` en el Project) para el control a fecha de corte."
			)
		)
	sd = getdate(status_date)
	if sd > getdate(today()):
		frappe.throw(_("La Status Date no puede ser una fecha futura (solo hoy o pasada)."))
	return sd


def _actual_hours_to_date(project: str, status_date) -> float:
	"""Σ `Timesheet Detail.hours` del Project hasta `status_date` (semántica ADR-0003: docstatus=1, `hours`).

	SQL estática y parametrizada (sin f-string; semgrep frappe-sql-format-injection). Corte por `from_time`
	dentro del día de la fecha (inclusive)."""
	rows = frappe.db.sql(
		"""select coalesce(sum(td.hours), 0)
			from `tabTimesheet Detail` td
			inner join `tabTimesheet` ts on td.parent = ts.name
			where ts.docstatus = 1
				and td.project = %(project)s
				and td.from_time <= timestamp(%(status_date)s, '24:00:00')""",
		{"project": project, "status_date": status_date},
	)
	return flt(rows[0][0], 2)


def _completed_on_map(task_names: list) -> dict:
	"""{task: completed_on} para las Tasks vivas indicadas (proxy de completitud a la fecha, D4)."""
	if not task_names:
		return {}
	rows = frappe.get_all(
		"Task",
		filters={"name": ("in", list(task_names))},
		fields=["name", "completed_on"],
	)
	return {r.name: r.completed_on for r in rows}


def compute_status(baseline_snapshot, current_snapshot, actual_hours, completed_on_map, status_date) -> dict:
	"""Composición pura de los indicadores D5 (sin acceso a BD; testeable en aislamiento).

	`baseline_snapshot` puede ser None (sin baseline vigente a la fecha)."""
	sd = getdate(status_date)

	# D5.1 — deslizamiento de fecha final Baseline vs Current (días).
	final_date_slip_days = None
	if baseline_snapshot:
		b_end = (baseline_snapshot.get("project") or {}).get("expected_end_date")
		c_end = (current_snapshot.get("project") or {}).get("expected_end_date")
		if b_end and c_end:
			final_date_slip_days = (getdate(c_end) - getdate(b_end)).days

	# D5.2 / D5.4 — tareas que debían estar terminadas a la fecha (baseline) y su completitud real.
	due_by_cutoff = 0
	completed_by_cutoff = 0
	overdue = []
	if baseline_snapshot:
		for t in baseline_snapshot.get("tasks", []):
			if t.get("is_group"):
				continue  # las summary no son trabajo entregable
			b_end = t.get("exp_end_date")
			if not b_end or getdate(b_end) > sd:
				continue  # no debía estar terminada a la fecha
			due_by_cutoff += 1
			done_on = completed_on_map.get(t["name"])
			if done_on and getdate(done_on) <= sd:
				completed_by_cutoff += 1
			else:
				overdue.append(
					{"name": t["name"], "subject": t.get("subject"), "baseline_exp_end_date": b_end}
				)

	return {
		"final_date_slip_days": final_date_slip_days,
		"tasks_overdue_at_cutoff": {"count": len(overdue), "tasks": overdue},
		"actual_hours_to_date": flt(actual_hours, 2),
		"counts": {
			"baseline_due_by_cutoff": due_by_cutoff,
			"completed_by_cutoff": completed_by_cutoff,
		},
	}


@frappe.whitelist()
def build_status_report(project: str, status_date: str | None = None) -> dict:
	"""Reporte de control a fecha de corte (ADR-0006). P4: exige READ sobre el Project.

	Compone Baseline (vigente a la fecha) + Current (plan de hoy) + Actual (Timesheet a la fecha) e indicadores
	D5. Si no hay baseline efectiva a la fecha, `baseline` es None con `note`."""
	if not frappe.db.exists("Project", project):
		frappe.throw(_("El Project {0} no existe.").format(project))
	frappe.has_permission("Project", ptype="read", doc=project, throw=True)  # P4

	sd = _resolve_status_date(project, status_date)

	baseline_name = get_effective_baseline(project, as_of=sd)
	baseline_snapshot = None
	baseline_meta = None
	note = None
	if baseline_name:
		snap = frappe.db.get_value("PMO Project Baseline", baseline_name, "snapshot")
		baseline_snapshot = frappe.parse_json(snap) if snap else None
		baseline_meta = {
			"name": baseline_name,
			"expected_end_date": (baseline_snapshot.get("project") or {}).get("expected_end_date")
			if baseline_snapshot
			else None,
		}
	else:
		note = _("Sin línea base vigente a la fecha de corte: se muestran Current y Actual.")

	current_snapshot = build_snapshot(project)
	actual_hours = _actual_hours_to_date(project, sd)

	completed_map = {}
	if baseline_snapshot:
		names = [t["name"] for t in baseline_snapshot.get("tasks", []) if not t.get("is_group")]
		completed_map = _completed_on_map(names)

	indicators = compute_status(baseline_snapshot, current_snapshot, actual_hours, completed_map, sd)

	return {
		"project": project,
		"status_date": str(sd),
		"baseline": baseline_meta,
		"current": {"expected_end_date": (current_snapshot.get("project") or {}).get("expected_end_date")},
		"note": note,
		"indicators": indicators,
	}
