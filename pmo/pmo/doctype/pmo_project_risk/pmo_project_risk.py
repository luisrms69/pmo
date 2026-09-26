# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Risk (ADR-0016 R1) — entrada VIVA del Risk Register.

Entidad persistente por riesgo, con identidad propia (`PMO-RISK-.#####`), que evoluciona durante la ejecución:
probability/impact/exposure (exposure DERIVADA server-side, matriz 3x3), owner, response/treatment y status
(Open/Managing/Closed/Materialized; sin workflow). La alimenta el `PMO Project Risk Assessment` (prompts
aplicables) o se crea a mano (riesgo no anticipado). NO submittable; P4 heredado del Project.
`may_affect_controlled` es SOLO señal (Risk ≠ Change Control; no crea CR).

**Historia (Opción E):** NO se mantiene una historia paralela. `track_changes=1` + el DocType nativo `Version`
son la fuente de verdad de QUÉ cambió (old → new), QUIÉN y CUÁNDO, y se consultan en el Timeline nativo. Lo único
que Frappe no cubre es el MOTIVO funcional obligatorio del cambio: se resuelve con el campo transitorio
`update_note` (obligatorio ante cambio material) que, tras un save exitoso, se publica como **Comment nativo** en
el Timeline del mismo Risk. `exposure` es derivada y NO cuenta como cambio material por sí sola.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from pmo.risk_matrix import derive_exposure

# Campos MATERIALES: su cambio en un Risk existente EXIGE Nota de actualización (motivo). `exposure` NO es trigger
# (es derivada de probability x impact). El registro de QUÉ cambió lo hace `Version` (track_changes) nativamente.
_MATERIAL_FIELDS = (
	"description",
	"probability",
	"impact",
	"status",
	"risk_owner",
	"response",
	"may_affect_controlled",
)


class PMOProjectRisk(Document):
	def before_insert(self):
		if not self.identified_on:
			self.identified_on = today()
		if not self.status:
			self.status = "Open"

	def validate(self):
		# `project` inmutable: lo impone el helper compartido vía doc_events (pmo.project_link).
		# Riesgo manual = sin pregunta de catálogo de origen.
		self.is_manual = 0 if self.source_question_code else 1
		if not (self.description or "").strip():
			frappe.throw(_("A risk description is required."), title=_("Missing risk description"))
		# exposure SIEMPRE derivada server-side (read_only en UI); nunca del cliente.
		self.exposure = derive_exposure(self.probability, self.impact)
		# Ante cambio material en un Risk existente, exige el motivo (Frappe no lo captura nativamente). El motivo
		# se captura en un flag y el campo se limpia AQUÍ (se persiste vacío en este mismo save); el Comment se
		# publica en on_update. Se evita `db_set` post-save (que provoca TimestampMismatchError).
		self._prepare_update_note()

	def on_update(self):
		# Tras un save exitoso con cambio material: publica el motivo como Comment nativo en el Timeline del mismo
		# Risk (junto al Version que ya registró old → new). Una sola nota → un solo Comment.
		note = self.flags.get("pmo_update_note")
		if note:
			self.add_comment("Comment", note)

	def _prepare_update_note(self):
		"""En la creación NO se exige nota (la identificación queda en `identified_on`/origen + evento de creación
		nativo). En un Risk existente, si cambió algún campo material, `update_note` es obligatorio; se guarda en
		un flag para publicarlo como Comment en on_update y el campo transitorio se limpia (se persiste vacío)."""
		self.flags.pmo_update_note = None
		before = self.get_doc_before_save()
		if before is None:
			self.update_note = None  # creación inicial: sin nota manual
			return
		changed = any((before.get(f) or None) != (self.get(f) or None) for f in _MATERIAL_FIELDS)
		if not changed:
			self.update_note = None  # descarta nota si no hubo cambio material
			return
		note = (self.update_note or "").strip()
		if not note:
			frappe.throw(
				_("Provide an Update note explaining why the risk changed."),
				title=_("Update note required"),
			)
		self.flags.pmo_update_note = note
		self.update_note = None  # transitorio: se persiste vacío en este save

	def on_trash(self):
		# Si el riesgo provino de un item del Assessment, libera el vínculo para que pueda re-generarse si el
		# prompt sigue aplicando (idempotencia de la generación).
		if self.source_item and frappe.db.exists("PMO Project Risk Item", self.source_item):
			frappe.db.set_value("PMO Project Risk Item", self.source_item, "risk", None)
