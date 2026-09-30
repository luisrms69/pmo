# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Adaptador del PMO Project Health Index (PHI) — reúne las señales canónicas EXISTENTES y delega el
cálculo a `pmo.health.compute_phi` (compositor puro). ADR-0013/0013a.

Principio (ADR-0011 D2 / ADR-0013 D1): **componer, no recalcular**. Este módulo es el ÚNICO con IO:
lee de `build_status_report` (Schedule/Execution + baseline), del motor de gobernanza `_evaluate/_facts`
(Governance), de la economía autorizada `get_authorized_economics` (Financial — user-invariant: el gate
económico es de PRESENTACIÓN, no del motor), del esfuerzo (`Task.expected_time` total + horas reales al
corte) y de `risk_signals` (Risk). `compute_phi` no consulta Tasks/invoices/Risks directamente."""

import frappe
from frappe import N_, _
from frappe.utils import cint, flt, getdate, today

from pmo.health import compute_phi

# ── Presentación (fuente EN, traducible). NUNCA se exponen los códigos internos al usuario. ──
# `N_()` marca las cadenas para extracción al POT aunque se traduzcan luego vía `_(variable)`.
# Etiquetas de banda de SALUD: se evita "On Track" para no confundir con la dimensión Schedule.
PHI_BAND_LABELS = {"on_track": N_("Healthy"), "at_risk": N_("At risk"), "deviated": N_("Deviated")}
PHI_COVERAGE_LABELS = {
	"sufficient": N_("Sufficient"),
	"partial": N_("Partial"),
	"insufficient": N_("Insufficient"),
}
# Mensajes de usuario para critical conditions (distintos de los técnicos del motor).
PHI_CONDITION_LABELS = {
	"economic_reference_inconsistent": N_("Economic reference inconsistent"),
	"cost_overrun": N_("Cost overrun"),
	"effort_overrun": N_("Effort overrun"),
	"high_exposure_risk_unmanaged": N_("Critical risk pending management"),
	"governance_baseline_missing": N_("Baseline missing"),
}
PHI_UNAVAILABLE_TITLE = N_("PHI unavailable")
PHI_UNAVAILABLE_MSG = N_(
	"There is not yet enough evaluable execution data to calculate overall project health."
)
PHI_EXEMPT_TITLE = N_("Basic tracking")
PHI_EXEMPT_MSG = N_("This project is not subject to formal PMO monitoring. PHI does not apply.")


def gather_phi_signals(project: str, cutoff: str | None = None, sr: dict | None = None) -> dict:
	"""Reúne las señales canónicas del Project para PHI. Devuelve el dict que consume `compute_phi`.

	`sr` opcional: reporte de `build_status_report` ya calculado por el caller (p. ej. Portfolio) para
	NO recalcularlo (modo ligero, ADR-0013 D8). Si es None, se construye aquí.

	No aplica el gate económico de presentación: el motor es user-invariant (ADR-0013 D2 re-resuelto). El
	caller whitelisted (`get_project_phi`) ya impone P4 (READ del Project)."""
	from pmo.governance import is_project_started
	from pmo.governance_project import is_governance_exempt

	# A. Exención formal → no tiene PHI (corto-circuito; el motor devuelve applicable=False).
	if is_governance_exempt(project):
		return {"exempt": True}

	from pmo.status_date import build_status_report

	# Resolver el cutoff con el MISMO patrón canónico de build_project_control (ADR-0006): cutoff explícito,
	# o `Project.pmo_status_date`, o hoy. build_status_report lanza si recibe None sin status date fijado.
	if sr is None:
		sd = (
			str(cutoff) if cutoff else (frappe.db.get_value("Project", project, "pmo_status_date") or today())
		)
		sr = build_status_report(project, sd)  # chokepoint P4 (READ, throw)
	ind = sr.get("indicators") or {}
	counts = ind.get("counts") or {}
	baseline_meta = sr.get("baseline")
	has_baseline = baseline_meta is not None

	# Duración del plan (baseline) para normalizar SCH-1: del MISMO snapshot congelado (inicio→fin).
	baseline_duration_days = _baseline_duration_days(baseline_meta)

	# Financial (user-invariant; solo existencia/consistencia de dato, gate de presentación aparte).
	from pmo.project_economics import get_authorized_economics, get_native_real_cost

	econ = get_authorized_economics(project)
	az = econ.get("data") or {}
	authorized_cost = flt(az.get("authorized_cost")) if econ.get("available") else None
	# Costo real COMPARABLE desde la fuente canónica única (labor+externo, excluye material).
	comparable_cost = get_native_real_cost(project)["comparable_cost"]
	percent_complete_native = flt(frappe.db.get_value("Project", project, "percent_complete"))

	# Resources (guardrail): presupuesto TOTAL de horas (Σ expected_time de hojas) vs reales al corte.
	budget_hours = _budget_hours(project)
	actual_hours = flt(ind.get("actual_hours_to_date"))

	# Governance (motor canónico ADR-0014): controles requeridos (completo/pendiente); no_aplica excluido.
	gov_required, gov_fulfilled = _governance_counts(project)

	# Risk (sin peso): señales derivadas existentes.
	from pmo.risk_signals import compute_risk_signals

	risk = compute_risk_signals(project)

	return {
		"exempt": False,
		"started": is_project_started(project),
		# Execution
		"has_baseline": has_baseline,
		"due_by_cutoff": counts.get("baseline_due_by_cutoff"),
		"completed_by_cutoff": counts.get("completed_by_cutoff"),
		# Schedule
		"slip_baseline_days": ind.get("final_date_slip_days"),
		"baseline_duration_days": baseline_duration_days,
		"slip_committed_days": ind.get("slip_vs_committed_days"),
		"has_committed": sr.get("committed_end_date") is not None,
		# Financial (guardrail/cap)
		"financial_inconsistent": econ.get("reason") == "inconsistent",
		"authorized_cost": authorized_cost,
		"comparable_cost": comparable_cost,
		"percent_complete": percent_complete_native,
		# Resources (guardrail)
		"budget_hours": budget_hours,
		"actual_hours": actual_hours,
		# Governance
		"gov_required": gov_required,
		"gov_fulfilled": gov_fulfilled,
		# Risk (critical condition/cap) — el cap exige evaluación establecida (no finge riesgo sin registro).
		"risk_assessment_exists": bool(risk.get("assessment_exists")),
		"risk_high_exposure": cint(risk.get("high_exposure")),
		"risk_no_owner": cint(risk.get("no_owner")),
		"risk_no_response": cint(risk.get("no_response")),
	}


def _baseline_duration_days(baseline_meta) -> int | None:
	"""Duración del plan congelado (inicio→fin) desde el snapshot de la baseline vigente. None si no aplica."""
	if not baseline_meta or not baseline_meta.get("name"):
		return None
	snap = frappe.db.get_value("PMO Project Baseline", baseline_meta.get("name"), "snapshot")
	if not snap:
		return None
	data = frappe.parse_json(snap) or {}
	proj = data.get("project") or {}
	start, end = proj.get("expected_start_date"), proj.get("expected_end_date")
	if not start or not end:
		return None
	days = (getdate(end) - getdate(start)).days
	return days if days > 0 else None


def _budget_hours(project: str) -> float:
	"""Σ `Task.expected_time` (horas estimadas TOTALES) de tareas hoja. Respeta la pqc de Task."""
	total = 0.0
	for t in frappe.get_list(
		"Task", filters={"project": project, "is_group": 0}, fields=["expected_time"], limit=0
	):
		total += flt(t.get("expected_time"))
	return total


def _governance_counts(project: str) -> tuple[int, int]:
	"""(requeridos, cumplidos) desde el motor canónico `_evaluate/_facts` (ADR-0014). `no_aplica` no cuenta."""
	from pmo.governance_inbox import STATE_COMPLETO, STATE_PENDIENTE, _evaluate, _facts

	controls = _evaluate(_facts(project))
	required = fulfilled = 0
	for c in controls.values():
		state = c.get("state")
		if state in (STATE_COMPLETO, STATE_PENDIENTE):
			required += 1
			if state == STATE_COMPLETO:
				fulfilled += 1
	return required, fulfilled


@frappe.whitelist()
def get_project_phi(project: str, cutoff: str | None = None) -> dict:
	"""Endpoint P4-safe: PHI de UN Project. Impone READ y delega al compositor puro.

	Nota: el motor es user-invariant; el gate económico de presentación (`can_see_project_economics`) se
	aplicará al MOSTRAR el detalle Financial, no aquí. Este endpoint no expone cifras económicas crudas."""
	from pmo.pmo.doctype.pmo_settings.pmo_settings import get_phi_weights

	frappe.has_permission("Project", ptype="read", doc=project, throw=True)
	return compute_phi(gather_phi_signals(project, cutoff), weights=get_phi_weights())


def decorate_phi(r: dict) -> dict:
	"""Añade campos de PRESENTACIÓN traducidos (server-side) sobre el resultado de `compute_phi`.
	NO altera el cálculo: solo mapea códigos → etiquetas de usuario. Traduce a la lengua de la sesión."""
	band = r.get("band")
	r["band_label"] = _(PHI_BAND_LABELS[band]) if band in PHI_BAND_LABELS else None
	cl = r.get("coverage_level")
	r["coverage_label"] = _(PHI_COVERAGE_LABELS[cl]) if cl in PHI_COVERAGE_LABELS else None
	# Condiciones críticas → mensajes de usuario (nunca el código interno).
	r["condition_labels"] = [
		_(PHI_CONDITION_LABELS.get(c["code"], c["code"])) for c in (r.get("critical_conditions") or [])
	]
	# Estado de presentación + textos para los casos sin número.
	if not r.get("applicable"):
		r["display_state"] = "exempt"
		r["display_title"] = _(PHI_EXEMPT_TITLE)
		r["display_message"] = _(PHI_EXEMPT_MSG)
	elif r.get("phi") is None:
		r["display_state"] = "unavailable"
		r["display_title"] = _(PHI_UNAVAILABLE_TITLE)
		r["display_message"] = _(PHI_UNAVAILABLE_MSG)
	else:
		r["display_state"] = "scored"
		r["display_title"] = None
		r["display_message"] = None
	return r


def get_phi_view(project: str, cutoff: str | None = None) -> dict:
	"""PHI decorado para PRESENTACIÓN (Project Control → Resumen). P4 + pesos de Settings + etiquetas."""
	return decorate_phi(get_project_phi(project, cutoff))


def phi_for_row(project: str, sr: dict, cutoff: str | None = None) -> dict:
	"""PHI compacto para una fila de Portfolio, reutilizando el `sr` ya calculado (modo ligero, D8).
	Devuelve solo lo necesario para tabla/orden; sin re-ejecutar build_status_report."""
	from pmo.pmo.doctype.pmo_settings.pmo_settings import get_phi_weights

	r = decorate_phi(compute_phi(gather_phi_signals(project, cutoff, sr=sr), weights=get_phi_weights()))
	dims = r.get("dimensions") or {}
	return {
		"phi": r.get("phi"),
		"phi_band": r.get("band"),  # clave interna estable (color/orden)
		"phi_band_raw": r.get("band_raw"),
		"phi_health": r.get("band_label") or r.get("display_title"),  # etiqueta visible
		"phi_state": r.get("display_state"),  # scored | unavailable | exempt
		"phi_execution": (dims.get("execution") or {}).get("score"),
		"phi_schedule": (dims.get("schedule") or {}).get("score"),
		"phi_governance": (dims.get("governance") or {}).get("score"),
		"phi_coverage_level": r.get("coverage_level"),
		"phi_coverage": r.get("coverage_label"),
		"phi_conditions": r.get("condition_labels") or [],
	}
