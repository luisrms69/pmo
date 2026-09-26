# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 — Señales de riesgo DERIVADAS por Project (fuente única de cálculo).

Todo se deriva por query de los datos existentes (`PMO Project Risk Assessment` + `PMO Project Risk`): NO se
almacena ningún estado, indicador ni snapshot; no hay máquina de estados nueva. Reutilizado por el form de
Project (botón/indicadores) y por la sección Riesgos de `PMO Project Control` (build_project_control) para no
duplicar la lógica de conteo.

P4: `compute_risk_signals` es cálculo INTERNO (conteos por Project, acotados al Project pedido). El endpoint
whitelisted `get_risk_signals` impone P4 (visibilidad del Project) antes de calcular; en Project Control la P4
ya la impone el chokepoint `build_status_report`.
"""

import frappe

from pmo.permissions import is_project_visible

RISK_DT = "PMO Project Risk"
ASSESSMENT_DT = "PMO Project Risk Assessment"
_ACTIVE = ("Open", "Managing")  # riesgos "vivos" que requieren seguimiento (no Closed/Materialized)
_HIGH_EXPOSURE = "High exposure"


def compute_risk_signals(project: str) -> dict:
	"""Señales derivadas del Project (sin permisos; el boundary impone P4). Solo conteos sobre datos vivos.

	`assessment_state` (derivado de datos reales, sin máquina de estados): "none" si no existe Assessment,
	"assessed" si existe. El workflow usa el Save nativo; no hay una acción de "revisado" que distinguir.
	"""
	assessment = frappe.db.get_value(ASSESSMENT_DT, {"project": project}, "name")
	assessment_state = "assessed" if assessment else "none"
	total = frappe.db.count(RISK_DT, {"project": project})
	active = {"project": project, "status": ("in", _ACTIVE)}
	open_count = frappe.db.count(RISK_DT, active)
	high_exposure = frappe.db.count(RISK_DT, {**active, "exposure": _HIGH_EXPOSURE})
	no_owner = frappe.db.count(RISK_DT, {**active, "risk_owner": ("in", (None, ""))})
	no_response = frappe.db.count(RISK_DT, {**active, "response": ("in", (None, ""))})
	# "Requiere atención" = hay riesgos vivos con exposición alta o con brechas de gestión (sin dueño/respuesta).
	needs_attention = bool(high_exposure or no_owner or no_response)
	return {
		"assessment_exists": bool(assessment),
		"assessment": assessment,
		"assessment_state": assessment_state,
		"total": total,
		"open": open_count,
		"high_exposure": high_exposure,
		"no_owner": no_owner,
		"no_response": no_response,
		"needs_attention": needs_attention,
	}


@frappe.whitelist()
def get_risk_signals(project: str) -> dict:
	"""Endpoint P4-safe para el form de Project. Verifica visibilidad del Project y devuelve las señales."""
	if not project:
		return {}
	user = frappe.session.user
	if user != "Administrator" and not is_project_visible(project, user):
		frappe.throw(frappe._("Not permitted to read this project."), frappe.PermissionError)
	return compute_risk_signals(project)
