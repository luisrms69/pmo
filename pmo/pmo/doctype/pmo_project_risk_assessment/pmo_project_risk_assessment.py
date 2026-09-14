# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Risk Assessment (ADR-0014 Risk) — cuestionario cualitativo VIVO por Project.

Uno por Project (campo `project` unique). NO submittable; `track_changes=1` conserva el historial (no se
guardan múltiples assessments históricos). Cuestionario precargado con 6 preguntas fijas; el usuario solo
responde. `exposure` se deriva server-side (matriz cualitativa 3x3), nunca se acepta del cliente. La pregunta
"puede afectar condición controlada" es SOLO señal (no crea Change Request; ver ADR-0014 / PMO Change Request).

Alineación ligera con PMI/PMBOK e ISO 31000 (identificar / evaluar cualitativamente / responder / monitorear),
sin subsistema cuantitativo (sin scores, Monte Carlo, reservas, owners, fechas por riesgo, workflows).
"""

import frappe
from frappe.model.document import Document

# Cuestionario predefinido (código estable + texto canónico en inglés; i18n traduce en presentación).
RISK_QUESTIONS = (
	("Q1", "Are there external dependencies that could affect the project?"),
	("Q2", "Is there relevant uncertainty in scope or requirements?"),
	("Q3", "Are there critical resources whose availability could affect the project?"),
	("Q4", "Is there a relevant risk of schedule deviation?"),
	("Q5", "Is there a relevant risk of cost/economic deviation?"),
	("Q6", "Are there technical or integration risks?"),
)

# Matriz cualitativa 3x3 simetrica probabilidad x impacto -> exposicion (misma regla conceptual del diseño de Risk).
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


class PMOProjectRiskAssessment(Document):
	def before_insert(self):
		# Cuestionario precargado: el usuario responde preguntas fijas, no redacta riesgos desde cero.
		if not self.questions:
			for code, text in RISK_QUESTIONS:
				self.append("questions", {"question_code": code, "question": text, "applies": "No"})

	def validate(self):
		for row in self.questions or []:
			if row.applies == "Yes":
				# exposure SIEMPRE derivada server-side (read_only en UI); nunca se confía en el input.
				row.exposure = derive_exposure(row.probability, row.impact)
			else:
				# Probabilidad/Impacto/Exposición/Acción/condición solo aplican si Applies == Yes.
				row.probability = None
				row.impact = None
				row.exposure = None
				row.may_affect_controlled = None
				row.action = None
