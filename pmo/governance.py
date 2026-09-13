# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Governance & Lifecycle (ADR-0014 D7/D8) — estado de ciclo de vida DERIVADO + índice de expediente.

No hay workflow ni estado paralelo sobre `Project` (ADR-0014 D7): el estado documental se **deriva** de
hechos existentes (Project.status + existencia/submit de Charter/Baseline/Closure/Review), igual que
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


def _has_submitted(doctype: str, project: str) -> bool:
	"""¿Existe un documento SUBMITTED de `doctype` para el Project? Guardado si el DocType aún no existe."""
	if not frappe.db.exists("DocType", doctype):
		return False
	return bool(frappe.db.exists(doctype, {"project": project, "docstatus": 1}))


def derive_lifecycle_state(project: str) -> str:
	"""Estado documental derivado (precedencia: el más avanzado gana). No modifica nada.

	reviewed → closed → closing (Completed sin Closure) → execution (baseline vigente) → planning (Charter
	emitido) → initiation. Cancelled/On hold no crean estado propio: se derivan de sus artefactos/baseline.
	"""
	from pmo.baseline import get_effective_baseline

	if _has_submitted("PMO Post-Project Review", project):
		return LIFECYCLE_REVIEWED
	if _has_submitted("PMO Project Closure", project):
		return LIFECYCLE_CLOSED
	if frappe.db.get_value("Project", project, "status") == "Completed":
		return LIFECYCLE_CLOSING
	if get_effective_baseline(project):
		return LIFECYCLE_EXECUTION
	if _has_submitted("PMO Project Charter", project):
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
	contenido. Charter/Baseline reales; Closure/Review como pendientes hasta su bloque. Change Requests =
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
		"charter": _artifact("PMO Project Charter", project, "charter_date"),
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
