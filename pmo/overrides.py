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
def create_duplicate_project(prev_doc: str, project_name: str):
	"""Override P0: valida READ sobre el Project origen y delega en el método nativo de ERPNext.

	`prev_doc` llega como str (JSON) desde el cliente; se acepta dict por robustez.
	"""
	data = json.loads(prev_doc) if isinstance(prev_doc, str) else prev_doc
	source = (data or {}).get("name")
	if source and frappe.db.exists("Project", source):
		# throw=True → PermissionError si el usuario no puede leer el Project origen (aplica has_permission).
		frappe.has_permission("Project", ptype="read", doc=source, throw=True)

	from erpnext.projects.doctype.project.project import (
		create_duplicate_project as _native,
	)

	return _native(prev_doc, project_name)


class PMOTaskScheduleMixin:
	"""ADR-0004 (D1/D2/D3) — Schedule Governance sobre `Task` via `extend_doctype_class`.

	Redefine EXCLUSIVAMENTE las dos validaciones de fecha cuya semantica cambiamos y deja `validate_dates()`
	y todo lo demas nativo. Se compone por MRO (el mixin precede a `Task`), y como `Task.validate_dates()`
	invoca estos metodos via `self.<m>()` (task.py:98-99), nuestras versiones ganan sin tocar
	`validate_dates()` (que sigue heredando cualquier validacion nueva de upstream).

	Semantica PMO:
	- `validate_parent_expected_end_date`: las fechas de un summary/parent (`is_group`) son un envelope NO
	  vinculante; una hija PUEDE extenderse mas alla del padre. No se bloquea.
	- `validate_parent_project_dates`: `Project.expected_*` es forecast, no limite duro; en particular el
	  Actual (`act_start_date`/`act_end_date`, derivados de Timesheet) NUNCA se bloquea por el fin
	  planificado del Project.

	No copiamos el cuerpo nativo (que ademas difiere entre 16.32.1 y upstream `7b0df4b`): lo sustituimos por
	nuestra semantica -> independiente de version. La coherencia inicio<=fin (`validate_from_to_dates`) y el
	resto de validaciones nativas permanecen intactas. Un guard de drift en `test_schedule_governance`
	falla si `Task` deja de definir estos metodos (habria que re-evaluar).
	"""

	def validate_parent_expected_end_date(self):
		# PMO: summary/parent = envelope no vinculante (ADR-0004 D1). No bloquear.
		return

	def validate_parent_project_dates(self):
		# PMO: Project.expected_* = forecast; el Actual nunca se bloquea (ADR-0004 D2/D3). No bloquear.
		return
