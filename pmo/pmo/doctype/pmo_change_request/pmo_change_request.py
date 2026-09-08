# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Change Request (ADR-0005). Contenedor de gobernanza del cambio: submittable + Workflow nativo,
con impacto estructurado mínimo, decisión del owner fijada al aprobar (Submit) y enlaces a la
Quotation-addendum y a las baselines before/after.

Semántica de estados (Workflow `PMO Change Request`):
    Borrador → En Revision → Aprobado / Rechazado → Implementado → Cerrado

- Al pasar a **En Revision** (formalizar): gate duro de baseline vigente + congelado de `baseline_before`.
- **Aprobar/Rechazar** = Submit (autoridad owner-only sellada por P4 sobre `submit` + condición del
  Workflow). `before_submit` fija `approved_by`/`approved_at` y actúa como **red de seguridad** del gate
  de baseline (cubre cualquier ruta a `docstatus=1`).
- **Aplicar Quotation al Project** (acción explícita, no transición): materializa los Scope Items vía el
  contrato `erpnext_proposals.apply_addendum_to_project` y fija `applied_*`. **No** mueve el Workflow.
- **Marcar Implementado**: transición Aprobado→Implementado; gate: si hay `proposal_group`, exige
  `applied_to_project`.
- **Cerrar**: transición Implementado→Cerrado; gate: exige `baseline_after`.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

from pmo import change_control

# Estados del Workflow (deben coincidir EXACTAMENTE con el fixture workflow.json / workflow_state.json).
DRAFT = "Borrador"
IN_REVIEW = "En Revision"
APPROVED = "Aprobado"
REJECTED = "Rechazado"
IMPLEMENTED = "Implementado"
CLOSED = "Cerrado"
_TERMINAL_STATES = (REJECTED, CLOSED)

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
		elif new_state == IMPLEMENTED:
			if self.proposal_group and not self.applied_to_project:
				frappe.throw(
					frappe._(
						"Aplica la Cotización al Project (los Scope Items) antes de marcar el cambio como implementado."
					)
				)
		elif new_state == CLOSED:
			if not self.baseline_after:
				frappe.throw(
					frappe._("Liga la nueva baseline (Baseline After) antes de cerrar el Change Request.")
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
					"No se puede formalizar/aprobar el Change Request: el Project no tiene una baseline vigente. "
					"Crea y aprueba una PMO Project Baseline antes de enviar a revisión."
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
		if not self.approved_by:
			self.approved_by = frappe.session.user
		if not self.approved_at:
			self.approved_at = now_datetime()

	# --- cancel: escape controlado (D10) -------------------------------------------

	def before_cancel(self):
		"""Cancelar es "retirar" un CR aún no materializado. Bloqueado si el cambio ya se aplicó al Project
		(`applied_to_project`), si ya se cerró con una nueva baseline (`baseline_after`) o si está en un
		estado terminal del Workflow (`Rechazado`/`Cerrado`): en esos casos la realidad/baseline ya cambió o
		el CR es evidencia terminal, y revertir exige un CR nuevo."""
		if self.applied_to_project:
			frappe.throw(
				frappe._(
					"No se puede cancelar: el cambio ya fue aplicado al Project. Registra un Change Request nuevo para revertirlo."
				)
			)
		if self.baseline_after:
			frappe.throw(
				frappe._("No se puede cancelar: el Change Request ya se cerró con una nueva baseline.")
			)
		if self.get("workflow_state") in _TERMINAL_STATES:
			frappe.throw(
				frappe._(
					"No se puede cancelar un Change Request en estado terminal ({0}). Registra un Change Request nuevo."
				).format(self.get("workflow_state"))
			)


# --- Acción explícita: Aplicar Quotation al Project (ADR-0005 D7) -------------------


@frappe.whitelist()
def aplicar_quotation_al_project(change_request: str, quotation: str):
	"""Aplica los Scope Items de la Quotation-addendum al Project EXISTENTE del CR, delegando en el
	contrato de `erpnext_proposals` (`apply_addendum_to_project`). Owner-only (P4 sobre write del CR
	submitted). NO mueve el Workflow: solo fija `applied_to_project`/`applied_at`/`applied_quotation`. La
	transición a `Implementado` es un paso explícito posterior ("Marcar Implementado")."""
	doc = frappe.get_doc("PMO Change Request", change_request)
	doc.check_permission("write")  # sobre un CR submitted → owner-only por P4
	if doc.docstatus != 1 or doc.get("workflow_state") != APPROVED:
		frappe.throw(
			frappe._("Solo se puede aplicar una Cotización desde un Change Request en estado 'Aprobado'.")
		)
	if doc.applied_to_project:
		frappe.throw(frappe._("La Cotización ya fue aplicada a este Change Request."))
	if not quotation:
		frappe.throw(frappe._("Indica la Cotización (Ganada) a aplicar."))

	# Delegación: erpnext_proposals valida (Ganada/single-live/…), escribe proposal_project y anexa Tasks.
	result = change_control.apply_addendum_to_project(quotation, doc.project)

	doc.applied_to_project = 1
	doc.applied_at = now_datetime()
	doc.applied_quotation = quotation
	doc.save()  # solo campos allow_on_submit sobre el CR submitted
	return result


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
			frappe._("La addenda se crea mientras el Change Request es editable (Borrador/En Revisión).")
		)
	if doc.proposal_group:
		frappe.throw(frappe._("Este Change Request ya tiene una addenda ({0}).").format(doc.proposal_group))

	# Localizar una Quotation del contrato original vía la relación persistente (no por nombre del Project).
	root_q = frappe.db.get_value(
		"Quotation", {"proposal_project": doc.project}, "name", order_by="creation asc"
	)
	if not root_q:
		frappe.throw(
			frappe._(
				"El Project no proviene de una propuesta (sin Cotización con proposal_project); no se puede crear una addenda."
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


# --- UX de baseline_after: selección explícita, más guiada (ADR-0005 D5) -----------


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def baseline_after_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query para `baseline_after`: baselines Submitted del mismo Project, distintas de
	`baseline_before` y compatibles temporalmente (`effective_date >= baseline_before.effective_date`).
	Reduce fricción sin automatizar la relación (que es de negocio, no "la vigente al instante")."""
	filters = filters or {}
	conds = ["b.docstatus = 1", "b.project = %(project)s"]
	vals = {"project": filters.get("project"), "txt": f"%{txt or ''}%", "start": start, "page_len": page_len}
	before = filters.get("baseline_before")
	if before:
		conds.append("b.name != %(before)s")
		vals["before"] = before
		eff = frappe.db.get_value("PMO Project Baseline", before, "effective_date")
		if eff:
			conds.append("b.effective_date >= %(eff)s")
			vals["eff"] = eff
	conds.append("(b.name like %(txt)s or b.revision like %(txt)s)")
	return frappe.db.sql(
		f"""select b.name, b.revision from `tabPMO Project Baseline` b
			where {" and ".join(conds)}
			order by b.effective_date desc, b.creation desc
			limit %(page_len)s offset %(start)s""",
		vals,
	)


@frappe.whitelist()
def get_current_baseline(project: str):
	"""Conveniencia para el botón 'Usar línea base vigente': devuelve la baseline vigente del Project si es
	visible para el usuario (P4). NO fija nada; el usuario puede escoger otra."""
	if not project:
		return None
	from pmo.baseline import get_effective_baseline
	from pmo.permissions import is_project_visible

	if not is_project_visible(project, frappe.session.user):
		frappe.throw(frappe._("No tienes acceso a este Project."), frappe.PermissionError)
	return get_effective_baseline(project)
