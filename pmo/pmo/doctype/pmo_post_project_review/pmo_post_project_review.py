# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Post-Project Review (ADR-0014 D5) — evaluación posterior del Project.

Distinto del Closure (Closure = *cómo terminó*, factual; Review = *qué aprendimos*, posterior/reflexivo).
Submittable + track_changes: al emitir se **congela** el contenido cualitativo evaluado + las lessons learned
como evidencia (snapshot canónico + hash, patrón Baseline). Proporcional (ISO 21513): pocos textos + child
`PMO Lessons Learned` (única parte estructurada, para reporting futuro de categorías/causas recurrentes).

Guard: solo se emite tras un Closure emitido (secuencia closed → post-project reviewed). Autosuficiente
(sin Risk); no toca PHI.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from pmo.baseline import canonical_json, snapshot_hash

REVIEW_SNAPSHOT_SCHEMA_VERSION = 1


def _base_closure(project: str) -> dict:
	"""Referencia + hash del Closure submitted que habilita la Review (trazabilidad de evidencia). Congela
	QUÉ cierre documental fue la base, de modo que una enmienda/cancelación posterior del Closure no rompa la
	trazabilidad. No duplica el Closure ni crea DocType nuevo."""
	row = frappe.get_all(
		"PMO Project Closure",
		filters={"project": project, "docstatus": 1},
		fields=["name", "snapshot_hash"],
		order_by="creation desc",
		limit=1,
	)
	if not row:
		return {"reference": None, "snapshot_hash": None}
	return {"reference": row[0]["name"], "snapshot_hash": row[0].get("snapshot_hash")}


def build_review_snapshot(doc) -> dict:
	"""Congela el contenido evaluado + lessons + trazabilidad (reviewed_by, Closure base) — evidencia
	inmutable de la revisión."""
	return {
		"snapshot_schema_version": REVIEW_SNAPSHOT_SCHEMA_VERSION,
		"review_date": str(doc.review_date) if doc.review_date else None,
		"reviewed_by": doc.reviewed_by,
		"based_on_closure": _base_closure(doc.project),
		"objectives_achieved": doc.objectives_achieved,
		"what_worked": doc.what_worked,
		"what_didnt": doc.what_didnt,
		"causes": doc.causes,
		"recommendations": doc.recommendations,
		"lessons": [
			{
				"area": r.area,
				"lesson": r.lesson,
				"recommended_action": r.recommended_action,
			}
			for r in (doc.lessons or [])
		],
	}


class PMOPostProjectReview(Document):
	def validate(self):
		# Una sola Review emitida por Project (las enmiendas reemplazan; la anterior queda cancelada).
		if not self.amended_from:
			existing = frappe.db.exists(
				"PMO Post-Project Review",
				{"project": self.project, "docstatus": 1, "name": ["!=", self.name or ""]},
			)
			if existing:
				frappe.throw(
					frappe._("This Project already has an issued Post-Project Review ({0}).").format(existing)
				)

	def before_submit(self):
		# Secuencia (ADR-0014 D5/D7): la revisión es posterior al cierre → exige un Closure emitido.
		if not frappe.db.exists("PMO Project Closure", {"project": self.project, "docstatus": 1}):
			frappe.throw(frappe._("Post-Project Review requires an issued Project Closure for this Project."))
		snapshot = build_review_snapshot(self)
		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		self.snapshot = canonical_json(snapshot)
		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()
