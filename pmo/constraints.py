# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Schedule Constraints — write-path acotado (ADR-0018, II.1 · SNET).

Frontera: este módulo **sí muta** el forecast de la Task que se está guardando (a diferencia de
`pmo/scheduling.py`, que es estrictamente read-only). Pero **solo** normaliza la **propia** Task y **nunca**
busca ni mueve sucesoras: ERPNext sigue siendo el ÚNICO propagador FS (`Task.on_update →
reschedule_dependent_tasks`). Se engancha en `before_validate` (doc_event) para que las validaciones nativas
de coherencia (`validate_from_to_dates`) corran sobre la fecha ya corregida; muta en memoria y **no** llama
`save()` (evita doble cascada/recursión).

SNET (Start No Earlier Than): si la Task es elegible y su `exp_start_date` cae **antes** del
`pmo_constraint_date`, se desplaza el inicio a esa fecha **preservando la hora original** y se conserva la
**duración en días naturales** (`date_diff`, igual que el core). Solo empuja hacia adelante.

Elegibilidad para mutación (ADR-0018): NO muta si la Task está iniciada (`act_start_date` presente — señal
canónica), es `Completed`/`Cancelled`, es grupo (`is_group`) o es hito (`is_milestone`). No-op seguro si
falta tipo o fecha de constraint (nunca inventa el dato). FNLT se almacena pero su diagnóstico es II.2 (aquí
no actúa). MSO/MFO fuera.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, getdate

SNET = "Start No Earlier Than (SNET)"
FNLT = "Finish No Later Than (FNLT)"  # modelo previsto (ADR-0018); diagnóstico en II.2, no actúa en II.1

_INELIGIBLE_STATUS = ("Completed", "Cancelled")


def compute_snet_start_end(exp_start, exp_end, snet):
	"""Núcleo PURO y testeable (sin BD): dado el inicio/fin actuales y la fecha SNET, devuelve
	`(new_start, new_end)` si hay que desplazar, o `None` si no aplica.

	Reglas: SNET solo empuja hacia ADELANTE (si `getdate(exp_start) >= getdate(snet)` → None). Conserva la
	duración en **días naturales** (`date_diff`, igual que el core) y **preserva la hora original** de
	`exp_start`. No-op (None) si falta cualquier dato."""
	if not exp_start or not exp_end or not snet:
		return None
	start_dt = get_datetime(exp_start)
	if getdate(start_dt) >= getdate(snet):
		return None
	duration = date_diff(exp_end, exp_start)  # días naturales (puede ser 0)
	# Fecha = SNET; hora = la original del exp_start (SNET = "no antes de este día", no "a medianoche").
	new_start = datetime.combine(getdate(snet), start_dt.time())
	new_end = add_days(new_start, duration)  # add_to_date preserva la componente horaria
	return new_start, new_end


def _is_eligible(doc) -> bool:
	"""Elegible para mutación SNET (ADR-0018). `act_start_date` = evidencia canónica de inicio."""
	if doc.get("act_start_date"):
		return False
	if doc.get("status") in _INELIGIBLE_STATUS:
		return False
	if doc.get("is_group"):
		return False
	if doc.get("is_milestone"):
		return False
	return True


def apply_start_constraint(doc, method=None):
	"""doc_event `before_validate` de Task: normaliza SNET sobre la PROPIA Task. Muta en memoria; no llama
	`save()`; no recorre sucesoras; sin `msgprint` (evita ruido en los saves recursivos de la cascada). No-op
	seguro si no hay constraint SNET aplicable."""
	if doc.get("pmo_constraint_type") != SNET:
		return  # FNLT/MSO/MFO/vacío: no actúa en II.1
	if not _is_eligible(doc):
		return
	shift = compute_snet_start_end(
		doc.get("exp_start_date"), doc.get("exp_end_date"), doc.get("pmo_constraint_date")
	)
	if not shift:
		return
	doc.exp_start_date, doc.exp_end_date = shift
	# Marca para el aviso final (lo emite notify_start_constraint en on_update, no aquí: sin msgprint en
	# before_validate para no hacer ruido en los saves recursivos de la cascada).
	doc.flags.pmo_snet_shift = str(getdate(shift[0]))


def notify_start_constraint(doc, method=None):
	"""doc_event `on_update`: aviso NO bloqueante si SNET movió el inicio en este save. Se muestra solo para
	la Task editada directamente, NO para las sucesoras movidas por la cascada nativa (que llevan
	`flags.ignore_recursion_check`), evitando una lluvia de mensajes durante la propagación."""
	if not doc.flags.get("pmo_snet_shift") or doc.flags.get("ignore_recursion_check"):
		return
	frappe.msgprint(
		# Fecha en ISO (str) — NO format_date: depende del locale y, con la sesión sin idioma (consola/jobs),
		# lanzaría, convirtiendo este aviso suave en un bloqueo.
		_(
			"The start was moved to {0} to honor the Start No Earlier Than (SNET) constraint; duration preserved."
		).format(doc.flags.pmo_snet_shift),
		title=_("Schedule constraint applied"),
		indicator="blue",
	)
