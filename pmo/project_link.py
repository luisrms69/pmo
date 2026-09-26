# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Regla estructural compartida: el `project` de un documento PMO es INMUTABLE una vez creado.

Un documento pertenece al Project en que se creó y no puede trasladarse a otro (integridad, P4 heredado,
trazabilidad/orígenes y documentos derivados asumen un Project fijo). Complementa a `set_only_once` (UX) con
enforcement server-side que cubre form/API/script/import/save. Reutilizado por los DocTypes con Link estructural
a Project (vía `doc_events` en hooks) para evitar duplicar la lógica.
"""

import frappe
from frappe import _


def enforce_immutable_project(doc, method=None):
	"""Rechaza cambiar `project` en un documento existente. No-op en la creación (permite seleccionarlo)."""
	if doc.is_new():
		return
	before = doc.get_doc_before_save()
	if before and before.get("project") and before.get("project") != doc.get("project"):
		frappe.throw(_("The Project of this document cannot be changed."), title=_("Project is immutable"))
