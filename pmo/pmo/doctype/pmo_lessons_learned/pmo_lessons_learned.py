# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Lessons Learned (ADR-0014 D5) — child table del Post-Project Review.

Estructura mínima para habilitar reporting futuro (categorías/causas recurrentes) sin volver el Review un
cuestionario extenso. Sin lógica propia (child de un submittable congelado al submit)."""

from frappe.model.document import Document


class PMOLessonsLearned(Document):
	pass
