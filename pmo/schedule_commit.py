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
