# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Post-Project Review (ADR-0014 D5) — evaluación posterior del Project.

Distinto del Closure (Closure = *cómo terminó*, factual; Review = *qué aprendimos*, posterior/reflexivo).
Submittable + track_changes: al emitir se **congela** el contenido cualitativo evaluado + las lessons learned
como evidencia (snapshot canónico + hash, patrón Baseline). Proporcional (ISO 21513): pocos textos + child
`PMO Lessons Learned` (única parte estructurada, para reporting futuro de categorías/causas recurrentes).

Guard: solo se emite tras un Closure emitido (secuencia closed → post-project reviewed). Autosuficiente
(sin Risk); no toca PHI.

Separación de capacidades (decisión de diseño):
- **Governance** = completar correctamente el ciclo del Project (Handoff → Baseline → Change Requests →
  Closure → Post-Project Review, + reserva de Risk). Vive en `pmo.governance` / `pmo.dashboard`. Termina al
  emitir el Review: `governance_flags.needs_review` pasa a False y el Project **deja de aparecer** en Pending
  Governance Actions. Las acciones de mejora **no** re-marcan al Project como pendiente de governance ni
  alteran su lifecycle.
- **Mejora continua** (capacidad SEPARADA, sección de dashboard futura, no en este bloque) = asegurar que las
  lessons con `recommended_action` produzcan cambios posteriores. Su unidad es la **acción** (no el Project),
  materializada como **ToDo nativo** (ver `on_submit`). Contrato de datos para construirla sin retrabajo:
  acción=`ToDo.description`, responsable=`ToDo.allocated_to`, fecha objetivo=`ToDo.date`,
  vencida=`date < hoy and status == "Open"`, Project de origen=`ToDo.reference_name` (este Review) → `.project`,
  vigencia=`status == "Open"` (Closed/Cancelled dejan de aparecer). Sin DocType de acciones, sin workflow, sin
  estados custom, sin scheduler.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from pmo.baseline import canonical_json, snapshot_hash

REVIEW_SNAPSHOT_SCHEMA_VERSION = 2


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
				"action_owner": r.action_owner,
				"target_date": str(r.target_date) if r.target_date else None,
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

		# Ciclo accionable: una lesson con `recommended_action` exige responsable y fecha (el
		# `mandatory_depends_on` marca el asterisco en la UI; esta validación server-side lo garantiza,
		# ya que en child tables no siempre se enforcea al guardar). Una lesson sin acción no requiere nada.
		for row in self.lessons or []:
			if row.recommended_action and not (row.action_owner and row.target_date):
				frappe.throw(
					frappe._(
						"Lesson '{0}': a Recommended action requires an Action owner and a Target date."
					).format(row.lesson or row.area or "")
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

	def on_submit(self):
		# Cierre del ciclo de lessons learned: cada lesson con `recommended_action` genera un ToDo NATIVO de
		# Frappe (sin subsistema paralelo). El estado/cierre de la acción viven en el ToDo; el Review queda
		# inmutable y su snapshot no rastrea la ejecución posterior. `action_owner`/`target_date` están
		# garantizados por `mandatory_depends_on` cuando hay `recommended_action`.
		for row in self.lessons or []:
			if not row.recommended_action:
				continue
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": row.action_owner,
					"date": row.target_date,
					"description": row.recommended_action,
					"reference_type": self.doctype,
					"reference_name": self.name,
				}
			).insert(ignore_permissions=True)
