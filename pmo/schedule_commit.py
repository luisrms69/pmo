# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Fecha comprometida de cronograma (ADR-0007).

Distingue la fecha **planeada/calculada** (nativa: `Task.exp_end_date`, `Project.expected_end_date`, que se
desplazan con dependencias/reprogramación) de la fecha **comprometida** (compromiso de negocio/acordado, no
necesariamente contractual):

- `Task.pmo_deadline` — fecha límite/comprometida de la tarea.
- `Project.pmo_committed_end_date` — fecha comprometida de terminación del proyecto.

La fecha comprometida **no se desplaza automáticamente** con la reprogramación, pero **no es inmutable**:
puede cambiarse por edición explícita (decisión autorizada). Estas validaciones son **avisos suaves**
(coherentes con ADR-0004: fechas no vinculantes; el Actual/Timesheet nunca se bloquea): informan cuando la
fecha calculada excede el compromiso, sin bloquear el guardado. Campos vacíos = sin compromiso (sin aviso).

Alcance v0.8.0: solo estos dos campos + avisos. Constraints tipados (SNET/FNLT/MSO/MFO), auto-reprogramación,
Baseline/Status Date: fuera de alcance (diferidos).
"""

import frappe
from frappe import _
from frappe.utils import getdate

from pmo.permissions import _has_pmo_authority


def validate_task_deadline(doc, method=None):
	"""ADR-0007 D4: avisa (no bloquea) si el fin planeado de la Task excede su fecha comprometida."""
	deadline = doc.get("pmo_deadline")
	planned_end = doc.get("exp_end_date")
	if not deadline or not planned_end:
		return
	if getdate(planned_end) > getdate(deadline):
		# Fechas en ISO (str) — NO usar format_date: depende del locale y, con la sesión sin idioma
		# (consola / jobs de fondo), lanzaría, convirtiendo este aviso suave en un bloqueo (viola D4).
		frappe.msgprint(
			_("The planned end ({0}) exceeds the committed date (PMO Deadline: {1}).").format(
				getdate(planned_end), getdate(deadline)
			),
			title=_("Schedule commitment at risk"),
			indicator="orange",
		)


def validate_project_committed_end(doc, method=None):
	"""ADR-0007 D4: avisa (no bloquea) si el fin calculado del Project excede su fecha comprometida."""
	committed = doc.get("pmo_committed_end_date")
	planned_end = doc.get("expected_end_date")
	if not committed or not planned_end:
		return
	if getdate(planned_end) > getdate(committed):
		# Fechas en ISO (str) — NO usar format_date (dependiente de locale; ver validate_task_deadline).
		frappe.msgprint(
			_("The project's planned end ({0}) exceeds the committed date ({1}).").format(
				getdate(planned_end), getdate(committed)
			),
			title=_("Schedule commitment at risk"),
			indicator="orange",
		)


@frappe.whitelist()
def change_committed_end_date(project: str, new_date: str | None = None, reason: str | None = None) -> dict:
	"""Cambio posterior del compromiso vigente `Project.pmo_committed_end_date` (decisión PMO autorizada).

	Modelo deliberadamente simple, sin DocType/workflow/CR/rebaseline ni historial propio:
	- Handoff = compromiso INICIAL autorizado e inmutable (no se toca aquí).
	- Project.pmo_committed_end_date = compromiso VIGENTE (lo único que se actualiza).
	- Version = antes/después técnico (el Project no rastrea cambios nativamente → se registra explícito).
	- Comentario/Timeline = motivo humano (autor/fecha por metadata nativa del Comment).

	Toda obligatoriedad se valida SERVER-SIDE: ocultar el botón en la UI NO es control de permisos.
	"""
	if not project or not frappe.db.exists("Project", project):
		frappe.throw(_("El Project indicado no existe."))
	# P4: visibilidad del Project (lectura). La autoridad de escritura del compromiso se valida aparte.
	frappe.has_permission("Project", ptype="read", doc=project, throw=True)
	# Autoridad PMO transversal (reutiliza la autoridad canónica; no se inventa rol nuevo).
	if not _has_pmo_authority(frappe.session.user):
		frappe.throw(
			_("Solo una autoridad PMO (PMO Manager o System Manager) puede cambiar el Fin comprometido."),
			frappe.PermissionError,
		)

	current = frappe.db.get_value("Project", project, "pmo_committed_end_date")
	if not current:
		frappe.throw(
			_(
				"El Project no tiene un Fin comprometido vigente que modificar. Se establece al emitir el Acta de Inicio (Handoff)."
			)
		)
	if not new_date:
		frappe.throw(_("Indica la nueva fecha de Fin comprometido."))
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Indica el motivo del cambio."))
	if getdate(new_date) == getdate(current):
		frappe.throw(_("La nueva fecha debe ser diferente de la fecha comprometida actual."))

	old_str = str(getdate(current))
	new_str = str(getdate(new_date))

	# Actualiza SOLO el compromiso vigente. `db_set` persiste + actualiza modified/modified_by sin disparar
	# la validación completa del Project (evita efectos colaterales y el aviso suave de este mismo módulo).
	proj = frappe.get_doc("Project", project)
	proj.db_set("pmo_committed_end_date", getdate(new_date))

	# Trazabilidad técnica: el Project tiene track_changes=0, así que un save NO generaría Version. La
	# registramos explícitamente con el formato nativo de diff para que aparezca en Historia/Version.
	frappe.get_doc(
		{
			"doctype": "Version",
			"ref_doctype": "Project",
			"docname": project,
			"data": frappe.as_json({"changed": [["pmo_committed_end_date", old_str, new_str]]}),
		}
	).insert(ignore_permissions=True)

	# Motivo humano en el timeline del Project (autor = session user y fecha = metadata nativa del Comment).
	proj.add_comment(
		"Comment",
		_("Fin comprometido actualizado: {0} → {1}. Motivo: {2}").format(old_str, new_str, reason),
	)

	return {"project": project, "committed_end_date": new_str}
