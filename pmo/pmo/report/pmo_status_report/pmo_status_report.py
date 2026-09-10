# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Status Report (ADR-0006 + ADR-0009) — control a fecha de corte / Status Date. Script Report P4-safe.

Reutiliza `pmo.status_date.build_status_report()` (NO otro engine): esa función impone P4 (READ sobre el
Project) y valida la Status Date (`<= today`) → el reporte es P4-safe por delegación (los Script Report no
aplican `permission_query_conditions`, así que la P4 se valida dentro de `execute`, como el resto de reports
P4 de la app).

ADR-0009 amplía la presentación: el detalle es una **tabla única por Task** (con baseline) que junta
fin baseline, fin forecast (plan vigente), slip, fecha comprometida y si estaba vencida al corte; el resumen
agrega el **forecast vigente** (`expected_end_date`, sin inventar una segunda fecha) y sus desviaciones vs
Baseline y vs compromiso. El forecast es el plan vivo de ERPNext, no una predicción calculada por PMO.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from pmo.status_date import build_status_report


def execute(filters=None):
	filters = frappe._dict(filters or {})
	project = filters.get("project")
	if not project:
		frappe.throw(_("Selecciona un Project."))

	# P4 + validación de la Status Date + composición: todo dentro de build_status_report (lanza si no).
	report = build_status_report(project, filters.get("status_date"))
	return _columns(), _rows(report), _message(report), None, _summary(report)


def _columns():
	def col(field, label, fieldtype="Data", width=200, options=None):
		c = {"fieldname": field, "label": _(label), "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("name", "Tarea", "Link", 180, options="Task"),
		col("subject", "Descripción", "Data", 280),
		col("baseline_exp_end_date", "Fin (Baseline)", "Date", 120),
		col("current_exp_end_date", "Fin (Forecast)", "Date", 120),
		col("slip_days", "Slip (días)", "Int", 100),
		col("pmo_deadline", "Fecha comprometida", "Date", 140),
		col("overdue", "Vencida al corte", "Data", 120),
	]


def _rows(report):
	# ADR-0009: tabla única por Task (con baseline) — baseline vs forecast, slip, deadline y marca de vencida.
	# Orden por slip descendente (mayor desviación primero); las sin forecast (slip None) al final.
	rows = report["indicators"].get("tasks_vs_baseline", [])
	rows = sorted(rows, key=lambda r: (r.get("slip_days") is None, -(r.get("slip_days") or 0)))
	return [
		{
			"name": r["name"],
			"subject": r.get("subject"),
			"baseline_exp_end_date": r.get("baseline_exp_end_date"),
			"current_exp_end_date": r.get("current_exp_end_date"),
			"slip_days": r.get("slip_days"),
			"pmo_deadline": r.get("pmo_deadline"),
			"overdue": _("Sí") if r.get("overdue_at_status_date") else "",
		}
		for r in rows
	]


def _summary(report):
	ind = report["indicators"]
	baseline = report.get("baseline")
	slip = ind.get("final_date_slip_days")
	slip_committed = ind.get("slip_vs_committed_days")
	exceeds = ind.get("forecast_exceeds_commitment", {}).get("count", 0)
	overdue = ind["tasks_overdue_at_cutoff"]["count"]
	counts = ind["counts"]
	forecast_end = (report.get("current") or {}).get("expected_end_date")

	summary = [
		{"label": _("Fecha de corte"), "value": report["status_date"], "datatype": "Data"},
		{
			"label": _("Línea base vigente"),
			"value": baseline["name"] if baseline else _("— (sin baseline a la fecha)"),
			"datatype": "Data",
			"indicator": "Blue" if baseline else "Gray",
		},
		# ADR-0009 D1: el forecast vigente es el plan vivo de ERPNext, no una predicción calculada por PMO.
		{
			"label": _("Forecast vigente (plan): fin"),
			"value": forecast_end if forecast_end else _("N/D"),
			"datatype": "Data",
			"indicator": "Blue",
		},
		{
			"label": _("Deslizamiento vs Baseline (días)"),
			"value": slip if slip is not None else _("N/D"),
			"datatype": "Data",
			"indicator": "Red" if (slip or 0) > 0 else "Green",
		},
		{
			"label": _("Deslizamiento vs compromiso (días)"),
			"value": slip_committed if slip_committed is not None else _("N/D"),
			"datatype": "Data",
			"indicator": "Red" if (slip_committed or 0) > 0 else "Green",
		},
		{
			"label": _("Tareas: forecast excede compromiso"),
			"value": exceeds,
			"datatype": "Int",
			"indicator": "Orange" if exceeds else "Green",
		},
		{
			"label": _("Tareas vencidas no terminadas"),
			"value": overdue,
			"datatype": "Int",
			"indicator": "Orange" if overdue else "Green",
		},
		{
			"label": _("Horas reales a la fecha"),
			"value": flt(ind["actual_hours_to_date"], 2),
			"datatype": "Float",
		},
		{
			"label": _("Completadas / previstas a la fecha"),
			"value": f"{counts['completed_by_cutoff']} / {counts['baseline_due_by_cutoff']}",
			"datatype": "Data",
		},
	]
	return summary


def _message(report):
	parts = []
	if report.get("note"):
		parts.append(report["note"])
	# Aclaración conceptual (ADR-0006): Current NO reconstruye el plan histórico.
	parts.append(
		_(
			"«Current» es el plan vigente hoy evaluado contra la fecha de corte, no una reconstrucción del "
			"plan que existía en esa fecha. El Actual proviene de Timesheet fechado; la completitud usa "
			"«completed_on» como proxy."
		)
	)
	base = report.get("baseline")
	if base and base.get("expected_end_date"):
		parts.append(
			_("Fin planeado (Baseline): {0} · Fin planeado (Current): {1}.").format(
				formatdate(base["expected_end_date"]),
				formatdate(report["current"]["expected_end_date"])
				if report["current"].get("expected_end_date")
				else _("N/D"),
			)
		)
	return "<br>".join(parts)
