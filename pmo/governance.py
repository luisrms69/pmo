# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Governance & Lifecycle (ADR-0014 D7/D8) — estado de ciclo de vida DERIVADO + índice de expediente.

No hay workflow ni estado paralelo sobre `Project` (ADR-0014 D7): el estado documental se **deriva** de
hechos existentes (Project.status + existencia/submit de Handoff/Baseline/Closure/Review), igual que
`pmo.health` deriva el semáforo. El índice de expediente (D8) es solo referencias/existencia/fechas; no
duplica el contenido de otras vistas.

Resiliencia: Closure y Post-Project Review son bloques posteriores; sus DocTypes pueden **no existir todavía**.
Toda consulta se guarda con `frappe.db.exists("DocType", ...)` → forward-compatible sin romper.
"""

import frappe
from frappe import N_

# Estado documental derivado (clave interna estable; la etiqueta se traduce en presentación).
LIFECYCLE_INITIATION = "initiation"
LIFECYCLE_PLANNING = "planning"
LIFECYCLE_EXECUTION = "execution_control"
LIFECYCLE_CLOSING = "closing"
LIFECYCLE_CLOSED = "closed"
LIFECYCLE_REVIEWED = "post_project_reviewed"

LIFECYCLE_LABELS = {
	LIFECYCLE_INITIATION: N_("Initiation"),
	LIFECYCLE_PLANNING: N_("Planning"),
	LIFECYCLE_EXECUTION: N_("Execution / Control"),
	LIFECYCLE_CLOSING: N_("Closing"),
	LIFECYCLE_CLOSED: N_("Closed"),
	LIFECYCLE_REVIEWED: N_("Post-project reviewed"),
}

# Estados terminales reales del Project nativo de ERPNext (Open/On hold/Completed/Cancelled): ambos requieren
# cierre formal (ADR-0014 D4/D7). Fuente única reutilizada por lifecycle y por las señales de gobierno.
TERMINAL_STATUSES = ("Completed", "Cancelled")
# Estados abiertos canónicos del Change Request (ADR-0005): aún no resueltos.
OPEN_CHANGE_REQUEST_STATES = ("Draft", "In Review")


def _has_submitted(doctype: str, project: str) -> bool:
	"""¿Existe un documento SUBMITTED de `doctype` para el Project? Guardado si el DocType aún no existe."""
	if not frappe.db.exists("DocType", doctype):
		return False
	return bool(frappe.db.exists(doctype, {"project": project, "docstatus": 1}))


def derive_lifecycle_state(project: str) -> str:
	"""Estado documental derivado (precedencia: el más avanzado gana). No modifica nada.

	reviewed → closed → closing (Project terminal sin Closure) → execution (baseline vigente) → planning
	(Handoff emitido) → initiation. Un Project **terminal** (Completed o Cancelled) sin Closure requiere cierre
	formal → Closing. On hold no es terminal: se deriva de sus artefactos/baseline.
	"""
	from pmo.baseline import get_effective_baseline

	if _has_submitted("PMO Post-Project Review", project):
		return LIFECYCLE_REVIEWED
	if _has_submitted("PMO Project Closure", project):
		return LIFECYCLE_CLOSED
	# Estados terminales reales del Project nativo de ERPNext (fuente única TERMINAL_STATUSES).
	if frappe.db.get_value("Project", project, "status") in TERMINAL_STATUSES:
		return LIFECYCLE_CLOSING
	if get_effective_baseline(project):
		return LIFECYCLE_EXECUTION
	if _has_submitted("PMO Project Handoff", project):
		return LIFECYCLE_PLANNING
	return LIFECYCLE_INITIATION


def _artifact(doctype: str, project: str, date_field: str) -> dict:
	"""Entrada de índice para un artefacto submittable: existencia + referencia + fecha del último emitido.

	`pending=True` cuando el DocType aún no existe (bloque futuro) → el expediente lo muestra como pendiente."""
	if not frappe.db.exists("DocType", doctype):
		return {"available": False, "pending": True, "reference": None, "date": None}
	row = frappe.get_all(
		doctype,
		filters={"project": project, "docstatus": 1},
		fields=["name", date_field],
		order_by="creation desc",
		limit=1,
	)
	if not row:
		return {"available": False, "pending": False, "reference": None, "date": None}
	return {
		"available": True,
		"pending": False,
		"reference": row[0]["name"],
		"date": str(row[0][date_field]) if row[0].get(date_field) else None,
	}


def build_expediente(project: str) -> dict:
	"""Índice del expediente de gobierno (ADR-0014 D8): existencia + referencias + fechas, sin duplicar
	contenido. Handoff/Baseline reales; Closure/Review como pendientes hasta su bloque. Change Requests =
	conteos (abiertos/total). Status/Control siempre disponible (el detalle vive en sus vistas)."""
	baseline = frappe.db.get_value("Project", project, "pmo_status_date")  # marca de control disponible
	from pmo.baseline import get_effective_baseline

	eff_baseline = get_effective_baseline(project)
	crs = frappe.get_all(
		"PMO Change Request", filters={"project": project}, fields=["name", "workflow_state"], limit=0
	)
	open_states = {"Draft", "In Review"}
	return {
		"lifecycle_state": derive_lifecycle_state(project),
		"handoff": _artifact("PMO Project Handoff", project, "handoff_date"),
		"baseline": {
			"available": bool(eff_baseline),
			"pending": False,
			"reference": eff_baseline,
			"date": str(frappe.db.get_value("PMO Project Baseline", eff_baseline, "effective_date"))
			if eff_baseline
			else None,
		},
		"status_control": {"available": True, "pending": False, "as_of": str(baseline) if baseline else None},
		"change_requests": {
			"total": len(crs),
			"open": len([c for c in crs if (c.get("workflow_state") or "") in open_states]),
		},
		"closure": _artifact("PMO Project Closure", project, "creation"),
		"review": _artifact("PMO Post-Project Review", project, "creation"),
	}


def governance_flags(project: str) -> dict:
	"""Señales de gobierno por Project (ADR-0014 D9), **fuente única** consumida por Portfolio/Dashboard.
	No duplica reglas por superficie; semántica alineada con D4/D7.

	`needs_baseline` = tiene Handoff submitted **y** no tiene línea base vigente/submitted (siguiente acción
	natural del arranque: Proposal ganada → Project → Handoff → **Baseline**). Risk queda fuera: no se
	consulta ni se genera ninguna señal de riesgo aquí (reserva de UX únicamente)."""
	from pmo.baseline import get_effective_baseline

	status = frappe.db.get_value("Project", project, "status")
	has_handoff = _has_submitted("PMO Project Handoff", project)
	has_baseline = bool(get_effective_baseline(project))
	has_closure = _has_submitted("PMO Project Closure", project)
	has_review = _has_submitted("PMO Post-Project Review", project)
	open_crs = frappe.db.count(
		"PMO Change Request", {"project": project, "workflow_state": ("in", OPEN_CHANGE_REQUEST_STATES)}
	)
	return {
		"has_handoff": has_handoff,
		"needs_baseline": has_handoff and not has_baseline,
		"needs_closure": (status in TERMINAL_STATUSES) and not has_closure,
		"needs_review": has_closure and not has_review,
		"open_change_requests": open_crs,
	}
