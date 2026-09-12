# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO dashboard — agregadores de presentación para el Workspace PMO (arquitectura híbrida native-first).

Native-first: los KPIs (tamaño y volumen) y la señal de recursos alimentan **Number Cards nativas**
(type=Custom con `method=`, o Document Type); la salud es un **Dashboard Chart Report-type**; los
cambios abiertos son **Quick List nativa**. Solo dos Custom Blocks consumen datos derivados sin
equivalente nativo: "requieren atención" (+ tareas más atrasadas) y "cartera por cliente".

P4: todo reutiliza motores/consultas que imponen permisos por usuario:
  - pmo_portfolio.execute → READ por proyecto (build_status_report) + set visible explícito.
  - frappe.get_list(...) → permission_query_conditions (Task / Project).
  - PMO Capacity Planning.execute → P4 + enmascarado.
Ningún get_all sobre datos P4; ningún ignore_permissions; caché SIEMPRE por usuario (nunca global).

Nota (Number Card Custom + P4): el pqc de "Number Card" exige, para type=Custom, que su
`document_type` sea legible por el usuario; por eso las cards Custom declaran `document_type="Project"`
(legible por los roles PMO). Ese campo es SOLO para el gate de permiso del widget; el valor lo produce
el `method` (server-side, P4 real). Sin él, las cards no renderizan para roles no-System-Manager.
"""

import json

import frappe
from frappe import N_
from frappe.utils import cint, flt, getdate, today

# Etiquetas visibles (Number Cards + Custom Blocks). JS en fixture → gettext no lo extrae. Inglés canónico.
_DASHBOARD_STRINGS = (
	# KPIs + card de gobernanza + labels de charts (Number Cards / Dashboard Charts nativos)
	N_("Active projects"),
	N_("Active tasks"),
	N_("People involved"),
	N_("Projects requiring attention"),
	N_("Overdue tasks"),
	N_("Projects without baseline"),
	N_("Active clients"),
	N_("Portfolio health"),
	N_("Capacity — current month"),
	N_("Top 5 by planned hours"),
	# Custom Blocks
	N_("Projects requiring attention"),
	N_("Customer"),
	N_("Health"),
	N_("Forecast end"),
	N_("Slip vs BL"),
	N_("Slip vs commit"),
	N_("Overdue"),
	N_("Planned/Actual (h)"),
	N_("Reason"),
	N_("No projects require attention right now."),
	N_("Most delayed tasks"),
	N_("Task"),
	N_("Project"),
	N_("Expected end"),
	N_("Committed"),
	N_("Delay (d)"),
	N_("Status"),
	N_("No delayed tasks among your projects."),
	N_("Portfolio by customer"),
	N_("Projects"),
	N_("At risk / deviated"),
	N_("No customer-linked projects."),
	N_("Could not load this PMO panel."),
)

_KPI_METRICS = ("active", "requiring_attention", "overdue_tasks", "without_baseline", "clients")
_RESOURCE_METRICS = ("people_involved",)


# ---------------------------------------------------------------------------
# Number Cards nativas (type=Custom) — reciben {"metric": ...} en filters_json
# ---------------------------------------------------------------------------
@frappe.whitelist()
def portfolio_kpi(filters: str | dict | None = None):
	"""KPI de tamaño/volumen (Number Card Custom). Derivado del motor PMO Portfolio (P4)."""
	metric = _metric(filters)
	if metric not in _KPI_METRICS:
		frappe.throw(frappe._("Unknown PMO KPI metric: {0}").format(metric))
	return {"value": _data()["kpis"].get(metric)}


@frappe.whitelist()
def resource_kpi(filters: str | dict | None = None):
	"""Señal de recursos (Number Card Custom). Reusa el resumen de PMO Capacity Planning (P4)."""
	metric = _metric(filters)
	if metric not in _RESOURCE_METRICS:
		frappe.throw(frappe._("Unknown PMO resource metric: {0}").format(metric))
	return {"value": _data()["resources"].get(metric)}


# ---------------------------------------------------------------------------
# Custom Blocks (2) — datos derivados sin equivalente nativo
# ---------------------------------------------------------------------------
@frappe.whitelist()
def attention_block():
	"""Bloque central: proyectos que requieren atención + tareas más atrasadas. P4."""
	d = _data()
	return {"attention": d["attention"], "delayed_tasks": d["delayed_tasks"]}


@frappe.whitelist()
def customers_block():
	"""Bloque secundario: cartera por cliente (agregación derivada del portafolio). P4."""
	return {"customers": _data()["customers"]}


def _metric(filters):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	return filters.get("metric")


# ---------------------------------------------------------------------------
# Cómputo único por usuario (caché por-usuario 60s; nunca global)
# ---------------------------------------------------------------------------
def _data():
	cache = frappe.cache()
	key = f"pmo:dashboard:{frappe.session.user}"
	cached = cache.get_value(key)
	if cached is not None:
		return frappe.parse_json(cached)
	data = _build()
	cache.set_value(key, frappe.as_json(data), expires_in_sec=60)
	return data


def _build():
	from pmo.pmo.report.pmo_portfolio.pmo_portfolio import (
		HEALTH_AT_RISK,
		HEALTH_OFF_TRACK,
		HEALTH_ON_TRACK,
		execute,
	)

	_cols, rows, _msg, _chart, _summary = execute({})

	active = len(rows)
	without_baseline = sum(1 for r in rows if not r.get("has_baseline"))
	at_risk = sum(1 for r in rows if r.get("health_key") == HEALTH_AT_RISK)
	deviated = sum(1 for r in rows if r.get("health_key") == HEALTH_OFF_TRACK)
	overdue_tasks = sum(cint(r.get("overdue")) for r in rows)

	proj_names = [r.get("project") for r in rows if r.get("project")]
	cust_map = {}
	if proj_names:
		for p in frappe.get_list(
			"Project", filters={"name": ["in", proj_names]}, fields=["name", "customer"], limit=0
		):
			cust_map[p.name] = p.customer

	clients = len({c for c in cust_map.values() if c})

	kpis = {
		"active": active,
		"requiring_attention": at_risk + deviated,
		"overdue_tasks": overdue_tasks,
		"without_baseline": without_baseline,
		"clients": clients,
	}

	sev = {HEALTH_OFF_TRACK: 2, HEALTH_AT_RISK: 1, HEALTH_ON_TRACK: 0}
	attention = []
	for r in rows:
		hk = r.get("health_key")
		overdue = cint(r.get("overdue"))
		exceeds = cint(r.get("forecast_exceeds"))
		if hk == HEALTH_ON_TRACK and not overdue and not exceeds:
			continue
		attention.append(
			{
				"project": r.get("project"),
				"project_name": r.get("project_name"),
				"customer": cust_map.get(r.get("project")),
				"health": r.get("health"),
				"health_key": hk,
				"forecast_end": r.get("forecast_end"),
				"slip_baseline": r.get("slip_baseline"),
				"slip_committed": r.get("slip_committed"),
				"overdue": overdue,
				"forecast_exceeds": exceeds,
				"planned_hours": r.get("planned_hours"),
				"actual_hours": r.get("actual_hours"),
				"reason": _attention_reason(
					hk, r.get("slip_committed"), r.get("slip_baseline"), overdue, exceeds
				),
			}
		)
	attention.sort(
		key=lambda a: (
			sev.get(a["health_key"], 0),
			cint(a["slip_committed"]),
			a["overdue"],
			cint(a["slip_baseline"]),
		),
		reverse=True,
	)
	attention = attention[:12]

	customers = []
	by_cust = {}
	for r in rows:
		c = cust_map.get(r.get("project"))
		if not c:
			continue
		agg = by_cust.setdefault(
			c, {"customer": c, "projects": 0, "at_risk_deviated": 0, "planned": 0.0, "actual": 0.0}
		)
		agg["projects"] += 1
		if r.get("health_key") in (HEALTH_OFF_TRACK, HEALTH_AT_RISK):
			agg["at_risk_deviated"] += 1
		agg["planned"] += flt(r.get("planned_hours"))
		agg["actual"] += flt(r.get("actual_hours"))
	if by_cust:
		customers = sorted(
			by_cust.values(), key=lambda c: (c["at_risk_deviated"], c["projects"]), reverse=True
		)

	return {
		"kpis": kpis,
		"resources": _resource_signal(),
		"attention": attention,
		"delayed_tasks": _delayed_tasks(),
		"customers": customers,
	}


def _attention_reason(health_key, slip_committed, slip_baseline, overdue, exceeds):
	parts = []
	if cint(slip_committed) > 0:
		parts.append(frappe._("forecast beyond commitment (+{0}d)").format(cint(slip_committed)))
	if overdue:
		parts.append(frappe._("{0} overdue task(s)").format(overdue))
	if exceeds:
		parts.append(frappe._("{0} task(s) forecast past deadline").format(exceeds))
	if not parts and cint(slip_baseline) > 0:
		parts.append(frappe._("slipped vs baseline (+{0}d)").format(cint(slip_baseline)))
	return "; ".join(parts) or frappe._("needs review")


def _delayed_tasks(limit=8):
	"""Tareas visibles más atrasadas (fin esperado pasado, no cerradas). P4 vía get_list (pqc de Task)."""
	rows = frappe.get_list(
		"Task",
		filters={
			"status": ["not in", ["Completed", "Cancelled", "Template"]],
			"exp_end_date": ["<", today()],
		},
		fields=["name", "subject", "project", "status", "exp_end_date", "pmo_deadline", "_assign"],
		order_by="exp_end_date asc",
		limit=limit,
	)
	out = []
	t = getdate(today())
	for r in rows:
		if not r.exp_end_date:
			continue
		assignee = None
		if r.get("_assign"):
			try:
				a = json.loads(r._assign)
				assignee = a[0] if a else None
			except ValueError, TypeError:
				assignee = None
		out.append(
			{
				"task": r.name,
				"subject": r.subject,
				"project": r.project,
				"status": r.status,
				"exp_end_date": r.exp_end_date,
				"pmo_deadline": r.get("pmo_deadline"),
				"delay_days": (t - getdate(r.exp_end_date)).days,
				"assignee": assignee,
			}
		)
	return out


def _resource_signal():
	"""Señal de recursos del resumen de PMO Capacity Planning (P4 + enmascarado), por índice estable:
	[0]=Resources(personas), [1]=Overallocated, [2]=sin capacidad, [3]=utilización %. Robusto al idioma."""
	default = {"people_involved": 0, "utilization": 0, "overallocated": 0, "without_capacity": 0}
	try:
		from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import execute as cap_execute

		filters = {
			"from_date": frappe.utils.get_first_day(today()).isoformat(),
			"to_date": frappe.utils.get_last_day(today()).isoformat(),
			"granularity": "Month",
		}
		summary = cap_execute(filters)[4] or []

		def val(i):
			return summary[i].get("value") if len(summary) > i else 0

		return {
			"people_involved": cint(val(0)),
			"overallocated": cint(val(1)),
			"without_capacity": cint(val(2)),
			"utilization": round(flt(val(3))),
		}
	except Exception:
		frappe.log_error(title="PMO dashboard resource signal", message=frappe.get_traceback())
		return default
