# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Risk (ADR-0014 D6) — registro vivo de riesgos del Project.

Capa ligera y cualitativa (ISO 31000 / PMBOK): identificación, evaluación cualitativa, responsable,
respuesta, seguimiento. **No submittable** (es un registro vivo, se actualiza durante la ejecución);
`track_changes` conserva el historial. La `exposure` se **deriva** de la matriz probabilidad x impacto
(no se captura ni se persiste un score numérico). P4 heredado del Project (ver `pmo.permissions`).

No es un subsistema: una respuesta que requiera modificar una condición controlada del Project
(alcance/fecha/baseline/economía/compromiso) se enruta por `PMO Change Request` (campo `change_request`),
nunca por un mecanismo de aprobación propio.
"""

import frappe
from frappe.model.document import Document

# Matriz cualitativa 3x3 simetrica probabilidad x impacto -> exposicion (ADR-0014 D6).
_LEVELS = ("Low", "Medium", "High")
_EXPOSURE_MATRIX = {
	("Low", "Low"): "Low",
	("Low", "Medium"): "Low",
	("Low", "High"): "Medium",
	("Medium", "Low"): "Low",
	("Medium", "Medium"): "Medium",
	("Medium", "High"): "High",
	("High", "Low"): "Medium",
	("High", "Medium"): "High",
	("High", "High"): "High",
}


def derive_exposure(probability: str | None, impact: str | None) -> str | None:
	"""Exposición cualitativa derivada; None si falta probabilidad o impacto. Fuente única de la regla."""
	if probability in _LEVELS and impact in _LEVELS:
		return _EXPOSURE_MATRIX[(probability, impact)]
	return None


class PMOProjectRisk(Document):
	def validate(self):
		# `exposure` es siempre derivada (read_only en UI); se recalcula en servidor, nunca se confía en el input.
		self.exposure = derive_exposure(self.probability, self.impact)
