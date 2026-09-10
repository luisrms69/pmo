# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Portfolio — visión de salud multi-proyecto (ronda product-readiness). Script Report P4-safe.

Responde "¿cómo va cada proyecto y cuáles debo vigilar?" en una sola vista. **No** introduce motor nuevo:
- Salud de cronograma por proyecto = `pmo.status_date.build_status_report` (ADR-0006/0009), que ya impone
  P4 (READ del Project) y compone Baseline/forecast/desviaciones.
- Esfuerzo por proyecto = suma de `Task.expected_time` vs `Task.actual_time` de Tasks hoja (misma semántica
  nativa de ADR-0008 Planificado vs Real, sin duplicar el reporte por Task).

P4: solo se listan los Projects **visibles** al observador (owner / DocShare-read / acceso ejecutivo),
reutilizando `pmo.permissions`. Cada fila trae una **salud** (En plan / En riesgo / Desviado) derivada de
las mismas señales que el Status Report; el detalle por proyecto sigue en `PMO Status Report` / `PMO Planned
vs Actual`.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from pmo.permissions import _is_global_reader, _member_projects_subquery
from pmo.status_date import build_status_report

HEALTH_ON_TRACK = "En plan"
HEALTH_AT_RISK = "En riesgo"
HEALTH_OFF_TRACK = "Desviado"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = []
	for project in _visible_projects(frappe.session.user, filters):
		try:
			data.append(_project_row(project))
		except frappe.PermissionError:
			# P4 autoritativa: build_status_report exige READ; un proyecto no legible se omite (no rompe
			# el dashboard). El pre-filtro ya limita el alcance; esto es defensa en profundidad.
			continue
	return _columns(), data, None, None, _summary(data)


def _visible_projects(user, filters):
	"""Projects visibles al observador (P4). Executive/Administrator → todos; normal → owner + DocShare-read.

	Excluye Cancelled siempre y Completed salvo `include_completed`. `company` filtra si se indica."""
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company

	if _is_global_reader(user):
		names = frappe.get_all("Project", filters=conditions, pluck="name")
	else:
		visible = {r[0] for r in frappe.db.sql(_member_projects_subquery(user))}
		names = [
			p.name
			for p in frappe.get_all("Project", filters=conditions, fields=["name"])
			if p.name in visible
		]

	rows = []
	for name in names:
		status = frappe.db.get_value("Project", name, "status")
		if status == "Cancelled":
			continue
		if status == "Completed" and not filters.get("include_completed"):
			continue
		rows.append(name)
	return rows


def _project_row(project):
	meta = frappe.db.get_value(
		"Project", project, ["project_name", "status", "pmo_status_date"], as_dict=True
	)
	# build_status_report es whitelisted (type-check): status_date debe ser str. Usa la del Project o hoy.
	sd = meta.get("pmo_status_date")
	status_date = str(sd) if sd else today()
	report = build_status_report(project, status_date)  # reusa el motor + P4
	ind = report["indicators"]

	planned, actual = _effort_totals(project)
	slip_baseline = ind.get("final_date_slip_days")
	slip_committed = ind.get("slip_vs_committed_days")
	overdue = ind["tasks_overdue_at_cutoff"]["count"]
	exceeds = ind.get("forecast_exceeds_commitment", {}).get("count", 0)
	has_baseline = bool(report.get("baseline"))

	return {
		"project": project,
		"project_name": meta.get("project_name"),
		"status": meta.get("status"),
		"forecast_end": (report.get("current") or {}).get("expected_end_date"),
		"slip_baseline": slip_baseline,
		"slip_committed": slip_committed,
		"overdue": overdue,
		"forecast_exceeds": exceeds,
		"planned_hours": planned,
		"actual_hours": actual,
		"pct_consumed": flt(actual / planned * 100, 1) if planned > 0 else None,
		"health": _health(slip_baseline, slip_committed, overdue, exceeds),
		"has_baseline": has_baseline,  # para el resumen (sin columna propia)
	}


def _effort_totals(project):
	"""Σ expected_time (Planned) y actual_time (Actual) de Tasks hoja (no is_group). Semántica ADR-0008."""
	tasks = frappe.get_all(
		"Task",
		filters={"project": project, "is_group": 0},
		fields=["expected_time", "actual_time"],
	)
	planned = flt(sum(flt(t.expected_time) for t in tasks), 2)
	actual = flt(sum(flt(t.actual_time) for t in tasks), 2)
	return planned, actual


def _health(slip_baseline, slip_committed, overdue, exceeds):
	"""Semáforo derivado de las mismas señales del Status Report. Positivo = peor."""
	if (slip_committed or 0) > 0 or overdue > 0 or exceeds > 0:
		return HEALTH_OFF_TRACK
	if (slip_baseline or 0) > 0:
		return HEALTH_AT_RISK
	return HEALTH_ON_TRACK


def _columns():
	def col(field, label, ftype="Data", width=110, options=None):
		c = {"fieldname": field, "label": _(label), "fieldtype": ftype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("project", "Project", "Link", 150, options="Project"),
		col("project_name", "Nombre", "Data", 200),
		col("status", "Estado", "Data", 90),
		col("health", "Salud", "Data", 100),
		col("forecast_end", "Fin (forecast)", "Date", 120),
		col("slip_baseline", "Slip vs Baseline (d)", "Int", 140),
		col("slip_committed", "Slip vs compromiso (d)", "Int", 150),
		col("overdue", "Vencidas", "Int", 90),
		col("forecast_exceeds", "Forecast > compromiso", "Int", 150),
		col("planned_hours", "Planned (h)", "Float", 100),
		col("actual_hours", "Actual (h)", "Float", 100),
		col("pct_consumed", "% Consumido", "Float", 110),
	]


def _summary(data):
	if not data:
		return []
	off = sum(1 for r in data if r["health"] == HEALTH_OFF_TRACK)
	risk = sum(1 for r in data if r["health"] == HEALTH_AT_RISK)
	no_baseline = sum(1 for r in data if not r["has_baseline"])
	return [
		{"label": _("Proyectos"), "value": len(data), "datatype": "Int"},
		{
			"label": _("Desviados"),
			"value": off,
			"datatype": "Int",
			"indicator": "Red" if off else "Green",
		},
		{
			"label": _("En riesgo"),
			"value": risk,
			"datatype": "Int",
			"indicator": "Orange" if risk else "Green",
		},
		{
			"label": _("Sin línea base"),
			"value": no_baseline,
			"datatype": "Int",
			"indicator": "Orange" if no_baseline else "Green",
		},
	]
