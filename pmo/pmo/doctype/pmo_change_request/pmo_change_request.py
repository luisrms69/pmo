# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Change Request (ADR-0005). Contenedor de gobernanza del cambio: submittable + Workflow nativo,
con impacto estructurado mínimo, decisión del owner fijada al aprobar (Submit) y enlaces a la
Quotation-addendum y a las baselines before/after.

Semántica de estados (Workflow `PMO Change Request`):
    Draft → In Review → Approved / Rejected → Implemented → Closed

Flujo único addenda-céntrico (ADR-0015):
- Al pasar a **In Review** (formalizar): gate duro de baseline vigente + congelado de `baseline_before`
  **y** Addenda ya creada (`proposal_group`); no existe ruta paralela "sin Addenda" (B4).
- **Aprobar** = Submit que aterriza en `Approved`: captura server-side `approved_addendum` +
  `approved_delta_fingerprint` (versión viva `En Revision` + huella canónica de `erpnext_proposals`),
  fail-closed, y fija `approved_by`/`approved_at` (B5). **Rechazar** también es Submit pero NO es
  aprobación: no captura ni marca aprobación. `before_submit` es además red de seguridad de los gates.
- **Reapprove addendum version** (acción explícita, no transición): cuando se emite una versión divergente,
  el Project Owner re-aprueba y se actualiza `approved_addendum`/`approved_delta_fingerprint` sin cambiar
  el workflow ni `applied_*` (B5).
- **Marcar Implementado**: transición Approved→Implemented; gate: `implementation_owner` + Addenda
  (`proposal_group`) + `applied_to_project`. `impacts_commercial` es solo clasificación informativa.
- **Cerrar**: transición Implemented→Closed; gate: `baseline_after` (fijada por una Baseline `Approved
  Change` que referencia el CR) + `stakeholder_communication`.
- El **apply** gobernado (deriva la versión Ganada + guard de fingerprint) es B6; no vive aquí todavía.
"""

import frappe
from frappe import N_
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime, today

from pmo import change_control

# Estados del Workflow (valor canónico en inglés; DEBEN coincidir EXACTAMENTE con workflow.json /
# workflow_state.json). N_() los marca para extracción al POT sin traducirlos en runtime (es no-op): la
# lógica compara estos valores estables y el es.po aporta el español mostrado (translated_doctype).
DRAFT = N_("Draft")
IN_REVIEW = N_("In Review")
APPROVED = N_("Approved")
REJECTED = N_("Rejected")
IMPLEMENTED = N_("Implemented")
CLOSED = N_("Closed")
_TERMINAL_STATES = (REJECTED, CLOSED)

# Estado del workflow "Propuesta Comercial" (erpnext_proposals) en el que la Addenda está congelada
# (docstatus 1) y lista para gobernarse. Valor EXACTO del fixture (sin acento).
ADDENDUM_REVIEW_STATE = "En Revision"

# Workflow Action labels (canónicos en inglés, definidos en workflow.json). Solo marcados para
# extracción (N_ es no-op): el motor de Workflow compara estos valores; el es.po da el español visible.
_WORKFLOW_ACTIONS = (
	N_("Send for Review"),
	N_("Return to Draft"),
	N_("Approve"),
	N_("Reject"),
	N_("Mark Implemented"),
	N_("Close"),
)

# Etiquetas del resumen de impacto (para el Change Register). Orden estable.
_IMPACT_LABELS = (
	("impacts_scope", "Scope"),
	("impacts_schedule", "Schedule"),
	("impacts_effort", "Effort / Resources"),
	("impacts_commercial", "Commercial"),
	("impacts_risk", "Risk"),
)


class PMOChangeRequest(Document):
	def before_insert(self):
		# Default inicial del responsable de implementación desde el Project (dato propio del cambio; editable
		# mientras el CR sea editable). NO modifica el Project.
		if not self.implementation_owner and self.project:
			self.implementation_owner = frappe.db.get_value("Project", self.project, "pmo_operational_owner")

	def validate(self):
		self._set_defaults()
		self._compute_impact_summary()
		self._set_currency_default()
		self._validate_baseline_integrity()
		self._apply_workflow_gates()

	def before_update_after_submit(self):
		"""En un doc submitted, Frappe ejecuta SOLO este hook (no `validate`). Las transiciones
		submitted→submitted (Marcar Implementado, Cerrar) y la edición de `baseline_after` (campo
		`allow_on_submit`) ocurren por esta vía, así que aquí re-aplicamos la integridad de baselines y los
		gates de Workflow."""
		self._validate_baseline_integrity()
		self._apply_workflow_gates()

	# --- defaults ------------------------------------------------------------------

	def _set_defaults(self):
		if not self.raised_by:
			self.raised_by = frappe.session.user
		if not self.request_date:
			self.request_date = today()
		if not self.priority:
			self.priority = (
				"Medium"  # default robusto (la ruta get_doc(dict) no aplica el default del schema)
			)

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
					frappe._("{0} must belong to the same Project as the Change Request.").format(
						frappe.bold(self.meta.get_label(fieldname))
					)
				)

		if self.baseline_before and self.baseline_after:
			if self.baseline_before == self.baseline_after:
				frappe.throw(frappe._("Baseline After cannot be the same as Baseline Before."))
			eb = frappe.db.get_value("PMO Project Baseline", self.baseline_before, "effective_date")
			ea = frappe.db.get_value("PMO Project Baseline", self.baseline_after, "effective_date")
			if eb and ea and getdate(ea) < getdate(eb):
				frappe.throw(
					frappe._("Baseline After cannot be effective earlier than Baseline Before ({0}).").format(
						eb
					)
				)

	# --- gates de Workflow (por transición) ----------------------------------------

	def _apply_workflow_gates(self):
		"""Aplica los gates ligados a la transición de estado. Se detecta el cambio comparando el estado
		nuevo (en memoria, ya seteado por `apply_workflow`) contra el previo persistido."""
		new_state = self.get("workflow_state")
		if not new_state:
			return
		before = self.get_doc_before_save()
		old_state = before.get("workflow_state") if before else None
		if new_state == old_state:
			return
		if new_state == IN_REVIEW:
			self._ensure_baseline_before()  # gate duro + congelado
			self._ensure_addendum()  # flujo único: toda CR formal tiene su Addenda (B4)
		elif new_state == REJECTED:
			if not (self.decision_notes and self.decision_notes.strip()):
				frappe.throw(
					frappe._("Provide Decision notes explaining why the Change Request is rejected.")
				)
		elif new_state == IMPLEMENTED:
			self._gate_implemented()
		elif new_state == CLOSED:
			self._gate_closed()

	def _gate_implemented(self):
		"""Gate Approved -> Implemented (flujo único, B4): responsable definido + Addenda existente
		(`proposal_group`) + aplicada al Project (`applied_to_project`). No hay ruta "sin Addenda".
		`impacts_commercial` es solo clasificación informativa y NO participa en este gate. `Mark
		Implemented` sigue siendo la confirmación explícita del responsable."""
		if not self.implementation_owner:
			frappe.throw(frappe._("Set the Implementation Owner before marking the change as implemented."))
		if not self.proposal_group:
			frappe.throw(
				frappe._("Create the Addendum for this Change Request before it can be implemented.")
			)
		if not self.applied_to_project:
			frappe.throw(
				frappe._(
					"Apply the Addendum to the Project (the Scope Items) before marking the change as implemented."
				)
			)

	def _gate_closed(self):
		"""Gate Implemented -> Closed: baseline_after (fijada por una Baseline `Approved Change` que referencia
		este CR) y comunicación a interesados informada."""
		if not self.baseline_after:
			frappe.throw(
				frappe._(
					"Link the new baseline before closing: submit a PMO Project Baseline of type 'Approved Change' that references this Change Request."
				)
			)
		if not (self.stakeholder_communication and self.stakeholder_communication.strip()):
			frappe.throw(
				frappe._(
					"Record the Stakeholder Communication before closing the implemented change (use 'N/A' if it genuinely does not apply)."
				)
			)

	def _ensure_addendum(self):
		"""Flujo único (ADR-0015 B4): una CR no puede pasar a `In Review` sin su Addenda canónica ya creada
		(`proposal_group` fijado por el sistema al crearla). No existe ruta paralela "sin Addenda"."""
		if not self.proposal_group:
			frappe.throw(
				frappe._(
					"Create the Addendum before sending the Change Request for review "
					"(every formal change goes through exactly one Addendum)."
				)
			)

	def _ensure_baseline_before(self):
		"""Gate duro (ADR-0005 D4): sin baseline vigente no hay Change Control. Congela `baseline_before`
		con la baseline vigente del Project la primera vez que se formaliza/aprueba."""
		if self.baseline_before:
			return
		from pmo.baseline import get_effective_baseline

		bl = get_effective_baseline(self.project)
		if not bl:
			frappe.throw(
				frappe._(
					"The Change Request cannot be formalized/approved: the Project has no baseline in effect. Create and approve a PMO Project Baseline before sending it for review."
				)
			)
		self.baseline_before = bl

	# --- aprobacion fijada al Submit (D6/D10) --------------------------------------

	def before_submit(self):
		"""Aprobar/Rechazar el CR = Submit (autoridad owner-only sellada por P4 sobre `submit`). Registra
		la decisión y garantiza el gate de baseline como red de seguridad (cualquier ruta a `docstatus=1`,
		incluido un submit directo que se salte 'En Revision'). El contenido de la solicitud queda inmutable
		(no `allow_on_submit`)."""
		self._ensure_baseline_before()
		self._ensure_addendum()  # red de seguridad del flujo único: ni un submit directo aprueba sin Addenda
		# Rechazar también es un Submit (docstatus 0→1): NO es una aprobación → no registra aprobación ni
		# captura la Addenda gobernada (B5). Solo el aterrizaje en `Approved` es aprobación real.
		if self.get("workflow_state") == REJECTED:
			return
		# Aprobación gobernada (B5): fija la versión exacta de Addenda aprobada + su fingerprint canónico.
		self._capture_approved_addendum()
		if not self.approved_by:
			self.approved_by = frappe.session.user
		if not self.approved_at:
			self.approved_at = now_datetime()

	def _capture_approved_addendum(self):
		"""Al aprobar (In Review → Approved / submit directo): resuelve la versión viva de la Addenda del
		grupo, exige que esté congelada y `En Revision`, y persiste `approved_addendum` +
		`approved_delta_fingerprint` (huella canónica de `erpnext_proposals`). Fail-closed ante
		ausencia/inconsistencia/error. `pmo` NO calcula la huella ni resuelve versiones por su cuenta."""
		quotation, fingerprint = _resolve_live_addendum_in_review(self.proposal_group)
		self.approved_addendum = quotation
		self.approved_delta_fingerprint = fingerprint

	# --- cancel: escape controlado (D10) -------------------------------------------

	def before_cancel(self):
		"""Cancelar es "retirar" un CR aún no materializado. Bloqueado si el cambio ya se aplicó al Project
		(`applied_to_project`), si ya se cerró con una nueva baseline (`baseline_after`) o si está en un
		estado terminal del Workflow (`Rechazado`/`Cerrado`): en esos casos la realidad/baseline ya cambió o
		el CR es evidencia terminal, y revertir exige un CR nuevo."""
		if self.applied_to_project:
			frappe.throw(
				frappe._(
					"Cannot cancel: the change was already applied to the Project. Record a new Change Request to revert it."
				)
			)
		if self.baseline_after:
			frappe.throw(
				frappe._("Cannot cancel: the Change Request was already closed with a new baseline.")
			)
		if self.get("workflow_state") in _TERMINAL_STATES:
			frappe.throw(
				frappe._(
					"Cannot cancel a Change Request in a terminal state ({0}). Record a new Change Request."
				).format(self.get("workflow_state"))
			)


# --- Aprobación gobernada de la Addenda (B5) ---------------------------------------


def _addendum_state(quotation: str):
	"""Estado congelado de la Quotation-addenda (docstatus + workflow_state). Seam aislado de la lectura de
	esquema de `erpnext_proposals` (Quotation.workflow_state) para poder verificar el estado sin reimplementar
	nada. Devuelve un `_dict` o `None`."""
	return frappe.db.get_value("Quotation", quotation, ["docstatus", "workflow_state"], as_dict=True)


def _resolve_live_addendum_in_review(proposal_group: str):
	"""Resuelve la versión VIVA de la Addenda del grupo y su fingerprint canónico, exigiendo que esté
	congelada y `En Revision`. Devuelve `(quotation, fingerprint)`. Fail-closed ante ausencia/estado
	inválido/error del contrato. `pmo` NO parsea grupos, NO calcula la huella y NO resuelve versiones: todo
	proviene de `erpnext_proposals` (vía `change_control`)."""
	if not proposal_group:
		frappe.throw(frappe._("The Change Request has no Addendum to approve."))
	quotation = change_control.get_live_proposal_for_group(proposal_group)
	if not quotation:
		frappe.throw(frappe._("No live Addendum version was found for this Change Request's Proposal Group."))
	info = _addendum_state(quotation)
	if not info or cint(info.docstatus) != 1 or info.workflow_state != ADDENDUM_REVIEW_STATE:
		frappe.throw(
			frappe._(
				"The Addendum must be frozen and In Review (submitted) before the change can be approved. "
				"Current version: {0}."
			).format(quotation)
		)
	fingerprint = change_control.get_addendum_delta_fingerprint(quotation)
	if not fingerprint:
		frappe.throw(frappe._("Could not obtain the Addendum's delta fingerprint (fail-closed)."))
	return quotation, fingerprint


@frappe.whitelist()
def reapprove_addendum_version(change_request: str):
	"""Re-aprueba la versión vigente de la Addenda cuando se emitió una nueva versión del mismo grupo
	(rechazo del cliente → nueva versión). Owner-only (P4 `submit` == owner). Actualiza `approved_addendum`
	y `approved_delta_fingerprint` con la versión viva `En Revision`. NO cambia `workflow_state`,
	`approved_by`/`approved_at` ni `applied_*`; la trazabilidad queda en Version/track_changes."""
	doc = frappe.get_doc("PMO Change Request", change_request)
	doc.check_permission("submit")  # owner-only (P4): aprobar/re-aprobar es autoridad del Project Owner
	if doc.docstatus != 1 or doc.get("workflow_state") != APPROVED:
		frappe.throw(frappe._("Re-approval is only possible for an Approved Change Request."))
	if doc.applied_to_project:
		frappe.throw(frappe._("The change was already applied; re-approval no longer applies."))
	quotation, fingerprint = _resolve_live_addendum_in_review(doc.proposal_group)
	doc.approved_addendum = quotation
	doc.approved_delta_fingerprint = fingerprint
	doc.save()  # solo campos allow_on_submit sobre el CR submitted
	return {"approved_addendum": quotation, "approved_delta_fingerprint": fingerprint}


# --- Acción explícita: Crear addenda comercial (ADR-0015) --------------------------
# NOTA (B4): la acción de "Aplicar Quotation al Project" con Quotation seleccionada por el usuario fue
# ELIMINADA. El apply automático y gobernado (deriva la versión Ganada + guard de fingerprint) se
# implementa en B6; entre B4 y B6 no existe ruta de apply.


@frappe.whitelist()
def crear_addenda(change_request: str):
	"""Inicia la addenda comercial del cambio delegando en `erpnext_proposals.create_addendum_quotation`.

	Autoridad (ADR-0005 Modelo 1, sin elevación): (a) **gobernanza PMO** — se exige `write` sobre el CR
	editable (owner o colaborador con DocShare-write; P4); (b) **autoría comercial** — la impone
	`erpnext_proposals` (`Proposals Manager`/`System Manager`). Si el usuario carece de autoría comercial,
	`create_addendum_quotation` lanza `PermissionError` (sin bypass).

	El root de la propuesta se localiza por la **relación persistente** `Quotation.proposal_project = Project`
	(no se parsea `project_name` ni `-ADD-NN`). Persiste la identidad de la addenda en `proposal_group`
	(campo existente). Devuelve el `name` de la nueva Quotation. Atómico con el request (sin commit manual)."""
	doc = frappe.get_doc("PMO Change Request", change_request)
	doc.check_permission("write")  # CR editable (docstatus 0) → owner o DocShare-write por P4
	if doc.docstatus != 0:
		frappe.throw(
			frappe._("The addendum is created while the Change Request is editable (Draft / In Review).")
		)
	if doc.proposal_group:
		frappe.throw(
			frappe._("This Change Request already has an addendum ({0}).").format(doc.proposal_group)
		)

	# Localizar una Quotation del contrato original vía la relación persistente (no por nombre del Project).
	root_q = frappe.db.get_value(
		"Quotation", {"proposal_project": doc.project}, "name", order_by="creation asc"
	)
	if not root_q:
		frappe.throw(
			frappe._(
				"The Project does not come from a proposal (no Quotation with proposal_project); an addendum cannot be created."
			)
		)

	# Delegación: erpnext_proposals crea la addenda ROOT-ADD-NN (exige autoría comercial) — sin elevar permisos.
	new_quotation = change_control.create_addendum_quotation(root_q)

	# Persistir la identidad de la addenda (grupo estable) en el modelo existente. Leer el grupo NO es
	# interpretar el patrón: es leer el campo persistente que fijó erpnext_proposals.
	group = frappe.db.get_value("Quotation", new_quotation, "proposal_group")
	if group:
		doc.proposal_group = group
		doc.save()
	return new_quotation
