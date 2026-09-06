# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Integración de Change Control con `erpnext_proposals` (ADR-0005).

Frontera dura: `pmo` **no** reproduce ni puentea la lógica de `erpnext_proposals`. La aplicación de un
addendum a un Project existente se **delega** al contrato acordado
`apply_addendum_to_project(quotation, project)` de `erpnext_proposals`, que es el único responsable de
validar (Ganada, docstatus, superseded, single-live, customer/company), **escribir `proposal_project`** y
anexar los Scope Items como Tasks (reuse + dedup). `pmo` nunca escribe `proposal_project` ni copia esos
guards.

Este módulo aísla el punto de integración para poder probarlo con el contrato mockeado mientras el helper
todavía no existe en `erpnext_proposals` (ciclo Git separado, con su propia autorización).
"""

import frappe
from frappe import _

# Contrato acordado (vive en erpnext_proposals, ruta canónica junto a create_project_from_quotation).
ADDENDUM_APPLIER = "erpnext_proposals.erpnext_proposals.utils.project.apply_addendum_to_project"


def apply_addendum_to_project(quotation: str, project: str):
	"""Delega en el contrato de `erpnext_proposals`. Devuelve lo que devuelva el helper (resumen del
	append). Lanza un error claro si la integración aún no está disponible en el entorno.

	NO valida reglas comerciales ni escribe `proposal_project`: eso es responsabilidad exclusiva del
	helper de `erpnext_proposals`.
	"""
	try:
		fn = frappe.get_attr(ADDENDUM_APPLIER)
	except Exception:
		frappe.throw(
			_(
				"La integración con erpnext_proposals no está disponible: falta el helper "
				"{0}. Actualiza erpnext_proposals (ciclo aparte) antes de aplicar la Cotización al Project."
			).format("apply_addendum_to_project(quotation, project)")
		)
	return fn(quotation, project)
