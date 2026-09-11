# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Baseline (ADR-0004). Baseline de cronograma/plan operacional: submittable, con lineage
lineal (configuration control), aprobacion fijada al Submit y snapshot canonico inmutable construido en
`before_submit`. NO es una PMI Scope Baseline completa (ver ADR-0004 D5/gaps).
"""

import json

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

from pmo.baseline import build_snapshot, canonical_json, run_preflight, snapshot_hash

ORIGINAL = "Original"


class PMOProjectBaseline(Document):
	def validate(self):
		self._validate_effective_date()
		self._validate_lineage()

	# --- vigencia (Opcion B: sin future-effective) ---------------------------------

	def _validate_effective_date(self):
		if self.effective_date and getdate(self.effective_date) > getdate(today()):
			frappe.throw(
				frappe._(
					"Effective Date cannot be in the future (v0.5.0 does not support scheduled baselines)."
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

		# no-Original -> debe sustituir la cabeza vigente de la cadena
		if not self.supersedes_baseline:
			frappe.throw(frappe._("A non-Original baseline must indicate which one it supersedes."))
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
