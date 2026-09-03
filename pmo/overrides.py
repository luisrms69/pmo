# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 Incremento 4 — cierre de vectores que se saltan `pqc` (ADR-0002).

`create_duplicate_project` (whitelisted, ERPNext) recibe `prev_doc` (JSON) del cliente y hace
`frappe.get_all("Task", filters={"project": prev_doc["name"]})` — que fuerza `ignore_permissions=True`
y por tanto **ignora `pqc`/`has_permission`**. Sin control, un usuario que **conozca/adivine el nombre**
de un Project confidencial puede duplicarlo y **exfiltrar todas sus Tasks** a un proyecto que él posee.

Mitigación (upgrade-safe): envolver el método vía `override_whitelisted_methods` y exigir permiso de
**lectura** sobre el Project origen antes de delegar en el método nativo. Si el usuario no puede leer el
origen (no es owner/member/executive/Administrator), se lanza `PermissionError`.
"""

import json

import frappe


@frappe.whitelist()
def create_duplicate_project(prev_doc, project_name):
	"""Override P0: valida READ sobre el Project origen y delega en el método nativo de ERPNext."""
	data = json.loads(prev_doc) if isinstance(prev_doc, str) else prev_doc
	source = (data or {}).get("name")
	if source and frappe.db.exists("Project", source):
		# throw=True → PermissionError si el usuario no puede leer el Project origen (aplica has_permission).
		frappe.has_permission("Project", ptype="read", doc=source, throw=True)

	from erpnext.projects.doctype.project.project import (
		create_duplicate_project as _native,
	)

	return _native(prev_doc, project_name)
