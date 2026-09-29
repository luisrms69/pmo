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

El responsable operativo interno y el contacto principal del cliente se **capturan en el Acta** (el contacto
filtrado por el Customer del Project vía la relación nativa Contact.links → Dynamic Link). Al emitir se
**sincronizan** hacia el Project y quedan **congelados** en el Handoff; cambios posteriores en el Project no
alteran un Handoff ya emitido.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from pmo.baseline import canonical_json, snapshot_hash
from pmo.permissions import get_project_team

HANDOFF_SNAPSHOT_SCHEMA_VERSION = 2


def build_handoff_snapshot(
	project: str,
	contractual_legal_ready: bool = False,
	captured: dict | None = None,
	committed_end_date: str | None = None,
	operational_owner: str | None = None,
	customer_contact: str | None = None,
) -> dict:
	"""Snapshot canonico del handoff: compone datos ya existentes (no recalcula ni recaptura).

	`contractual_legal_ready` = confirmacion de readiness contractual/legal del documento. `captured` =
	evidencia humana capturada del propio documento (fecha de handoff, project manager, resumen y metadata de
	emision). Ambas quedan **dentro del snapshot** y por tanto cubiertas por `snapshot_hash` (evidencia
	congelada del Handoff, ADR-0014).

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
			"committed_end_date": committed_end_date
			if committed_end_date is not None
			else (str(proj.get("pmo_committed_end_date")) if proj.get("pmo_committed_end_date") else None),
		},
		"captured": captured or {},
		# Responsable/contacto: capturados en el Acta (fuente autoritativa). Se conserva el fallback al
		# Project solo para llamadas standalone de build (p. ej. utilidades/tests) sin valor explícito.
		"operational_owner": operational_owner
		if operational_owner is not None
		else proj.get("pmo_operational_owner"),
		"customer_contact": customer_contact
		if customer_contact is not None
		else proj.get("pmo_customer_contact"),
		"contractual_legal_ready": bool(contractual_legal_ready),
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
		# Obligatoriedades críticas del Acta de Inicio validadas SERVER-SIDE al emitir (no dependen solo del
		# `reqd` del formulario): objetivo, alcance, fecha comprometida, checks de coordinación/readiness,
		# identidad de quien autorizó y confirmación de autorización explícita. El backend es la autoridad.
		if not (self.project_objective or "").strip():
			frappe.throw(frappe._("Captura el Objetivo del proyecto antes de emitir el Handoff."))
		if not (self.scope_high_level or "").strip():
			frappe.throw(frappe._("Captura el Alcance de alto nivel antes de emitir el Handoff."))
		if not self.committed_end_date:
			frappe.throw(
				frappe._(
					"Captura la Fecha comprometida de terminación (Fin comprometido) antes de emitir el Handoff."
				)
			)
		if not self.pm_informed_coordinated:
			frappe.throw(
				frappe._("Confirma 'PM informado y transferencia coordinada' antes de emitir el Handoff.")
			)
		if not self.internal_team_informed:
			frappe.throw(
				frappe._("Confirma 'Equipo interno necesario informado' antes de emitir el Handoff.")
			)
		if not self.startup_conditions_reviewed:
			frappe.throw(
				frappe._(
					"Confirma 'Condiciones de arranque y pendientes revisados' antes de emitir el Handoff."
				)
			)
		# Readiness contractual/legal previa a ejecución: PMO no aprueba jurídicamente ni captura contratos;
		# solo confirma que los requisitos para iniciar se verificaron cuando aplica.
		if not self.contractual_legal_ready:
			frappe.throw(
				frappe._("Confirma 'Readiness contractual/legal verificada' antes de emitir el Handoff.")
			)
		# Autorización formal para iniciar: identidad de quien autorizó + confirmación explícita (ADR-0014).
		if not (self.authorized_by or "").strip():
			frappe.throw(
				frappe._("Indica quién autorizó el inicio ('Autorizado por') antes de emitir el Handoff.")
			)
		if not self.start_authorization_confirmed:
			frappe.throw(
				frappe._(
					"Confirma 'Autorización explícita para iniciar obtenida' antes de emitir el Handoff."
				)
			)

		# Project Manager: FUENTE ÚNICA = Project.pmo_project_manager. Se sella server-side (no se confía en el
		# valor del cliente ni se permite elegir otro), se congela como evidencia y NO se sincroniza de vuelta.
		# Sin PM canónico en el Project no puede emitirse (sin fallback inventado).
		canonical_pm = frappe.db.get_value("Project", self.project, "pmo_project_manager")
		if not canonical_pm:
			frappe.throw(
				frappe._(
					"Define el Project Manager (Responsable del proyecto) en el Project antes de emitir el Handoff."
				)
			)
		self.project_manager = canonical_pm

		# Responsable operativo y contacto del cliente: se CAPTURAN en el Acta (ya no se toman del Project).
		# Obligatorios server-side; al emitir se sincronizan al Project y quedan congelados en el Handoff.
		if not self.operational_owner:
			frappe.throw(frappe._("Indica el Responsable operativo interno antes de emitir el Handoff."))
		if not self.customer_contact:
			frappe.throw(frappe._("Indica el Contacto principal del cliente antes de emitir el Handoff."))
		# El contacto se valida contra el Customer del Project usando la relación NATIVA (Contact.links →
		# Dynamic Link a Customer). Sin Customer no puede validarse la relación → se exige definirlo primero.
		customer = frappe.db.get_value("Project", self.project, "customer")
		if not customer:
			frappe.throw(
				frappe._(
					"Define el Customer en el Project antes de emitir el Handoff (requerido para el Contacto del cliente)."
				)
			)
		if not frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Contact",
				"parent": self.customer_contact,
				"link_doctype": "Customer",
				"link_name": customer,
			},
		):
			frappe.throw(
				frappe._(
					"El Contacto principal del cliente no está relacionado con el Customer del Project. Selecciona un contacto del Customer."
				)
			)

		# Metadata de emisión ANTES de construir el snapshot, para que quede DENTRO de él (y del hash).
		self.issued_by = frappe.session.user
		self.issued_at = now_datetime()

		# Evidencia humana capturada del propio documento → congelada en el snapshot (cubierta por el hash).
		# Incluye la evidencia de autorización: quién autorizó + confirmación explícita + cuándo se formalizó
		# (issued_at). El compromiso autorizado (committed_end_date) queda congelado aquí como acta.
		captured = {
			"handoff_date": str(self.handoff_date) if self.handoff_date else None,
			"project_manager": self.project_manager,
			"handoff_summary": self.handoff_summary,
			"project_objective": self.project_objective,
			"scope_high_level": self.scope_high_level,
			"committed_end_date": str(self.committed_end_date) if self.committed_end_date else None,
			"pm_informed_coordinated": bool(self.pm_informed_coordinated),
			"internal_team_informed": bool(self.internal_team_informed),
			"startup_conditions_reviewed": bool(self.startup_conditions_reviewed),
			"authorized_by": self.authorized_by,
			"start_authorization_confirmed": bool(self.start_authorization_confirmed),
			"issued_by": self.issued_by,
			"issued_at": str(self.issued_at),
		}
		# Congela la evidencia canonica al emitir. El responsable operativo, el contacto del cliente y la fecha
		# comprometida son los AUTORIZADOS en el Acta (fuente formal): se congelan en el snapshot desde el
		# propio Handoff, no desde el Project.
		snapshot = build_handoff_snapshot(
			self.project,
			self.contractual_legal_ready,
			captured,
			committed_end_date=str(self.committed_end_date),
			operational_owner=self.operational_owner,
			customer_contact=self.customer_contact,
		)

		self.snapshot_schema_version = snapshot["snapshot_schema_version"]
		self.snapshot_hash = snapshot_hash(snapshot)
		self.snapshot = canonical_json(snapshot)  # forma canonica (misma que se hashea)

		# Campos derivados de presentacion (congelados): se leen del snapshot.
		self.proposal_reference = snapshot["proposal_reference"]
		self.customer = snapshot["project"]["customer"]
		self.company = snapshot["project"]["company"]

	def on_submit(self):
		# El Acta es el punto de captura: al emitir sincroniza al Project el compromiso inicial y las partes
		# capturadas (responsable operativo y contacto del cliente). Única escritura del Handoff hacia el
		# Project, solo al emitir; el Handoff conserva su copia congelada como evidencia.
		frappe.db.set_value(
			"Project",
			self.project,
			{
				"pmo_committed_end_date": self.committed_end_date,
				"pmo_operational_owner": self.operational_owner,
				"pmo_customer_contact": self.customer_contact,
			},
		)
