# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO dashboard — agregadores de presentación para el Workspace PMO (arquitectura híbrida native-first).

Native-first: los KPIs (tamaño/volumen, económicos y recursos) alimentan **Number Cards nativas**
(type=Custom con `method=`, o Document Type); la salud es un **Dashboard Chart Report-type**. Los
KPIs económicos agregados (`economic_kpi`) respetan el gate económico y la agregación por proyecto.
Custom Blocks para lo derivado sin equivalente nativo: "requieren atención" (+ tareas más atrasadas),
"cartera por cliente" (salud + económicos gateados) y "situación económica" agregada.

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

from pmo.project_economics import (
	ECONOMIC_ROLES,
	can_see_project_economics,
	get_authorized_economics,
)

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
	# Sección Project Governance (Custom HTML Block "PMO Governance"): indicadores + acciones humanas.
	N_("Pending governance actions"),
	N_("No pending governance actions."),
	N_("Without Handoff"),
	N_("Without baseline"),
	N_("Open change requests"),
	N_("Require closure"),
	N_("Require review"),
	# Acciones por Project (se construyen server-side en _governance_actions).
	N_("Create Handoff"),
	N_("Create initial baseline"),
	N_("Address {0} change request"),
	N_("Address {0} change requests"),
	N_("Issue closure"),
	N_("Perform post-project review"),
	# Fila ejecutiva económica + situación económica agregada (Number Cards + Custom Block "PMO Economics").
	N_("Authorized value"),
	N_("Billed"),
	N_("Real cost"),
	N_("Utilization"),
	N_("Authorized margin"),
	N_("Economic situation"),
	N_("No economic access."),
	N_("Authorized"),  # etiqueta corta para el agregado económico y la Cartera
	N_("{0} without linked proposal (excluded)"),
	N_("{0} with inconsistent authorized data"),
	# Cartera por cliente (columnas: cliente · proyectos activos · salud · [autorizado · facturado]).
	N_("Active projects"),
)

_KPI_METRICS = ("active", "requiring_attention", "overdue_tasks", "without_baseline", "clients")
_RESOURCE_METRICS = ("people_involved", "utilization")
_ECONOMIC_METRICS = ("authorized_revenue", "billed", "real_cost")


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
	"""Bloque secundario: cartera por cliente (agregación derivada del portafolio). P4. `econ_access`
	indica si el observador puede ver columnas económicas (mismo gate económico que los KPIs)."""
	d = _data()
	econ = d["economics"]
	return {
		"customers": d["customers"],
		"econ_access": bool(econ.get("has_access")),
		"currency": econ.get("currency"),
	}


@frappe.whitelist()
def governance_block():
	"""Sección Project Governance (ADR-0014 D9): conteos + proyectos con acción de gobierno pendiente. P4."""
	return {"governance": _data()["governance"]}


@frappe.whitelist()
def economic_kpi(filters: str | dict | None = None):
	"""KPI económico agregado del portafolio (Number Card Custom). Gateado por rol económico + READ por
	proyecto (`can_see_project_economics`). Sin acceso → `value=None` (la card muestra "—", no expone
	economía). Compone valores canónicos; no inventa métricas."""
	metric = _metric(filters)
	if metric not in _ECONOMIC_METRICS:
		frappe.throw(frappe._("Unknown PMO economic metric: {0}").format(metric))
	econ = _data()["economics"]
	if not econ.get("has_access"):
		return {"value": None}
	return {"value": econ.get(metric)}


@frappe.whitelist()
def economics_block():
	"""Situación económica agregada del portafolio (Custom Block). Gateada; incluye trazabilidad
	(proyectos sin propuesta excluidos / inconsistentes) para no falsear el agregado."""
	return {"economics": _data()["economics"]}


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
		HEALTH_LABELS,
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

	# Cartera por cliente: horas + salud rollup (peor proyecto manda). La economía por cliente se anexa
	# después, solo si el observador pasa el gate económico.
	by_cust = {}
	for r in rows:
		c = cust_map.get(r.get("project"))
		if not c:
			continue
		agg = by_cust.setdefault(
			c,
			{
				"customer": c,
				"projects": 0,
				"at_risk_deviated": 0,
				"planned": 0.0,
				"actual": 0.0,
				"_off": 0,
				"_risk": 0,
			},
		)
		agg["projects"] += 1
		hk = r.get("health_key")
		if hk in (HEALTH_OFF_TRACK, HEALTH_AT_RISK):
			agg["at_risk_deviated"] += 1
		if hk == HEALTH_OFF_TRACK:
			agg["_off"] += 1
		elif hk == HEALTH_AT_RISK:
			agg["_risk"] += 1
		agg["planned"] += flt(r.get("planned_hours"))
		agg["actual"] += flt(r.get("actual_hours"))

	economics = _economics(rows, cust_map)

	customers = []
	for agg in by_cust.values():
		hk = HEALTH_OFF_TRACK if agg["_off"] else (HEALTH_AT_RISK if agg["_risk"] else HEALTH_ON_TRACK)
		row = {
			"customer": agg["customer"],
			"projects": agg["projects"],
			"at_risk_deviated": agg["at_risk_deviated"],
			"planned": agg["planned"],
			"actual": agg["actual"],
			"health_key": hk,
			"health": frappe._(HEALTH_LABELS[hk]),
		}
		if economics.get("has_access"):
			pc = economics["per_customer"].get(agg["customer"], {})
			row["authorized"] = pc.get("authorized")  # None si el cliente no tiene autorizado disponible
			row["billed"] = pc.get("billed", 0.0)
		customers.append(row)
	customers.sort(key=lambda c: (c["at_risk_deviated"], c["projects"]), reverse=True)

	return {
		"kpis": kpis,
		"resources": _resource_signal(),
		"attention": attention,
		"delayed_tasks": _delayed_tasks(),
		"customers": customers,
		"economics": economics,
		"governance": _governance(),
	}


def _project_native(project):
	"""Lectura de los reales nativos del Project (ERPNext) para la agregación económica. `comparable_cost`
	= total_costing_amount + total_purchase_cost (labor + externo, SIN material), MISMA semántica que la
	sección `costs` de Project Control. Aislado en un helper para trazabilidad y testeabilidad."""
	nat = (
		frappe.db.get_value(
			"Project",
			project,
			["company", "total_billed_amount", "total_costing_amount", "total_purchase_cost"],
			as_dict=True,
		)
		or frappe._dict()
	)
	cur = (
		frappe.db.get_value("Company", nat.get("company"), "default_currency") if nat.get("company") else None
	)
	return {
		"billed": flt(nat.get("total_billed_amount")),
		"comparable_cost": flt(flt(nat.get("total_costing_amount")) + flt(nat.get("total_purchase_cost")), 2),
		"currency": cur,
	}


def _economics(rows, cust_map):
	"""Agregación económica del portafolio (gateada). **Compone** valores canónicos existentes; NO inventa
	métricas (nada de ROI/CPI/SPI/EVM). Respeta `can_see_project_economics` por proyecto. Reglas:

	- `authorized_revenue=None` (proyecto sin propuesta) se **excluye** de la suma, nunca se convierte en 0.
	- Estados `inconsistent` se **cuentan aparte** (trazabilidad) y no falsean el agregado.
	- Si ningún proyecto tuvo autorizado disponible → `authorized_revenue=None` (no 0).
	- Costo real = `comparable_cost` (labor + externo, sin material), MISMA semántica que Project Control.
	- Sin rol económico → `{has_access: False}` (los KPIs devuelven None; sin exponer economía)."""
	if not (set(frappe.get_roles()) & set(ECONOMIC_ROLES)):
		return {"has_access": False}

	authorized = authorized_margin = billed = real_cost = 0.0
	authorized_count = counted = excluded_no_proposal = inconsistent = 0
	base_currencies = set()
	per_customer = {}

	for r in rows:
		project = r.get("project")
		if not project or not can_see_project_economics(project):
			continue
		counted += 1
		nat = _project_native(project)
		billed_p = nat["billed"]
		billed += billed_p
		real_cost += nat["comparable_cost"]
		if nat["currency"]:
			base_currencies.add(nat["currency"])

		econ = get_authorized_economics(project)
		auth_p = None
		if econ.get("available"):
			data = econ.get("data") or {}
			auth_p = flt(data.get("authorized_revenue"))
			authorized += auth_p
			authorized_margin += flt(data.get("authorized_margin"))
			authorized_count += 1
		elif econ.get("reason") == "inconsistent":
			inconsistent += 1
		elif econ.get("reason") == "no_proposal":
			excluded_no_proposal += 1

		c = cust_map.get(project)
		if c:
			pc = per_customer.setdefault(c, {"authorized": None, "billed": 0.0})
			pc["billed"] = flt(pc["billed"] + billed_p, 2)
			if auth_p is not None:
				pc["authorized"] = flt((pc["authorized"] or 0.0) + auth_p, 2)

	return {
		"has_access": True,
		# None (no 0) si ningún proyecto tenía autorizado disponible → no falsear.
		"authorized_revenue": flt(authorized, 2) if authorized_count else None,
		"authorized_margin": flt(authorized_margin, 2) if authorized_count else None,
		"billed": flt(billed, 2),
		"real_cost": flt(real_cost, 2),
		"projects_counted": counted,
		"authorized_count": authorized_count,
		"excluded_no_proposal": excluded_no_proposal,
		"inconsistent": inconsistent,
		"currency": (next(iter(base_currencies)) if len(base_currencies) == 1 else None),
		"per_customer": per_customer,
	}


def _governance_actions(f):
	"""Acciones de gobierno en lenguaje humano, DERIVADAS de las señales canónicas (fuente única
	`pmo.governance`). Sin claves internas de lifecycle. Orden natural del ciclo:
	Handoff → Baseline → Cambios → Cierre → Revisión. Risk NO participa (reserva de UX)."""
	actions = []
	if not f["has_handoff"]:
		actions.append(frappe._("Create Handoff"))
	elif f["needs_baseline"]:
		# Solo cuando ya hay Handoff (no se muestra si todavía falta el Handoff).
		actions.append(frappe._("Create initial baseline"))
	n = cint(f["open_change_requests"])
	if n > 0:
		actions.append(
			frappe._("Address {0} change request").format(n)
			if n == 1
			else frappe._("Address {0} change requests").format(n)
		)
	if f["needs_closure"]:
		actions.append(frappe._("Issue closure"))
	if f["needs_review"]:
		actions.append(frappe._("Perform post-project review"))
	return actions


def _governance():
	"""Sección Project Governance (ADR-0014 D9). Consume las señales canónicas de `pmo.governance`
	(fuente única) sobre los Projects VISIBLES (P4 vía get_list, que aplica permission_query_conditions).
	Devuelve conteos + filas con ACCIONES en lenguaje humano; **no expone** claves internas de lifecycle.
	Incluye estados terminales (Completed/Cancelled). Sin maturity score. Risk: reserva de UX (sin señal)."""
	from pmo.governance import governance_flags

	counts = {
		"without_handoff": 0,
		"needs_baseline": 0,
		"open_change_requests": 0,
		"needs_closure": 0,
		"needs_review": 0,
	}
	items = []
	for p in frappe.get_list("Project", fields=["name", "project_name", "customer", "status"], limit=0):
		f = governance_flags(p.name)
		if not f["has_handoff"]:
			counts["without_handoff"] += 1
		if f["needs_baseline"]:
			counts["needs_baseline"] += 1
		if f["needs_closure"]:
			counts["needs_closure"] += 1
		if f["needs_review"]:
			counts["needs_review"] += 1
		counts["open_change_requests"] += cint(f["open_change_requests"])
		actions = _governance_actions(f)
		if actions:
			items.append(
				{
					"project": p.name,
					"project_name": p.project_name,
					"customer": p.customer,
					"actions": actions,
				}
			)
	return {"counts": counts, "items": items[:20]}


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
