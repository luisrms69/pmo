# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Charter (ADR-0014 D3/D11) — autorizacion/arranque formal del Project.

Submittable + track_changes: al emitir (submit) se **congela** un snapshot canonico con hash (mismo patron
que PMO Project Baseline: `canonical_json` + `snapshot_hash`). El Charter **compone**, no recaptura: los datos
canonicos (customer/company, fecha comprometida, propuesta ganada, economia autorizada, hitos y equipo
iniciales) se derivan del Project y se congelan como evidencia historica del arranque; solo se capturan a mano
los campos de gobierno que no existen en otro lado (sponsor/PM/objetivo/alcance/entregables/supuestos/
restricciones).

Autosuficiente: NO depende de Risk ni de ningun registro de riesgos (ADR-0014 D3/D6). No toca PHI.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from pmo.baseline import canonical_json, snapshot_hash
from pmo.project_economics import get_authorized_economics

CHARTER_SNAPSHOT_SCHEMA_VERSION = 1


def build_charter_snapshot(project: str) -> dict:
	"""Snapshot canonico de arranque: compone datos ya existentes (no recalcula ni recaptura).

	Economia autorizada: se consume la frontera canonica `get_authorized_economics` (lazy a
	erpnext_proposals); si no esta disponible se registra el motivo, nunca se inventa. Hitos = Tasks
	`is_milestone`; equipo inicial = `Project.users`.
	"""
	proj = (
		frappe.db.get_value(
			"Project",
			project,
			[
				"project_name",
				"customer",
				"company",
				"expected_start_date",
				"expected_end_date",
				"pmo_committed_end_date",
			],
			as_dict=True,
		)
		or frappe._dict()
	)
	customer_name = (
		frappe.db.get_value("Customer", proj.get("customer"), "customer_name")
		if proj.get("customer")
		else None
	)
	# `proposal_project` es un custom field de erpnext_proposals: solo se consulta si la app esta instalada
	# (autosuficiencia, ADR-0014 D3 — el Charter no depende de erpnext_proposals).
	proposal = None
	if "erpnext_proposals" in frappe.get_installed_apps():
		proposal = frappe.db.get_value(
			"Quotation",
			{"proposal_project": project, "workflow_state": "Ganada", "docstatus": 1},
			"name",
		)

	econ = get_authorized_economics(project)  # {available, reason, data, message}
	edata = econ.get("data") or {}
	economics = {
		"available": econ.get("available"),
		"reason": econ.get("reason"),
		"authorized_revenue": edata.get("authorized_revenue"),
		"authorized_cost": edata.get("authorized_cost"),
		"authorized_margin": edata.get("authorized_margin"),
		"currency": edata.get("currency"),
	}

	milestones = [
		{
			"task": t.name,
			"subject": t.subject,
			"exp_end_date": str(t.exp_end_date) if t.exp_end_date else None,
		}
		for t in frappe.get_all(
			"Task",
			filters={"project": project, "is_milestone": 1},
			fields=["name", "subject", "exp_end_date"],
			order_by="exp_end_date asc",
		)
	]
	team = [
		{"user": u.user}
		for u in frappe.get_all(
			"Project User", filters={"parent": project, "parenttype": "Project"}, fields=["user"]
		)
	]

	return {
		"snapshot_schema_version": CHARTER_SNAPSHOT_SCHEMA_VERSION,
		"project": {
			"name": project,
			"project_name": proj.get("project_name"),
			"customer": proj.get("customer"),
			"customer_name": customer_name,
			"company": proj.get("company"),
			"expected_start_date": str(proj.get("expected_start_date"))
			if proj.get("expected_start_date")
			else None,
			"expected_end_date": str(proj.get("expected_end_date"))
			if proj.get("expected_end_date")
			else None,
			"committed_end_date": str(proj.get("pmo_committed_end_date"))
			if proj.get("pmo_committed_end_date")
			else None,
		},
		"proposal_reference": proposal,
		"economics": economics,
		"milestones": milestones,
		"team": team,
	}


class PMOProjectCharter(Document):
	def validate(self):
		# Un solo Charter emitido por Project (las enmiendas reemplazan; el anterior queda cancelado).
		if not self.amended_from:
			existing = frappe.db.exists(
				"PMO Project Charter",
				{"project": self.project, "docstatus": 1, "name": ["!=", self.name or ""]},
			)
			if existing:
				frappe.throw(frappe._("This Project already has an issued Charter ({0}).").format(existing))

	def before_submit(self):
		# Congela la evidencia canonica al emitir (ADR-0014 D3/D11). El Print Format se reconstruye SOLO
		# desde este snapshot, nunca desde datos vivos.
		snapshot = build_charter_snapshot(self.project)
		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		self.snapshot = canonical_json(snapshot)  # forma canonica (misma que se hashea)

		# Campos derivados de presentacion (congelados): se leen del snapshot, no de datos vivos.
		self.committed_end_date = snapshot["project"]["committed_end_date"]
		self.proposal_reference = snapshot["proposal_reference"]
		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()
