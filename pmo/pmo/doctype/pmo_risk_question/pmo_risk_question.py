# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Risk Question (ADR-0016 Risk Analysis R1) — catálogo administrable de prompts de identificación.

Master global (no ligado a Project, sin P4): el administrador gestiona las preguntas como data. Cada pregunta
es un PROMPT de aplicabilidad (sí/no), no el riesgo en sí; cuando aplica, el equipo redacta el enunciado del
riesgo en el `PMO Project Risk Assessment`. La precarga del cuestionario toma un SNAPSHOT de code/texto/sección,
de modo que editar el catálogo después nunca altera assessments existentes. Las secciones viven como opciones
`Select` versionadas en el DocType (nunca Property Setter): añadir una sección es un cambio versionado de la app.

`sort_order` se autogenera en pasos de 10 dentro de la sección si se deja vacío (el admin puede fijarlo a mano
para reordenar). No es obligatorio.
"""

import frappe
from frappe.model.document import Document

_SORT_STEP = 10


class PMORiskQuestion(Document):
	def before_insert(self):
		# Si no se especifica orden, tomar el siguiente disponible en la sección (pasos de 10). El admin
		# puede fijarlo manualmente para reordenar; no es trabajo administrativo obligatorio.
		if not self.sort_order:
			self.sort_order = self._next_sort_order()

	def _next_sort_order(self) -> int:
		"""Siguiente `sort_order` en la sección: máximo actual + 10 (o 10 si la sección está vacía)."""
		if not self.section:
			return _SORT_STEP
		rows = frappe.get_all(
			"PMO Risk Question",
			filters={"section": self.section},
			pluck="sort_order",
		)
		current_max = max((int(v or 0) for v in rows), default=0)
		return current_max + _SORT_STEP
