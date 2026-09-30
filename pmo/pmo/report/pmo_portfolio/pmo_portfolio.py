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
from frappe import N_, _
from frappe.utils import flt, today

from pmo.financial_health import FIN_STATE_LABELS, get_project_financial_health
from pmo.governance import governance_flags

# Salud: única fuente de verdad en pmo.health (claves + algoritmo, ADR-0011 D2). Se re-exporta aquí para
# los consumidores que ya importan estos símbolos desde este módulo (print_status, dashboard).
from pmo.health import (  # re-export estable para print_status/dashboard
	HEALTH_AT_RISK,
	HEALTH_LABELS,
	HEALTH_OFF_TRACK,
	HEALTH_ON_TRACK,
	_health,
)
from pmo.permissions import _is_global_reader, _member_projects_subquery
from pmo.phi import phi_for_row
from pmo.project_economics import can_see_project_economics
from pmo.status_date import build_status_report

# Orden de criticidad para el portafolio (peor primero): Deviated → At risk → Healthy → sin PHI → exento.
_PHI_RANK = {"deviated": 0, "at_risk": 1, "on_track": 2}


def _criticality_key(row):
	"""Clave de orden por criticidad PHI. Los que tienen banda mandan; luego 'sin PHI'; exento al final."""
	state = row.get("phi_state")
	if state == "scored":
		return (
			_PHI_RANK.get(row.get("phi_band"), 3),
			(row.get("phi") if row.get("phi") is not None else 100),
		)
	if state == "unavailable":
		return (4, 0)
	return (5, 0)  # exempt / basic tracking


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
	# Jerarquizar por criticidad PHI (peor primero) sin romper filtros ni P4 (solo reordena filas visibles).
	data.sort(key=_criticality_key)
	return _columns(), data, None, _health_chart(data), _summary(data)


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
		"Project", project, ["project_name", "status", "customer", "pmo_status_date"], as_dict=True
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
	health_key = _health(slip_baseline, slip_committed, overdue, exceeds)

	row = {
		"project": project,
		"project_name": meta.get("project_name"),
		"status": meta.get("status"),
		"customer": meta.get("customer"),  # inventario del portafolio (sin dimensión económica)
		"forecast_end": (report.get("current") or {}).get("expected_end_date"),
		"slip_baseline": slip_baseline,
		"slip_committed": slip_committed,
		"overdue": overdue,
		"forecast_exceeds": exceeds,
		"planned_hours": planned,
		"actual_hours": actual,
		"pct_consumed": flt(actual / planned * 100, 1) if planned > 0 else None,
		"health_key": health_key,  # valor interno estable (lógica/resumen)
		"health": _(HEALTH_LABELS[health_key]),  # presentación traducida
		"has_baseline": has_baseline,  # para el resumen (sin columna propia)
		# Señales de gobierno canónicas (ADR-0014 D9): fuente única en pmo.governance; sin recalcular ni
		# columnas nuevas — expuestas en la fila para consumidores/resúmenes.
		**governance_flags(project),
	}
	# PHI (ADR-0013): reutiliza el mismo `report` (build_status_report) ya calculado (modo ligero, D8).
	row.update(phi_for_row(project, report))
	# Financial Health (ADR-0013b): indicador financiero SEPARADO; solo con acceso económico por proyecto.
	if can_see_project_economics(project):
		fh = get_project_financial_health(project)
		row["fin_state"] = fh["state"]
		row["fin_health"] = _(FIN_STATE_LABELS[fh["state"]]) if fh["state"] in FIN_STATE_LABELS else None
		row["fin_gap"] = fh.get("cost_gap")
	else:
		row["fin_state"] = row["fin_health"] = row["fin_gap"] = None
	return row


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


def _columns():
	def col(field, label, ftype="Data", width=110, options=None):
		c = {"fieldname": field, "label": _(label), "fieldtype": ftype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("project", N_("Project"), "Link", 150, options="Project"),
		col("project_name", N_("Name"), "Data", 200),
		col("customer", N_("Customer"), "Link", 160, options="Customer"),
		col("status", N_("Status"), "Data", 90),
		col("phi", N_("PHI"), "Int", 70),
		col("phi_health", N_("Health"), "Data", 120),
		col("phi_execution", N_("Execution"), "Int", 95),
		col("phi_schedule", N_("Commitment"), "Int", 95),  # etiqueta visible de la dimensión PHI (clave interna sigue 'schedule')
		col("phi_governance", N_("Governance"), "Int", 100),
		col("phi_coverage", N_("Coverage"), "Data", 100),
		col("fin_health", N_("Financial health"), "Data", 130),
		col("health", N_("Schedule status"), "Data", 110),
		col("forecast_end", N_("Forecast end"), "Date", 120),
		col("slip_baseline", N_("Slip vs Baseline (d)"), "Int", 140),
		col("slip_committed", N_("Slip vs commitment (d)"), "Int", 150),
		col("overdue", N_("Overdue"), "Int", 90),
		col("forecast_exceeds", N_("Forecast > commitment"), "Int", 150),
		col("planned_hours", N_("Planned (h)"), "Float", 100),
		col("actual_hours", N_("Actual (h)"), "Float", 100),
		col("pct_consumed", N_("% Consumed"), "Float", 110),
	]


def _health_chart(data):
	"""Donut de distribución de salud para el Dashboard Chart Report-type del Workspace PMO.
	Reutiliza `health_key` ya calculado (sin métrica nueva). P4: opera sobre `data` ya filtrado."""
	counts = {HEALTH_ON_TRACK: 0, HEALTH_AT_RISK: 0, HEALTH_OFF_TRACK: 0}
	for r in data:
		if r.get("health_key") in counts:
			counts[r["health_key"]] += 1
	return {
		"data": {
			"labels": [
				_(HEALTH_LABELS[HEALTH_ON_TRACK]),
				_(HEALTH_LABELS[HEALTH_AT_RISK]),
				_(HEALTH_LABELS[HEALTH_OFF_TRACK]),
			],
			"datasets": [
				{
					"values": [
						counts[HEALTH_ON_TRACK],
						counts[HEALTH_AT_RISK],
						counts[HEALTH_OFF_TRACK],
					]
				}
			],
		},
		"type": "donut",
		"colors": ["#2ECC71", "#F8814F", "#E24C4C"],
	}


def _summary(data):
	if not data:
		return []
	off = sum(1 for r in data if r["health_key"] == HEALTH_OFF_TRACK)
	risk = sum(1 for r in data if r["health_key"] == HEALTH_AT_RISK)
	no_baseline = sum(1 for r in data if not r["has_baseline"])
	return [
		{"label": _("Projects"), "value": len(data), "datatype": "Int"},
		{
			"label": _("Off track"),  # estado de cronograma (no "salud"); reservado "At risk" para PHI
			"value": off,
			"datatype": "Int",
			"indicator": "Red" if off else "Green",
		},
		{
			"label": _("Behind"),
			"value": risk,
			"datatype": "Int",
			"indicator": "Orange" if risk else "Green",
		},
		{
			"label": _("Without baseline"),
			"value": no_baseline,
			"datatype": "Int",
			"indicator": "Orange" if no_baseline else "Green",
		},
	]
