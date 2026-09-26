# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Enforcement server-side del orden de la Addenda (Change Control v2, ADR-0015 D7).

`pmo` intercepta las transiciones de workflow de la `Quotation` (hook sobre eventos `validate` y
`before_update_after_submit`, mismo patrón que `erpnext_proposals`, que corren ANTES del write) y **solo
permite o bloquea**: no modifica la Quotation ni el Change Request, no cambia de usuario, no eleva permisos
ni commitea. `erpnext_proposals` sigue ignorando al CR (dependencia `pmo → erpnext_proposals` intacta).

Frontera: `pmo` NO parsea `ROOT-ADD-NN`; localiza el CR por el campo `proposal_group` y consume el
fingerprint canónico vía `change_control` (que delega en `erpnext_proposals`). Regla gobernada (D7):

- Transición **desde `En Revision`**:
  - `→ Rechazada`: siempre permitida (salida limpia de rechazo; PMO no la automatiza, solo la permite).
  - cualquier otro avance (`→ Aprobada`): permitido **solo si** el CR está `Approved` **y** el fingerprint
    actual de la Quotation == `approved_delta_fingerprint`. Si no → **bloquear** (fail-closed): CR no
    aprobado, sin fingerprint aprobado, o delta divergente (exige `reapprove_addendum_version`).
- Transiciones que **no** parten de `En Revision` (p. ej. Borrador→En Revision, Aprobada→Enviada→Ganada) o
  Quotations sin CR asociado: PMO **no interviene**.

El gobierno del delta es SEMÁNTICO: no se exige `approved_addendum == quotation.name`; una nueva versión con
la MISMA huella puede avanzar (ADR-0015 gobierna el delta, no el ID técnico de versión).
"""

import frappe
from frappe import _

from pmo import change_control
from pmo.pmo.doctype.pmo_change_request.pmo_change_request import (
	ADDENDUM_REJECTED_STATE,
	ADDENDUM_REVIEW_STATE,
	APPROVED,
)


def enforce_change_control_order(doc, method=None):
	"""Hook `doc_events` de PMO sobre Quotation (validate / before_update_after_submit). Permite o bloquea
	la transición de workflow de una Addenda gobernada por un CR. No escribe nada."""
	group = doc.get("proposal_group")
	if not group:
		return  # Quotation normal (no addenda): PMO no interviene

	new_state = doc.get("workflow_state")
	old_state = doc.get_value_before_save("workflow_state") if hasattr(doc, "get_value_before_save") else None
	if not new_state or old_state == new_state:
		return  # no es una transición de workflow

	# PMO solo gobierna el paso que sale de `En Revision`; el resto no lo toca.
	if old_state != ADDENDUM_REVIEW_STATE:
		return

	crs = frappe.get_all(
		"PMO Change Request",
		filters={"proposal_group": group, "docstatus": ["!=", 2]},
		fields=["name", "workflow_state", "approved_delta_fingerprint"],
	)
	if not crs:
		return  # la Addenda no está gobernada por un CR → PMO no interviene
	if len(crs) > 1:
		frappe.throw(
			_(
				"Inconsistent Change Control state: more than one active Change Request references the "
				"Proposal Group {0}."
			).format(group)
		)
	cr = crs[0]

	# Salida limpia de rechazo: siempre permitida (PMO no la ejecuta, solo la deja pasar).
	if new_state == ADDENDUM_REJECTED_STATE:
		return

	# Cualquier otro avance desde `En Revision` (→ Aprobada) exige gobernanza aprobada + delta idéntico.
	if cr.workflow_state != APPROVED:
		frappe.throw(
			_(
				"The addendum cannot advance beyond 'In Review' until its Change Request ({0}) is Approved."
			).format(cr.name)
		)
	if not cr.approved_delta_fingerprint:
		frappe.throw(
			_(
				"The Change Request ({0}) has no approved delta fingerprint to authorize this addendum."
			).format(cr.name)
		)
	current_fp = change_control.get_addendum_delta_fingerprint(doc.name)
	if current_fp != cr.approved_delta_fingerprint:
		frappe.throw(
			_(
				"This addendum version's delta differs from the version approved in Change Request {0}. "
				"Reapprove the addendum version before advancing it."
			).format(cr.name)
		)
	# fingerprint idéntico al aprobado → avance permitido
