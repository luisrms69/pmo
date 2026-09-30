# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Settings (Single) — calibración mínima del PHI capturable por PMO Manager (ADR-0013a).

Solo expone los **pesos de dimensión** del PHI. Governance se **calcula** (`100 - Execution - Schedule`),
no se captura. Thresholds, bandas, caps y demás calibración permanecen versionados en código
(`pmo/health.py`); este Single NO es un catálogo general de parámetros."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

_EXECUTION_DEFAULT = 50
_SCHEDULE_DEFAULT = 35


class PMOSettings(Document):
	def validate(self):
		exe = cint(self.execution_weight)
		sch = cint(self.schedule_weight)
		if exe <= 0 or sch <= 0:
			frappe.throw(_("Execution and Schedule weights must be greater than 0."))
		if exe + sch >= 100:
			frappe.throw(_("Execution + Schedule must be less than 100 so Governance stays greater than 0."))
		# Governance es calculado, nunca capturado.
		self.governance_weight = 100 - exe - sch


def get_phi_weights() -> dict:
	"""Pesos del PHI desde PMO Settings, con fallback a los defaults versionados si el Single no existe
	o no es válido. Devuelve {execution, schedule, governance} que suma 100."""
	from pmo.health import PHI_WEIGHTS

	try:
		doc = frappe.get_cached_doc("PMO Settings")
		exe = cint(doc.execution_weight)
		sch = cint(doc.schedule_weight)
		gov = cint(doc.governance_weight) or (100 - exe - sch)
		if exe > 0 and sch > 0 and gov > 0 and exe + sch + gov == 100:
			return {"execution": exe, "schedule": sch, "governance": gov}
	except Exception:
		frappe.logger("pmo").warning("PMO Settings no disponible; PHI usa pesos por defecto")
	return dict(PHI_WEIGHTS)
