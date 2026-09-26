# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 (i18n género): migra los tokens de probability/exposure a los tokens propios de pmo.

`Low/Medium/High` genéricos se heredaban de erpnext en masculino y no permitían género femenino para
Probabilidad/Exposición. Ahora probability usa `... likelihood` y exposure `... exposure` (tokens propios de pmo,
traducibles a femenino). Impact conserva `Low/Medium/High` (masculino, correcto). Este patch reetiqueta los datos
existentes. Idempotente: tras migrar, los valores ya no coinciden con los antiguos → no-op. NO toca `impact`.
"""

import frappe

_PROBABILITY = {
	"Low": "Low likelihood",
	"Medium": "Medium likelihood",
	"High": "High likelihood",
}
_EXPOSURE = {
	"Low": "Low exposure",
	"Medium": "Medium exposure",
	"High": "High exposure",
}

# probability/exposure viven en estos DocTypes (parent risk + item del assessment).
_DOCTYPES = ("PMO Project Risk", "PMO Project Risk Item")


def _remap(doctype: str, field: str, mapping: dict):
	if not frappe.db.table_exists(doctype):
		return
	for old, new in mapping.items():
		frappe.db.sql(  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-sql-format-injection
			f"update `tab{doctype}` set `{field}` = %s where `{field}` = %s",
			(new, old),
		)


def execute():
	for dt in _DOCTYPES:
		_remap(dt, "probability", _PROBABILITY)
		_remap(dt, "exposure", _EXPOSURE)
