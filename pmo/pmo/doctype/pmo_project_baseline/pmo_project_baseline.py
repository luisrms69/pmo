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
				frappe._("Effective Date no puede ser futura (v0.5.0 no soporta baselines programadas).")
			)

	# --- invariantes de configuration control (lineage lineal) ---------------------

	def _validate_lineage(self):
		# revision unica por Project
		if frappe.db.exists(
			"PMO Project Baseline",
			{"project": self.project, "revision": self.revision, "name": ["!=", self.name or ""]},
		):
			frappe.throw(
				frappe._("Ya existe una baseline con revision {0} en este Project.").format(
					frappe.bold(self.revision)
				)
			)

		if self.baseline_type == ORIGINAL:
			if self.supersedes_baseline:
				frappe.throw(frappe._("Una baseline Original no debe sustituir a otra."))
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
				frappe.throw(frappe._("Ya existe una baseline Original para este Project."))
			return

		# no-Original -> debe sustituir la cabeza vigente de la cadena
		if not self.supersedes_baseline:
			frappe.throw(frappe._("Una baseline que no es Original debe indicar cual sustituye."))
		if self.supersedes_baseline == self.name:
			frappe.throw(frappe._("Una baseline no puede sustituirse a si misma."))

		sup = frappe.db.get_value(
			"PMO Project Baseline",
			self.supersedes_baseline,
			["project", "docstatus"],
			as_dict=True,
		)
		if not sup:
			frappe.throw(frappe._("La baseline que se sustituye no existe."))
		if sup.project != self.project:
			frappe.throw(frappe._("Solo se puede sustituir una baseline del mismo Project."))
		if sup.docstatus != 1:
			frappe.throw(frappe._("Solo se puede sustituir una baseline Submitted y no Cancelada."))

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
				frappe._("Esa baseline ya fue sustituida; debe sustituir la cabeza vigente de la cadena.")
			)

		self._guard_no_cycle()

	def _guard_no_cycle(self):
		seen, cur, depth = set(), self.supersedes_baseline, 0
		while cur and depth < 1000:
			if cur == self.name:
				frappe.throw(frappe._("Ciclo detectado en la cadena de supersession."))
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
				frappe._("No se puede congelar: {0}").format(
					json.dumps(preflight["blocking"], ensure_ascii=False)
				)
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
			frappe.throw(frappe._("Effective Date no puede ser posterior a la fecha de aprobacion."))
