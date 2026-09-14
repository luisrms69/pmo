# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Project Handoff (ADR-0014) — evidencia formal de la transferencia del Project a ejecucion.

Documento corto y submittable: deja constancia del handoff (acta de transferencia) y marca el hito de
Governance "handoff completado". Flujo: Proposal ganada -> Project + WBS inicial -> **Project Handoff** ->
Baseline.

Naturaleza (heredada del anterior Charter): submittable + track_changes, uno emitido por Project, snapshot
canonico con hash (patron PMO Project Baseline: `canonical_json` + `snapshot_hash`) congelado al submit, y
P4 heredado del Project. NO recaptura alcance/entregables/economia: el Handoff **compone** datos ya
existentes en Project/Proposal y solo captura a mano lo que no vive en otro lado (resumen de handoff).

El responsable operativo interno y el contacto principal del cliente viven en el Project (custom fields) y se
**congelan** en el Handoff al emitir; cambios posteriores en el Project no alteran un Handoff ya emitido.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from pmo.baseline import canonical_json, snapshot_hash
from pmo.permissions import get_project_team

HANDOFF_SNAPSHOT_SCHEMA_VERSION = 1


def build_handoff_snapshot(project: str) -> dict:
	"""Snapshot canonico del handoff: compone datos ya existentes (no recalcula ni recaptura).

	Incluye el responsable operativo interno y el contacto principal del cliente (custom fields del Project),
	hitos (`Task.is_milestone`) y equipo inicial derivado de las fuentes P4 (owner + DocShare + ToDo). **NO**
	incluye economia autorizada: el Handoff es una transferencia operativa y la economia esta sujeta al gate
	`can_see_project_economics` (permlevel 1); guardarla en un snapshot legible por cualquiera con READ del
	Project/Handoff violaria esa politica. La economia autorizada vive en su frontera canonica y en el Closure
	(campo permlevel 1), no aqui."""
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
				"pmo_operational_owner",
				"pmo_customer_contact",
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
	# (autosuficiencia — el Handoff no depende de erpnext_proposals).
	proposal = None
	if "erpnext_proposals" in frappe.get_installed_apps():
		proposal = frappe.db.get_value(
			"Quotation",
			{"proposal_project": project, "workflow_state": "Ganada", "docstatus": 1},
			"name",
		)

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
	# Equipo inicial DERIVADO de las fuentes P4 canonicas (owner + DocShare + ToDo activo), no de
	# `Project User` (la membresia no se persiste; ADR-0002). Congelado en el snapshot al submit.
	team = [{"user": u} for u in get_project_team(project)]

	return {
		"snapshot_schema_version": HANDOFF_SNAPSHOT_SCHEMA_VERSION,
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
		"operational_owner": proj.get("pmo_operational_owner"),
		"customer_contact": proj.get("pmo_customer_contact"),
		"proposal_reference": proposal,
		"milestones": milestones,
		"team": team,
	}


class PMOProjectHandoff(Document):
	def validate(self):
		# Un solo Handoff emitido por Project (las enmiendas reemplazan; el anterior queda cancelado).
		if not self.amended_from:
			existing = frappe.db.exists(
				"PMO Project Handoff",
				{"project": self.project, "docstatus": 1, "name": ["!=", self.name or ""]},
			)
			if existing:
				frappe.throw(frappe._("This Project already has an issued Handoff ({0}).").format(existing))

	def before_submit(self):
		# Readiness contractual/legal previa a ejecución: confirmación mínima antes de emitir el Handoff. PMO
		# no aprueba jurídicamente ni captura contratos; solo confirma que los requisitos para iniciar se
		# verificaron cuando aplica (Proposal/Quotation ya autorizada → Project → Handoff verifica → ejecución).
		if not self.contractual_legal_ready:
			frappe.throw(
				frappe._("Confirm 'Contractual / Legal Readiness Verified' before issuing the Handoff.")
			)

		# Congela la evidencia canonica al emitir. El responsable operativo y el contacto del cliente se toman
		# del Project y quedan fijos: cambios posteriores en el Project no alteran un Handoff ya emitido.
		snapshot = build_handoff_snapshot(self.project)

		# Los dos datos que justifican el Handoff deben existir para poder emitirlo (acta de transferencia):
		# el responsable operativo interno y el contacto principal del cliente viven en el Project.
		if not snapshot["operational_owner"]:
			frappe.throw(
				frappe._(
					"Set the internal Operational Owner (Responsable operativo interno) on the Project before issuing the Handoff."
				)
			)
		if not snapshot["customer_contact"]:
			frappe.throw(
				frappe._(
					"Set the primary Customer Contact (Contacto principal del cliente) on the Project before issuing the Handoff."
				)
			)

		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		self.snapshot = canonical_json(snapshot)  # forma canonica (misma que se hashea)

		# Campos derivados de presentacion (congelados): se leen del snapshot, no de datos vivos.
		self.operational_owner = snapshot["operational_owner"]
		self.customer_contact = snapshot["customer_contact"]
		self.committed_end_date = snapshot["project"]["committed_end_date"]
		self.proposal_reference = snapshot["proposal_reference"]
		self.customer = snapshot["project"]["customer"]
		self.company = snapshot["project"]["company"]
		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()
