# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Orientación PMO — capa LIGERA de "¿qué debo atender AHORA?" sobre el Project (read-only).

NO es un motor nuevo: COMPONE señales ya calculadas y las presenta como ≤3 recomendaciones accionables.
Reutiliza:
  - `pmo.project_control.project_governance_state` → controles de gobernanza (estado/responsable/etapa),
    Project Manager, status, exención y P4 (impone `has_permission("Project","read",throw=True)`).
  - `pmo.project_control._planning_section` → orientación OPERATIVA (sin responsable + planeación
    incompleta) sobre tareas hoja. Se le pasa un stub `{"status_date": today(), "baseline": None}`:
    * corte = HOY (acciones pendientes AHORA), NO `pmo_status_date` (que es diagnóstico histórico);
    * `baseline=None` → no se calcula cobertura de baseline (no se usa aquí) y NO se ejecuta
      `build_status_report`/`build_project_control`.

Distinción deliberada frente a las otras superficies:
  - Orientación PMO → "¿qué atiendo ahora?" (este módulo);
  - Project Control → "¿cómo está?"; Governance → "¿qué controles cumplo?".
No duplica reglas de Governance/Planning: solo decide qué familias son OPERATIVAS (independientes de la
exención) vs. de GOBERNANZA (respetan `pmo_governance_exempt`) y las ordena de forma determinista.

Exención (decisión de diseño): familias 2/5/6 (gobernanza) se omiten si el proyecto está exento; 1/3/4
(operativas) siguen disponibles — un proyecto exento igual puede tener tareas sin responsable o sin
programación completa.
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from pmo.governance import TERMINAL_STATUSES
from pmo.project_control import _planning_section, project_governance_state

PM = "PM"
PMO = "PMO"

# Orden global de prerrequisitos (determinista; sin puntajes). Las etapas ya las gatea `_evaluate`
# (un control solo es `pendiente` en su etapa aplicable), así que basta este orden fijo sobre los
# candidatos realmente aplicables.
FAMILY_ORDER = (
	"pm_unassigned",
	"handoff",
	"baseline",
	"unassigned_tasks",
	"planning_incomplete",
	"governance",
)

MAX_RECOMMENDATIONS = 3


@frappe.whitelist()
def get_orientation(project: str) -> dict:
	"""≤3 recomendaciones de "qué atender ahora" para el Project. Compositor read-only; P4 vía
	`project_governance_state` (throw si no hay READ). Devuelve `has_recommendations=False` si no hay nada."""
	# P4 + contrato de gobernanza (PM, status, started, exempt, controls, baseline). Una sola llamada.
	pgs = project_governance_state(project)
	# Orientación operativa al corte de HOY (no pmo_status_date). Stub sin baseline (no se usa aquí).
	plan = _planning_section(project, {"status_date": today(), "baseline": None})

	candidates = _build_candidates(pgs, plan)
	recs = _prioritize(candidates, pgs.get("status"))[:MAX_RECOMMENDATIONS]
	return {
		"project": project,
		"has_recommendations": bool(recs),
		"recommendations": recs,
	}


def _controls_map(pgs: dict) -> dict:
	"""{control_key: control_dict} desde el contrato de project_governance_state."""
	return {c["control"]: c for c in (pgs.get("controls") or [])}


def _build_candidates(pgs: dict, plan: dict) -> dict:
	"""Construye las familias APLICABLES hoy. Devuelve {family: recommendation}. Reutiliza las reglas de
	aplicabilidad ya implementadas (estado del control, delimitación de `unassigned`); no las redefine."""
	exempt = bool(pgs.get("exempt"))
	status = pgs.get("status")
	controls = _controls_map(pgs)
	out = {}

	# --- 1. OPERATIVA · PM sin asignar (independiente de exención; relevante mientras no sea terminal) ---
	if not pgs.get("project_manager") and status not in TERMINAL_STATUSES:
		out["pm_unassigned"] = {
			"family": "pm_unassigned",
			"owner": PMO,
			"message": _("Project Manager sin asignar"),
			"action": {"label": _("Asignar responsable"), "kind": "scroll_field"},
			"can_act": True,
		}

	# --- 3. OPERATIVA · Actividades activas y exigibles sin responsable ---
	ua = (plan.get("unassigned") or {}).get("count") or 0
	if ua > 0:
		out["unassigned_tasks"] = {
			"family": "unassigned_tasks",
			"owner": PM,
			# Mensaje NEUTRO: la lista muestra todas las tareas del proyecto, no solo las sin responsable.
			"message": _("{0} actividad(es) sin responsable").format(ua),
			"action": {"label": _("Ver actividades"), "kind": "task_list"},
			"can_act": True,
		}

	# --- 4. OPERATIVA · Planeación incompleta (fechas/estimación) — solo si hay tareas hoja ---
	if cint(plan.get("total")) > 0 and cint(plan.get("schedule_incomplete")) > 0:
		n = cint(plan.get("schedule_incomplete"))
		out["planning_incomplete"] = {
			"family": "planning_incomplete",
			"owner": PM,
			"message": _("{0} actividad(es) sin programación completa (fechas/estimación)").format(n),
			"action": {"label": _("Revisar planeación"), "kind": "project_control_status"},
			"can_act": True,
		}

	# --- 2/5/6 GOBERNANZA · respetan la exención ---
	if not exempt:
		acta = controls.get("acta") or {}
		if acta.get("state") == "pendiente":
			out["handoff"] = {
				"family": "handoff",
				"owner": acta.get("action_owner") or PM,
				"message": acta.get("situation") or _("Acta de inicio pendiente"),
				"action": {"label": _("Crear acta de inicio"), "kind": "create_handoff"},
				"can_act": bool(acta.get("can_create")),
			}

		baseline = controls.get("baseline") or {}
		if baseline.get("state") == "pendiente":
			out["baseline"] = {
				"family": "baseline",
				"owner": baseline.get("action_owner") or PM,
				"message": baseline.get("situation") or _("Línea base pendiente"),
				"action": {"label": _("Establecer línea base"), "kind": "establish_baseline"},
				"can_act": bool(baseline.get("can_create")),
			}

		gov = _governance_candidate(controls, status)
		if gov:
			out["governance"] = gov

	return out


def _governance_candidate(controls: dict, status: str) -> dict | None:
	"""UNA sola recomendación de gobernanza, elegida por ETAPA (no CONTROL_ORDER ciego):
	- Proyecto terminal: Closure antes que Review.
	- Proyecto activo: un Change Request en revisión (decisión PMO pendiente) antes que Riesgos y que
	  otros cambios.
	Devuelve None si ningún control de esa familia está pendiente."""
	if status in TERMINAL_STATUSES:
		order = ("closure", "review")
	else:
		change = controls.get("change") or {}
		in_review = cint((change.get("counts") or {}).get("in_review"))
		# CR esperando decisión PMO primero; luego riesgos; luego el resto de cambios.
		order = ("change", "risk") if in_review > 0 else ("risk", "change")

	nav = {
		"risk": "manage_risks",
		"change": "change_requests",
		"closure": "create_closure",
		"review": "create_review",
	}
	labels = {
		"risk": _("Gestionar riesgos"),
		"change": _("Ver cambios"),
		"closure": _("Emitir cierre"),
		"review": _("Realizar revisión posterior"),
	}
	for key in order:
		c = controls.get(key) or {}
		if c.get("state") == "pendiente":
			return {
				"family": "governance",
				"control": key,
				"owner": c.get("action_owner") or PM,
				"message": c.get("situation") or c.get("label") or _("Control de gobernanza pendiente"),
				"action": {"label": labels[key], "kind": nav[key], "existing": c.get("existing")},
				"can_act": bool(c.get("can_create") or c.get("existing") or key in ("change", "risk")),
			}
	return None


def _prioritize(candidates: dict, status: str) -> list:
	"""Orden determinista por prerrequisitos (FAMILY_ORDER). Sin puntajes ni estados nuevos."""
	return [candidates[f] for f in FAMILY_ORDER if f in candidates]
