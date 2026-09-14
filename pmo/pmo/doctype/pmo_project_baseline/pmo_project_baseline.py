# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Baseline (ADR-0004). Baseline de cronograma/plan operacional: submittable, con lineage
lineal (configuration control), aprobacion fijada al Submit y snapshot canonico inmutable construido en
`before_submit`. NO es una PMI Scope Baseline completa (ver ADR-0004 D5/gaps).

Tipos (`baseline_type`, valores canonicos en ingles; el es.po da el display en espanol):
  - **Original**: primera referencia autorizada del Project (unica valida por Project).
  - **Approved Change**: nueva referencia derivada de un `PMO Change Request` aprobado e **implementado**;
    exige la Solicitud de Cambio (mismo Project, estado Implemented, no reutilizada) y fija `baseline_after`
    en ese CR (relacion consistente con el mecanismo existente, sin segunda semantica).
  - **Replan**: nueva referencia por decision de gestion (desviaciones acumuladas), sin Change Request.

`revision` se **autogenera** por Project (`BL-001`, `BL-002`, ...): consecutiva, unica, determinista y
read-only. `supersedes_baseline` de toda baseline posterior a Original se **autodetermina** con la vigente
(cadena lineal). La aprobacion es el Submit (`approved_by`/`approved_at` automaticos).
"""

import json

import frappe
from frappe.model.document import Document
from frappe.query_builder import Order
from frappe.utils import cint, getdate, now_datetime, today

from pmo.baseline import (
	build_snapshot,
	canonical_json,
	get_effective_baseline,
	run_preflight,
	snapshot_hash,
)

ORIGINAL = "Original"
APPROVED_CHANGE = "Approved Change"
REPLAN = "Replan"
# Estado del Workflow del Change Request en el que ya fue aprobado/aplicado y aun necesita su nueva baseline
# para poder cerrarse (valor canonico en ingles; coincide con workflow.json / PMOChangeRequest).
CR_IMPLEMENTED = "Implemented"


class PMOProjectBaseline(Document):
	def before_insert(self):
		# Revision consecutiva autogenerada por Project (independiente de la fecha; read-only en UI).
		if not self.revision:
			self.revision = self._next_revision()

	def validate(self):
		self._autofill_supersedes()
		self._validate_effective_date()
		self._validate_reason()
		self._validate_change_request()
		self._validate_lineage()

	def on_submit(self):
		self._link_change_request_baseline_after()

	# --- revision autogenerada (consecutiva por Project) ---------------------------

	def _next_revision(self) -> str:
		"""`BL-NNN` = max(NNN existente en el Project) + 1. Cuenta todas las baselines del Project para no
		reutilizar numeros; la unicidad la refuerza `_validate_lineage`."""
		revisions = frappe.get_all(
			"PMO Project Baseline", filters={"project": self.project}, pluck="revision"
		)
		maxn = 0
		for r in revisions:
			if r and r.startswith("BL-"):
				try:
					maxn = max(maxn, int(r[3:]))
				except ValueError:
					pass
		return f"BL-{maxn + 1:03d}"

	# --- linea base sustituida autodeterminada -------------------------------------

	def _autofill_supersedes(self):
		"""Toda baseline posterior a Original sustituye la cabeza vigente de la cadena. El sistema ya la
		conoce; no se obliga al usuario a buscarla. Original nunca sustituye."""
		if self.baseline_type == ORIGINAL:
			self.supersedes_baseline = None
		elif not self.supersedes_baseline:
			self.supersedes_baseline = get_effective_baseline(self.project)

	# --- motivo obligatorio para baselines posteriores a Original ------------------

	def _validate_reason(self):
		"""Original: motivo opcional. Cambio aprobado / Replaneación aprobada: obligatorio (explica por qué se
		sustituye la vigente). Autoritativo en el servidor; `mandatory_depends_on` solo guía la UI."""
		if self.baseline_type != ORIGINAL and not (self.reason and self.reason.strip()):
			frappe.throw(
				frappe._("Provide a Reason (Motivo) for an Approved Change or an approved Replan baseline.")
			)

	# --- vigencia (Opcion B: sin future-effective) ---------------------------------

	def _validate_effective_date(self):
		if self.effective_date and getdate(self.effective_date) > getdate(today()):
			frappe.throw(
				frappe._("Effective Date cannot be in the future (scheduled baselines are not supported).")
			)

	# --- Cambio aprobado: Solicitud de Cambio valida (mismo Project, Implemented, no reutilizada) ---

	def _validate_change_request(self):
		"""Solo Approved Change usa `change_request`. Debe ser del mismo Project, estar Implemented (aprobado
		y aplicado, a la espera de su nueva baseline para cerrar) y no tener ya otra baseline posterior. Para
		los demas tipos se limpia (no hay semantica de CR)."""
		if self.baseline_type != APPROVED_CHANGE:
			self.change_request = None
			return
		if not self.change_request:
			frappe.throw(
				frappe._("Select the approved Change Request that backs this baseline (Approved Change).")
			)
		cr = frappe.db.get_value(
			"PMO Change Request",
			self.change_request,
			["project", "workflow_state", "baseline_after"],
			as_dict=True,
		)
		if not cr:
			frappe.throw(frappe._("The selected Change Request does not exist."))
		if cr.project != self.project:
			frappe.throw(frappe._("The Change Request must belong to the same Project as the baseline."))
		if cr.workflow_state != CR_IMPLEMENTED:
			frappe.throw(
				frappe._(
					"Only an Implemented Change Request can back a new baseline (it must be approved and applied, awaiting its new baseline to close)."
				)
			)
		if cr.baseline_after and cr.baseline_after != self.name:
			frappe.throw(
				frappe._("That Change Request already has an associated later baseline ({0}).").format(
					cr.baseline_after
				)
			)

	# --- invariantes de configuration control (lineage lineal) ---------------------

	def _validate_lineage(self):
		# revision unica por Project
		if frappe.db.exists(
			"PMO Project Baseline",
			{"project": self.project, "revision": self.revision, "name": ["!=", self.name or ""]},
		):
			frappe.throw(
				frappe._("A baseline with revision {0} already exists in this Project.").format(
					frappe.bold(self.revision)
				)
			)

		if self.baseline_type == ORIGINAL:
			if self.supersedes_baseline:
				frappe.throw(frappe._("An Original baseline must not supersede another."))
			# maximo una Original valida (no cancelada) por Project
			if frappe.db.exists(
				"PMO Project Baseline",
				{
					"project": self.project,
					"baseline_type": ORIGINAL,
					"docstatus": ["<", 2],
					"name": ["!=", self.name or ""],
				},
			):
				frappe.throw(frappe._("An Original baseline already exists for this Project."))
			return

		# no-Original -> debe sustituir la cabeza vigente de la cadena (autodeterminada arriba)
		if not self.supersedes_baseline:
			frappe.throw(
				frappe._(
					"A non-Original baseline requires an effective baseline to supersede, but the Project has none. Create and approve an Original baseline first."
				)
			)
		if self.supersedes_baseline == self.name:
			frappe.throw(frappe._("A baseline cannot supersede itself."))

		sup = frappe.db.get_value(
			"PMO Project Baseline",
			self.supersedes_baseline,
			["project", "docstatus", "effective_date"],
			as_dict=True,
		)
		if not sup:
			frappe.throw(frappe._("The superseded baseline does not exist."))
		if sup.project != self.project:
			frappe.throw(frappe._("Only a baseline from the same Project can be superseded."))
		if sup.docstatus != 1:
			frappe.throw(frappe._("Only a Submitted, non-Cancelled baseline can be superseded."))

		# monotonia de vigencia en la cadena: la sucesora no puede ser efectiva ANTES que la sustituida
		# (igual fecha permitida). Asi "cabeza de la cadena" == "mayor effective_date" no se contradicen.
		if (
			self.effective_date
			and sup.effective_date
			and getdate(self.effective_date) < getdate(sup.effective_date)
		):
			frappe.throw(
				frappe._(
					"Effective Date cannot be earlier than that of the superseded baseline ({0})."
				).format(sup.effective_date)
			)

		# sin bifurcaciones: la baseline sustituida no puede tener ya otro sucesor no cancelado
		if frappe.db.exists(
			"PMO Project Baseline",
			{
				"supersedes_baseline": self.supersedes_baseline,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		):
			frappe.throw(
				frappe._(
					"That baseline was already superseded; you must supersede the current head of the chain."
				)
			)

		self._guard_no_cycle()

	# --- cancelacion: solo la cabeza de la cadena (preserva el lineage) -------------

	def before_cancel(self):
		"""No se puede cancelar una baseline con un sucesor no-cancelado (dejaria la cadena rota o un
		draft apuntando a una baseline Cancelled). Cancelar la cabeza es valido y revierte la vigencia a la
		anterior. Nota: Frappe ya bloquea nativamente el caso de sucesor Submitted; esto lo hace explicito y
		cubre tambien el sucesor Draft.
		"""
		successor = frappe.db.exists(
			"PMO Project Baseline",
			{"supersedes_baseline": self.name, "docstatus": ["<", 2]},
		)
		if successor:
			frappe.throw(
				frappe._(
					"This baseline cannot be cancelled: it has a successor ({0}). Cancel the head of the chain first."
				).format(successor)
			)

	def _guard_no_cycle(self):
		seen, cur, depth = set(), self.supersedes_baseline, 0
		while cur and depth < 1000:
			if cur == self.name:
				frappe.throw(frappe._("Cycle detected in the supersession chain."))
			if cur in seen:
				break
			seen.add(cur)
			cur = frappe.db.get_value("PMO Project Baseline", cur, "supersedes_baseline")
			depth += 1

	# --- relacion consistente con Change Request (baseline_after) -------------------

	def _link_change_request_baseline_after(self):
		"""Al aprobar (Submit) una baseline de tipo Cambio aprobado, fija `PMO Change Request.baseline_after`
		= esta baseline (campo `allow_on_submit`), usando el mecanismo Frappe normal (save que re-valida la
		integridad de baselines del CR). No crea una segunda semantica: reutiliza el vinculo existente. La
		autoridad es el propio Submit de la baseline."""
		if self.baseline_type != APPROVED_CHANGE or not self.change_request:
			return
		cr = frappe.get_doc("PMO Change Request", self.change_request)
		if cr.baseline_after == self.name:
			return
		cr.baseline_after = self.name
		cr.save(ignore_permissions=True)

	# --- congelado autoritativo (ADR-0004 D5): solo en before_submit ---------------

	def before_submit(self):
		preflight = run_preflight(self.project)
		if preflight["blocking"]:
			frappe.throw(
				frappe._("Cannot freeze: {0}").format(json.dumps(preflight["blocking"], ensure_ascii=False))
			)

		snapshot = build_snapshot(self.project)
		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		# se persiste la forma canonica (misma que hashea) para reproducibilidad
		self.snapshot = canonical_json(snapshot)
		self.preflight_result = json.dumps(preflight, ensure_ascii=False)

		self.snapshot_at = now_datetime()
		self.approved_by = frappe.session.user
		self.approved_at = now_datetime()
		if not self.effective_date:
			self.effective_date = today()
		if getdate(self.effective_date) > getdate(self.approved_at):
			frappe.throw(frappe._("Effective Date cannot be later than the approval date."))


# --- UX de change_request: seleccion explicita, filtrada (mismo Project, Implemented, no reutilizada) ---


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def change_request_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict | None = None,
):
	"""Link query para `change_request` (baseline Cambio aprobado): Change Requests Submitted del mismo
	Project, en estado `Implemented` y sin `baseline_after` (no reutilizados). Reduce friccion sin automatizar
	la relacion. Query Builder: sin SQL por f-string; los valores viajan como parametros."""
	filters = filters or {}
	like = f"%{txt or ''}%"
	cr = frappe.qb.DocType("PMO Change Request")
	query = (
		frappe.qb.from_(cr)
		.select(cr.name, cr.title)
		.where(cr.docstatus == 1)
		.where(cr.project == filters.get("project"))
		.where(cr.workflow_state == CR_IMPLEMENTED)
		.where(cr.baseline_after.isnull() | (cr.baseline_after == ""))
		.where(cr.name.like(like) | cr.title.like(like))
		.orderby(cr.modified, order=Order.desc)
		.limit(cint(page_len))
		.offset(cint(start))
	)
	return query.run()
