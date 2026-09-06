# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Change Request (ADR-0005). Contenedor de gobernanza del cambio: submittable, con impacto
estructurado minimo, decision del owner fijada al aprobar (Submit) y enlaces a la Quotation-addendum y a
las baselines before/after.

Alcance de este bloque (Bloque 2): esquema + invariantes BASE independientes del Workflow (defaults,
`impact_summary`, moneda, integridad de baselines, aprobacion en Submit, guard de cancel). El Workflow, el
gate de baseline vigente al formalizar (`En revision`), la congelacion de `baseline_before`, la accion
"Aplicar Quotation al Project" y la semantica Aplicado/Implementado llegan en el Bloque 3.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

# Etiquetas del resumen de impacto (para el Change Register). Orden estable.
_IMPACT_LABELS = (
	("impacts_scope", "Alcance"),
	("impacts_schedule", "Cronograma"),
	("impacts_effort", "Esfuerzo/Recursos"),
	("impacts_commercial", "Comercial"),
	("impacts_risk", "Riesgo"),
)


class PMOChangeRequest(Document):
	def validate(self):
		self._set_defaults()
		self._compute_impact_summary()
		self._set_currency_default()
		self._validate_baseline_integrity()

	# --- defaults ------------------------------------------------------------------

	def _set_defaults(self):
		if not self.raised_by:
			self.raised_by = frappe.session.user
		if not self.request_date:
			self.request_date = today()
		if not self.priority:
			self.priority = "Media"  # default robusto (la ruta get_doc(dict) no aplica el default del schema)

	def _compute_impact_summary(self):
		marcados = [label for field, label in _IMPACT_LABELS if self.get(field)]
		self.impact_summary = ", ".join(marcados)

	def _set_currency_default(self):
		if self.currency or not self.project:
			return
		company = frappe.db.get_value("Project", self.project, "company")
		if company:
			self.currency = frappe.db.get_value("Company", company, "default_currency")

	# --- integridad de baselines (independiente del Workflow) ----------------------

	def _validate_baseline_integrity(self):
		"""Ambas baselines, si se indican, deben pertenecer al mismo Project del CR; `baseline_after` no
		puede ser igual a `baseline_before` y su `effective_date` no puede ser anterior (D5/D9)."""
		for fieldname in ("baseline_before", "baseline_after"):
			bl = self.get(fieldname)
			if bl and frappe.db.get_value("PMO Project Baseline", bl, "project") != self.project:
				frappe.throw(
					frappe._("{0} debe pertenecer al mismo Project del Change Request.").format(
						frappe.bold(self.meta.get_label(fieldname))
					)
				)

		if self.baseline_before and self.baseline_after:
			if self.baseline_before == self.baseline_after:
				frappe.throw(frappe._("Baseline After no puede ser igual a Baseline Before."))
			eb = frappe.db.get_value("PMO Project Baseline", self.baseline_before, "effective_date")
			ea = frappe.db.get_value("PMO Project Baseline", self.baseline_after, "effective_date")
			if eb and ea and getdate(ea) < getdate(eb):
				frappe.throw(
					frappe._("Baseline After no puede ser efectiva antes que Baseline Before ({0}).").format(
						eb
					)
				)

	# --- aprobacion fijada al Submit (D6/D10) --------------------------------------

	def before_submit(self):
		"""Aprobar/Rechazar el CR = Submit (la autoridad owner-only la sella P4 sobre `submit`). Se registra
		quien aprueba y cuando. El contenido de la solicitud queda inmutable (no `allow_on_submit`)."""
		if not self.approved_by:
			self.approved_by = frappe.session.user
		if not self.approved_at:
			self.approved_at = now_datetime()

	# --- cancel: escape controlado (D10) -------------------------------------------

	def before_cancel(self):
		"""Cancelar es "retirar" un CR aun no materializado. Bloqueado si el cambio ya se aplico al Project
		(`applied_to_project`) o si el CR ya se cerro con una nueva baseline (`baseline_after`): en esos
		casos la realidad/baseline ya cambio y revertir exige un CR nuevo.
		Nota: el bloqueo por estado terminal `Rechazado`/`Cerrado` del Workflow se anade en el Bloque 3."""
		if self.applied_to_project:
			frappe.throw(
				frappe._(
					"No se puede cancelar: el cambio ya fue aplicado al Project. Registra un Change Request nuevo para revertirlo."
				)
			)
		if self.baseline_after:
			frappe.throw(
				frappe._("No se puede cancelar: el Change Request ya se cerro con una nueva baseline.")
			)
