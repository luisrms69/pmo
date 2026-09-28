# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Gobernanza V1 — MOTOR ÚNICO read-only de desviaciones de gobernanza (el "contrato").

Una sola fuente de verdad que evalúa, por Project sujeto a gobernanza, el estado de cada control y produce:
  - la BANDEJA de desviaciones (una fila por control-en-desviación), y
  - el RESUMEN DE CUMPLIMIENTO (Completos/Pendientes/No aplica/Total por control),
ambos DERIVADOS del mismo `_evaluate(project)` (nunca dos lógicas). Reutiliza los motores existentes
(`pmo.governance`, `pmo.risk_signals`, workflow del Change Request, `get_effective_baseline`); NO recalcula
slips ni duplica reglas. NO crea DocType, workflow, scheduler, SLA ni política.

P4: los endpoints iteran `frappe.get_list("Project", ...)` (impone `permission_query_conditions`); los
proyectos excluidos de gobernanza se omiten de las desviaciones y de los numeradores/denominadores (no
falsean el cumplimiento) pero siguen visibles vía el reporte de exentos.

Responsable de la siguiente acción (PM/PMO): convención semántica del control (el workflow del CR no separa
por rol). PMO = decisión de un cambio en revisión + revisión posterior; PM = el resto.
"""

import frappe
from frappe import N_
from frappe.utils import cint, getdate, today

# Cadenas visibles del Custom Block "PMO Governance" (JS en fixture → gettext no las extrae del JSON). Se
# registran aquí para que `generate-pot` las conserve; su traducción es-MX vive en locale/es.po.
_GOVERNANCE_BOARD_STRINGS = (
	N_("Supervision of the project governance cycle compliance: what is missing, why, and who must act."),
	N_("Governance cycle of the project"),
	N_("Requires PMO action"),
	N_("Requires PM action"),
	N_("Active projects excluded"),
	N_("Items requiring PMO review or decision."),
	N_("Items requiring the Project Manager's attention."),
	N_("Projects not subject to governance."),
	N_("Require attention"),
	N_("Projects with pending or in-review governance items."),
	N_("Projects not subject to governance"),
	N_("Active projects formally excluded from PMO governance."),
	N_("No projects excluded from governance."),
	N_("No pending governance actions."),
	N_("Could not load this PMO panel."),
	N_("Project"),
	N_("Project Manager"),
	N_("Control"),
	N_("Situation"),
	N_("Age / Date"),
	N_("Owner"),
	N_("Review"),
	N_("Complete"),
	N_("Pending"),
	N_("Not applicable"),
	N_("Exclusion reason"),
	N_("Authorized by"),
	N_("Date"),
)

from pmo.baseline import get_effective_baseline
from pmo.governance import (
	OPEN_CHANGE_REQUEST_STATES,
	TERMINAL_STATUSES,
	is_project_started,
)
from pmo.governance_project import is_governance_exempt
from pmo.risk_signals import compute_risk_signals

# Claves internas estables de control + etiqueta es-MX de presentación.
CONTROL_ACTA = "acta"
CONTROL_BASELINE = "baseline"
CONTROL_RISK = "risk"
CONTROL_CHANGE = "change"
CONTROL_CLOSURE = "closure"
CONTROL_REVIEW = "review"

CONTROL_ORDER = (
	CONTROL_ACTA,
	CONTROL_BASELINE,
	CONTROL_RISK,
	CONTROL_CHANGE,
	CONTROL_CLOSURE,
	CONTROL_REVIEW,
)
CONTROL_LABELS = {
	CONTROL_ACTA: "Acta de inicio",
	CONTROL_BASELINE: "Línea base",
	CONTROL_RISK: "Riesgos",
	CONTROL_CHANGE: "Cambios",
	CONTROL_CLOSURE: "Cierre",
	CONTROL_REVIEW: "Revisión posterior",
}
# Descripción muy breve de cada etapa del ciclo (es-MX) para las tarjetas del dashboard. Solo presentación.
CONTROL_DESCRIPTIONS = {
	CONTROL_ACTA: "Formaliza la transferencia del proyecto a ejecución.",
	CONTROL_BASELINE: "Congela el plan comprometido de referencia.",
	CONTROL_RISK: "Evalúa y gestiona los riesgos del proyecto.",
	CONTROL_CHANGE: "Controla formalmente los cambios de alcance/plan.",
	CONTROL_CLOSURE: "Cierre formal del proyecto ya terminado.",
	CONTROL_REVIEW: "Revisión posterior y lecciones aprendidas.",
}
# Ícono (sprite de Frappe) por etapa, para el encabezado de cada tarjeta. Solo presentación.
CONTROL_ICONS = {
	CONTROL_ACTA: "file",
	CONTROL_BASELINE: "milestone",
	CONTROL_RISK: "alert",
	CONTROL_CHANGE: "switch",
	CONTROL_CLOSURE: "tick-circle",
	CONTROL_REVIEW: "review",
}

# Estados de un control por-Project.
STATE_COMPLETO = "completo"
STATE_PENDIENTE = "pendiente"
STATE_NO_APLICA = "no_aplica"

PM = "PM"
PMO = "PMO"


def _age_days(since):
	"""Días desde `since` (fecha/datetime) hasta hoy, o None si no hay fecha defendible."""
	if not since:
		return None
	d = getdate(since)
	return max((getdate(today()) - d).days, 0)


def _facts(project: str) -> dict:
	"""Hechos canónicos del Project leídos UNA vez (nativos + artefactos + señales existentes)."""
	p = (
		frappe.db.get_value(
			"Project",
			project,
			["project_name", "status", "actual_start_date", "actual_end_date", "pmo_project_manager"],
			as_dict=True,
		)
		or frappe._dict()
	)
	handoff = frappe.get_all(
		"PMO Project Handoff",
		filters={"project": project, "docstatus": 1},
		fields=["name", "handoff_date"],
		order_by="creation desc",
		limit=1,
	)
	closure = frappe.get_all(
		"PMO Project Closure",
		filters={"project": project, "docstatus": 1},
		fields=["name", "closure_date"],
		order_by="creation desc",
		limit=1,
	)
	review = frappe.get_all(
		"PMO Post-Project Review",
		filters={"project": project, "docstatus": 1},
		fields=["name"],
		limit=1,
	)
	crs = frappe.get_all(
		"PMO Change Request",
		filters={"project": project},
		fields=[
			"name",
			"title",
			"workflow_state",
			"docstatus",
			"request_date",
			"approved_at",
			"applied_at",
			"baseline_after",
			# Flags de impacto declarados en el CR: definen si el cambio afecta el plan congelado en la
			# baseline (scope/WBS, cronograma y asignaciones/esfuerzo forman parte del snapshot ADR-0004).
			"impacts_scope",
			"impacts_schedule",
			"impacts_effort",
		],
	)
	return {
		"project": project,
		"project_name": p.get("project_name") or project,
		"project_manager": p.get("pmo_project_manager"),
		"status": p.get("status"),
		"actual_start_date": p.get("actual_start_date"),
		"actual_end_date": p.get("actual_end_date"),
		"started": is_project_started(project),
		"handoff": handoff[0] if handoff else None,
		"baseline": get_effective_baseline(project),
		"closure": closure[0] if closure else None,
		"review": review[0] if review else None,
		"crs": crs,
		"risk": compute_risk_signals(project),
	}


def _change_rows(f: dict) -> list:
	"""Filas de desviación de Change Control, una por CR abierto, mapeando el estado real del workflow al
	responsable de la siguiente acción. Reutiliza los estados existentes (ADR-0005/0015); no inventa estados.
	Rebaseline: un CR Implementado exige nueva baseline SOLO si el cambio AFECTA el plan congelado —declarado
	en el propio CR con `impacts_scope`/`impacts_schedule`/`impacts_effort` (scope/WBS, cronograma y
	asignaciones forman el snapshot ADR-0004)—. Un cambio solo comercial/riesgo NO exige rebaseline. Con
	`baseline_after` ya vinculado, el rebaseline quedó reflejado ⇒ sin desviación."""
	rows = []
	for cr in f["crs"]:
		state = cr.get("workflow_state") or ""
		if state not in OPEN_CHANGE_REQUEST_STATES or cint(cr.get("docstatus")) == 2:
			continue
		title = cr.get("title") or cr.get("name")
		base = {
			"control": CONTROL_CHANGE,
			"target_doctype": "PMO Change Request",
			"target_name": cr.get("name"),
		}
		if state == "Draft":
			rows.append(
				{
					**base,
					"situation": f"Cambio en preparación: {title}",
					"action_owner": PM,
					"since_date": cr.get("request_date"),
				}
			)
		elif state == "In Review":
			# Decisión de gobierno (aprobar/rechazar) → PMO. Fecha defendible: solicitud del cambio.
			rows.append(
				{
					**base,
					"situation": f"Cambio en revisión, espera decisión PMO: {title}",
					"action_owner": PMO,
					"since_date": cr.get("request_date"),
				}
			)
		elif state == "Approved":
			rows.append(
				{
					**base,
					"situation": f"Cambio aprobado sin aplicar: {title}",
					"action_owner": PM,
					"since_date": cr.get("approved_at"),
				}
			)
		elif state == "Implemented":
			affects_baseline = bool(
				cint(cr.get("impacts_scope"))
				or cint(cr.get("impacts_schedule"))
				or cint(cr.get("impacts_effort"))
			)
			if affects_baseline and not cr.get("baseline_after"):
				rows.append(
					{
						**base,
						"situation": f"Cambio implementado sin re-baseline: {title}",
						"action_owner": PM,
						"since_date": cr.get("applied_at"),
					}
				)
			# No exige rebaseline si el cambio no afecta el plan congelado, o si `baseline_after` ya lo refleja.
	return rows


def _evaluate(f: dict) -> dict:
	"""Estado de CADA control del Project (completo/pendiente/no_aplica) + su desviación si aplica.
	FUENTE ÚNICA consumida por la bandeja y por el resumen de cumplimiento."""
	started = f["started"]
	has_handoff = bool(f["handoff"])
	has_baseline = bool(f["baseline"])
	is_terminal = f["status"] in TERMINAL_STATUSES
	has_closure = bool(f["closure"])
	has_review = bool(f["review"])
	risk = f["risk"]

	controls = {}

	# A. ACTA DE INICIO — obligatoria desde que el proyecto inicia ejecución. La evidencia de cumplimiento
	# (Acta emitida) tiene prioridad: si existe, el control está completo aunque el proyecto aún no "inicie".
	if has_handoff:
		controls[CONTROL_ACTA] = {"state": STATE_COMPLETO}
	elif started:
		controls[CONTROL_ACTA] = {
			"state": STATE_PENDIENTE,
			"situation": "Proyecto iniciado sin Acta de inicio",
			"action_owner": PM,
			"since_date": f["actual_start_date"],
			"target_doctype": "PMO Project Handoff",
			"target_name": None,
		}
	else:
		controls[CONTROL_ACTA] = {"state": STATE_NO_APLICA}

	# B. LÍNEA BASE — obligatoria desde el inicio de ejecución (independiente del Acta: su ausencia no la oculta).
	# La baseline vigente cuenta como completo aunque el proyecto aún no "inicie" (ya congeló su compromiso).
	if has_baseline:
		controls[CONTROL_BASELINE] = {"state": STATE_COMPLETO}
	elif not started:
		controls[CONTROL_BASELINE] = {"state": STATE_NO_APLICA}
	else:
		# Antigüedad desde el hito que exige el plan: handoff emitido si existe, si no el inicio de ejecución.
		since = (f["handoff"] or {}).get("handoff_date") or f["actual_start_date"]
		controls[CONTROL_BASELINE] = {
			"state": STATE_PENDIENTE,
			"situation": "Proyecto en ejecución sin línea base vigente",
			"action_owner": PM,
			"since_date": since,
			"route": "pmo_project_control",
			"target_name": f["project"],
		}

	# C. RIESGOS — la gobernanza de riesgos EMPIEZA con la primera línea base (antes: no aplica). Desde ahí es
	# obligatorio tener el control de riesgos: (1) que exista la EVALUACIÓN de riesgos, y (2) que los riesgos
	# activos estén gestionados (con responsable y respuesta). Un riesgo alto BIEN gestionado NO es desviación.
	# Reutiliza `pmo.risk_signals` (Risk Assessment/Risk Analysis existente); no crea otro mecanismo.
	if not has_baseline:
		controls[CONTROL_RISK] = {"state": STATE_NO_APLICA}
	elif not risk.get("assessment_exists"):
		# Con baseline pero sin ninguna evaluación de riesgos → control ausente (no basta con no tener riesgos).
		controls[CONTROL_RISK] = {
			"state": STATE_PENDIENTE,
			"situation": "Proyecto con línea base sin evaluación de riesgos",
			"action_owner": PM,
			"since_date": None,  # sin fecha canónica del nacimiento de la carencia (gap reportado)
			"target_doctype": "PMO Project Risk Assessment",
			"target_name": None,
		}
	else:
		deficiency = cint(risk.get("no_owner")) > 0 or cint(risk.get("no_response")) > 0
		if not deficiency:
			controls[CONTROL_RISK] = {"state": STATE_COMPLETO}
		else:
			parts = []
			if cint(risk.get("no_owner")) > 0:
				parts.append(f"{cint(risk['no_owner'])} sin responsable")
			if cint(risk.get("no_response")) > 0:
				parts.append(f"{cint(risk['no_response'])} sin plan de respuesta")
			controls[CONTROL_RISK] = {
				"state": STATE_PENDIENTE,
				"situation": "Riesgos activos con gestión incompleta: " + ", ".join(parts),
				"action_owner": PM,
				"since_date": None,  # sin fecha canónica del nacimiento de la carencia (gap reportado)
				"target_doctype": "PMO Project Risk Assessment",
				"target_name": risk.get("assessment"),
			}

	# D. CAMBIOS — una entrada por CR abierto (multi-fila). Estado del control para cumplimiento:
	change_rows = _change_rows(f)
	total_crs = len(f["crs"])
	if change_rows:
		controls[CONTROL_CHANGE] = {"state": STATE_PENDIENTE, "rows": change_rows}
	elif total_crs:
		controls[CONTROL_CHANGE] = {"state": STATE_COMPLETO}
	else:
		controls[CONTROL_CHANGE] = {"state": STATE_NO_APLICA}

	# E. CIERRE — obligatorio cuando el Project es terminal (Completed/Cancelled).
	if not is_terminal:
		controls[CONTROL_CLOSURE] = {"state": STATE_NO_APLICA}
	elif has_closure:
		controls[CONTROL_CLOSURE] = {"state": STATE_COMPLETO}
	else:
		controls[CONTROL_CLOSURE] = {
			"state": STATE_PENDIENTE,
			"situation": "Proyecto terminado sin cierre formal",
			"action_owner": PM,
			"since_date": f[
				"actual_end_date"
			],  # Completed: derivado de tareas; Cancelled: puede faltar (gap)
			"target_doctype": "PMO Project Closure",
			"target_name": None,
		}

	# F. REVISIÓN POSTERIOR — obligatoria una vez emitido el Cierre. Responsable: PMO (ver reporte: el modelo
	# de permisos actual solo permite crearla a Projects User/System Manager → discrepancia reportada).
	if not has_closure:
		controls[CONTROL_REVIEW] = {"state": STATE_NO_APLICA}
	elif has_review:
		controls[CONTROL_REVIEW] = {"state": STATE_COMPLETO}
	else:
		controls[CONTROL_REVIEW] = {
			"state": STATE_PENDIENTE,
			"situation": "Cierre emitido sin revisión posterior",
			"action_owner": PMO,
			"since_date": (f["closure"] or {}).get("closure_date"),
			"target_doctype": "PMO Post-Project Review",
			"target_name": None,
		}

	return controls


def compute_deviations(project: str) -> list:
	"""Lista de desviaciones de gobernanza de UN Project (asume sujeto a gobernanza; el caller filtra exentos).
	Fila por control en estado `pendiente`. Cada fila lleva responsable + fecha/antigüedad + destino de "Revisar"."""
	f = _facts(project)
	controls = _evaluate(f)
	rows = []
	for key in CONTROL_ORDER:
		c = controls.get(key, {})
		if c.get("state") != STATE_PENDIENTE:
			continue
		devs = c.get("rows") or [c]  # CHANGE trae varias filas; el resto una
		for d in devs:
			since = d.get("since_date")
			rows.append(
				{
					"project": f["project"],
					"project_name": f["project_name"],
					"project_manager": f["project_manager"],
					"control": key,
					"control_label": CONTROL_LABELS[key],
					"situation": d.get("situation"),
					"action_owner": d.get("action_owner"),
					"since_date": str(since) if since else None,
					"age_days": _age_days(since),
					"target_doctype": d.get("target_doctype"),
					"target_name": d.get("target_name"),
					"route": d.get("route"),
				}
			)
	return rows


def _visible_projects():
	"""Projects visibles para el usuario (P4 vía permission_query_conditions). Activos e inactivos: la
	gobernanza cubre todo el ciclo (incluye terminales que requieren cierre/revisión)."""
	return frappe.get_list(
		"Project",
		fields=[
			"name",
			"project_name",
			"status",
			"pmo_project_manager",
			"pmo_governance_exempt",
			"pmo_exempt_reason",
			"pmo_exempt_by",
			"pmo_exempt_on",
		],
		limit=0,
	)


@frappe.whitelist()
def governance_board() -> dict:
	"""Tablero de Gobernanza (P4). Bandeja de desviaciones + KPIs + resumen de cumplimiento, todo del mismo
	contrato. Los proyectos excluidos se omiten de desviaciones y cumplimiento (se ven en su reporte)."""
	projects = _visible_projects()
	items = []
	excluded = []
	# Denominadores del cumplimiento: SOLO proyectos sujetos a gobernanza (excluidos no falsean el %).
	summary = {k: {"completo": 0, "pendiente": 0, "no_aplica": 0, "con_pendientes": 0} for k in CONTROL_ORDER}
	governed = exempt_count = 0

	for p in projects:
		if cint(p.get("pmo_governance_exempt")):
			exempt_count += 1
			# Proyectos ACTIVOS excluidos → se muestran en la misma página (no en un reporte aparte).
			if p.get("status") not in TERMINAL_STATUSES:
				excluded.append(
					{
						"project": p.name,
						"project_name": p.get("project_name") or p.name,
						"project_manager": p.get("pmo_project_manager"),
						"reason": p.get("pmo_exempt_reason"),
						"exempt_by": p.get("pmo_exempt_by"),
						"exempt_on": str(p.get("pmo_exempt_on")) if p.get("pmo_exempt_on") else None,
					}
				)
			continue
		governed += 1
		f = _facts(p.name)
		controls = _evaluate(f)
		# Resumen de cumplimiento (misma evaluación que la bandeja).
		for key in CONTROL_ORDER:
			st = controls.get(key, {}).get("state", STATE_NO_APLICA)
			summary[key][st] += 1
			if st == STATE_PENDIENTE:
				summary[key]["con_pendientes"] += 1
		# Bandeja: filas pendientes.
		items.extend(compute_deviations(p.name))

	pmo_actions = sum(1 for r in items if r["action_owner"] == PMO)
	pm_actions = sum(1 for r in items if r["action_owner"] == PM)
	# Orden de la bandeja: mayor antigüedad primero; sin fecha al final.
	items.sort(key=lambda r: (r["age_days"] is None, -(r["age_days"] or 0)))

	# `stages` = las seis etapas del ciclo para las tarjetas del dashboard. Es PURA AGREGACIÓN de la
	# clasificación del motor (`_evaluate`): completo/pendiente/no_aplica por control, con
	# `completo + pendiente + no_aplica = governed`. NO recalcula reglas de lifecycle (fuente única).
	# `compliance` se conserva (payload interno + tests); la tabla de cumplimiento se retira de la UI.
	stages = []
	compliance = []
	for key in CONTROL_ORDER:
		s = summary[key]
		stages.append(
			{
				"control": key,
				"control_label": CONTROL_LABELS[key],
				"description": CONTROL_DESCRIPTIONS[key],
				"icon": CONTROL_ICONS[key],
				"completo": s["completo"],
				"pendiente": s["pendiente"],
				"no_aplica": s["no_aplica"],
			}
		)
		compliance.append(
			{
				"control": key,
				"control_label": CONTROL_LABELS[key],
				"completos": s["completo"],
				"pendientes": s["pendiente"],
				"no_aplica": s["no_aplica"],
				"total": governed,
				"con_pendientes": s["con_pendientes"],
			}
		)

	return {
		"kpis": {
			"pmo_actions": pmo_actions,
			"pm_actions": pm_actions,
			"exempt_active": exempt_count,
		},
		"stages": stages,
		"items": items,
		"excluded": excluded,
		"compliance": compliance,
		"governed": governed,
	}


@frappe.whitelist()
def get_project_governance(project: str) -> dict:
	"""Estado de gobernanza de UN Project para el form nativo (P4: READ del Project). Compacto: iniciado +
	exento + desviaciones del propio proyecto (o vacío si exento)."""
	frappe.has_permission("Project", ptype="read", doc=project, throw=True)
	exempt = is_governance_exempt(project)
	return {
		"project": project,
		"started": is_project_started(project),
		"exempt": exempt,
		"deviations": [] if exempt else compute_deviations(project),
	}
