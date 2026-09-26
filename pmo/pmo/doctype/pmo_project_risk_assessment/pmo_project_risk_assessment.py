# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Risk Assessment (ADR-0016 R1, modelo definitivo) — cribado/identificación VIVO por Project.

Uno por Project (`project` unique + **inmutable** una vez creado), NO submittable, vivo/reevaluable durante el
proyecto. El workflow usa el **Guardar nativo de Frappe** (sin acciones/botones extra):

Al guardar, el Save **sincroniza únicamente identificaciones nuevas todavía no materializadas**:
- filas `Applies = No` no generan Risk;
- una fila `Applies = Yes` que ya tiene `item.risk` NO regenera ni modifica el `PMO Project Risk` existente;
- una fila `Applies = Yes` **completa** y sin `item.risk` genera su `PMO Project Risk` (riesgo nuevo);
- filas manuales nuevas siguen el mismo principio; idempotente (clave `item.risk`) → guardar repetido no duplica.

Antes de generar, una fila `Applies = Yes` debe estar **completa** (description + probability + impact); la
validación server-side impide guardar una identificación incompleta. `exposure` se deriva server-side (nunca
captura manual). Tras generarse, el *as-identified* del item queda congelado; la evolución ocurre EXCLUSIVAMENTE
en `PMO Project Risk`. El cuestionario se precarga desde `PMO Risk Question` (activas) con SNAPSHOT.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from pmo.risk_matrix import derive_exposure  # re-exportado para compatibilidad de imports

# Campos mínimos obligatorios para constituir una identificación válida (y crear un PMO Project Risk correcto).
_REQUIRED_WHEN_APPLIES = (
	("description", "Risk description"),
	("probability", "Probability"),
	("impact", "Impact"),
)


def get_active_catalog_questions() -> list:
	"""Preguntas activas del catálogo `PMO Risk Question`, ordenadas por sección y `sort_order`. Fuente de la
	precarga (se snapshotean en el assessment; el catálogo no vuelve a consultarse después del insert)."""
	return frappe.get_all(
		"PMO Risk Question",
		filters={"active": 1},
		fields=["name as question_code", "question", "section"],
		order_by="section asc, sort_order asc, name asc",
	)


class PMOProjectRiskAssessment(Document):
	def before_insert(self):
		# Precarga desde el catálogo: snapshot de code/texto/sección. Si el catálogo está vacío, el assessment
		# nace sin filas de catálogo (el equipo puede añadir riesgos manuales). No se re-precarga en saves.
		if not self.questions:
			for q in get_active_catalog_questions():
				self.append(
					"questions",
					{
						"question_code": q.question_code,
						"question": q.question,
						"section": q.section,
						"applies": "No",
					},
				)

	def validate(self):
		# `project` inmutable: lo impone el helper compartido vía doc_events (pmo.project_link).
		for row in self.questions or []:
			# Riesgo manual = fila sin code de catálogo (escape hatch para riesgos no anticipados).
			row.is_manual = 0 if row.question_code else 1
			if row.applies == "Yes":
				# Identificación válida = campos mínimos completos (impide guardar una fila incompleta). Se
				# impone server-side además del `mandatory_depends_on` de la UI (que en child tables no basta).
				for fieldname, label in _REQUIRED_WHEN_APPLIES:
					if not (str(row.get(fieldname) or "").strip()):
						frappe.throw(
							_("Row #{0}: {1} is required when the risk applies.").format(row.idx, _(label)),
							frappe.MandatoryError,
							title=_("Incomplete risk identification"),
						)
				# exposure as-identified SIEMPRE derivada server-side (read_only en UI); nunca del cliente.
				row.exposure = derive_exposure(row.probability, row.impact)
			else:
				# Sin aplicar: se limpian los campos de identificación (rating y enunciado).
				row.probability = None
				row.impact = None
				row.exposure = None
				row.may_affect_controlled = None
				row.description = None

	def on_update(self):
		# El Save sincroniza SOLO identificaciones nuevas todavía no materializadas (idempotente).
		self._generate_risks()

	def _generate_risks(self):
		"""Materializa `PMO Project Risk` para cada item aplicable que aún no tenga riesgo. Idempotente (clave por
		`item.risk` / origen `(assessment, source_item)`): guardar repetido no duplica ni toca Risks existentes."""
		for row in self.questions or []:
			if row.applies != "Yes" or row.risk:
				continue
			# Idempotencia adicional: por si el link del item no está sincronizado, buscar por origen.
			existing = frappe.db.get_value(
				"PMO Project Risk",
				{"assessment": self.name, "source_item": row.name},
				"name",
			)
			if existing:
				frappe.db.set_value("PMO Project Risk Item", row.name, "risk", existing)
				row.risk = existing
				continue
			risk = frappe.get_doc(
				{
					"doctype": "PMO Project Risk",
					"project": self.project,
					"assessment": self.name,
					"source_item": row.name,
					"source_question_code": row.question_code,
					"source_section": row.section,
					"description": row.description,
					"probability": row.probability,
					"impact": row.impact,
					"may_affect_controlled": row.may_affect_controlled,
					"status": "Open",
					"identified_on": today(),
				}
			).insert(ignore_permissions=True)
			# Fija el vínculo directamente (no re-dispara el save del Assessment).
			frappe.db.set_value("PMO Project Risk Item", row.name, "risk", risk.name)
			row.risk = risk.name
