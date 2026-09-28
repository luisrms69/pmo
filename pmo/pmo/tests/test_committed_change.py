# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Cambio posterior del Fin comprometido (Project.pmo_committed_end_date). Datos ficticios.

Modelo mínimo (sin DocType/workflow/CR/rebaseline/historial propio):
- Handoff = compromiso inicial autorizado e inmutable.
- Project.pmo_committed_end_date = compromiso vigente (único que cambia).
- Version = antes/después técnico (Project no rastrea cambios nativamente → se registra explícito).
- Comentario/Timeline = motivo humano.

Cubre: autoridad (reutiliza `_has_pmo_authority`), obligatoriedades server-side, inmutabilidad del Handoff,
actualización del Project, trazabilidad Version y creación del comentario en el timeline.
"""

import json

import frappe
from frappe.exceptions import PermissionError, ValidationError
from frappe.tests import IntegrationTestCase

from pmo.schedule_commit import change_committed_end_date

ENDPOINT = "pmo.schedule_commit.change_committed_end_date"


def _user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	u = frappe.get_doc("User", email)
	if roles:
		u.add_roles(*roles)
	return email


def _project(name, owner="Administrator", committed=None):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": "Open",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	frappe.db.set_value("Project", pid, "pmo_committed_end_date", committed, update_modified=False)
	return pid


class TestCommittedChange(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_authorized_can_change_with_reason(self):
		p = _project("CC Authorized", committed="2026-03-31")
		out = change_committed_end_date(p, "2026-06-30", "Reprogramación acordada con el cliente")
		self.assertEqual(out["committed_end_date"], "2026-06-30")
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-06-30")

	def test_unauthorized_rejected_by_backend(self):
		# Usuario owner (pasa el P4 de lectura) pero SIN autoridad PMO → rechazado por el gate server-side.
		u = _user("cc_unauth@example.com", roles=("Projects User",))
		p = _project("CC Unauth", owner=u, committed="2026-03-31")
		frappe.set_user(u)
		with self.assertRaises(PermissionError):
			change_committed_end_date(p, "2026-06-30", "Intento sin autoridad")
		frappe.set_user("Administrator")
		# El compromiso no cambió.
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-03-31")

	def test_empty_reason_rejected(self):
		p = _project("CC EmptyReason", committed="2026-03-31")
		with self.assertRaises(ValidationError):
			change_committed_end_date(p, "2026-06-30", "   ")

	def test_same_date_rejected(self):
		p = _project("CC SameDate", committed="2026-03-31")
		with self.assertRaises(ValidationError):
			change_committed_end_date(p, "2026-03-31", "Sin cambio real")

	def test_project_without_current_commitment_rejected(self):
		p = _project("CC NoCommit", committed=None)
		with self.assertRaises(ValidationError):
			change_committed_end_date(p, "2026-06-30", "No hay compromiso vigente")

	def test_new_date_required(self):
		p = _project("CC NoDate", committed="2026-03-31")
		with self.assertRaises(ValidationError):
			change_committed_end_date(p, None, "Falta fecha")

	def test_version_traceability_created(self):
		p = _project("CC Version", committed="2026-03-31")
		before = frappe.db.count("Version", {"ref_doctype": "Project", "docname": p})
		change_committed_end_date(p, "2026-07-15", "Ajuste de calendario")
		versions = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Project", "docname": p},
			fields=["data"],
			order_by="creation desc",
		)
		self.assertEqual(len(versions), before + 1)
		changed = json.loads(versions[0]["data"])["changed"]
		self.assertIn(["pmo_committed_end_date", "2026-03-31", "2026-07-15"], changed)

	def test_timeline_comment_created(self):
		p = _project("CC Comment", committed="2026-03-31")
		change_committed_end_date(p, "2026-08-01", "Nuevo compromiso autorizado")
		comment = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Project",
				"reference_name": p,
				"comment_type": "Comment",
			},
			fields=["content", "owner"],
			order_by="creation desc",
			limit=1,
		)
		self.assertTrue(comment)
		self.assertIn("2026-03-31", comment[0]["content"])
		self.assertIn("2026-08-01", comment[0]["content"])
		self.assertIn("Nuevo compromiso autorizado", comment[0]["content"])
		# Autor por metadata nativa del comentario (no se duplica en campos nuevos).
		self.assertEqual(comment[0]["owner"], "Administrator")

	def test_handoff_initial_commitment_immutable(self):
		# El Handoff conserva SIEMPRE el compromiso inicial; cambiar el vigente del Project no lo altera.
		emp = frappe.db.exists("Employee", {"employee_name": "CC Op"}) or (
			frappe.get_doc({"doctype": "Employee", "employee_name": "CC Op", "first_name": "CC"})
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
		ct = frappe.db.exists("Contact", {"first_name": "CC Contact"}) or (
			frappe.get_doc({"doctype": "Contact", "first_name": "CC Contact"})
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
		p = _project("CC Handoff Immutable", committed=None)
		frappe.db.set_value("Project", p, "pmo_operational_owner", emp, update_modified=False)
		frappe.db.set_value("Project", p, "pmo_customer_contact", ct, update_modified=False)
		hof = frappe.get_doc(
			{
				"doctype": "PMO Project Handoff",
				"project": p,
				"handoff_summary": "Transferencia",
				"project_objective": "Objetivo.",
				"scope_high_level": "Alcance.",
				"committed_end_date": "2026-03-31",
				"authorized_by": "Sponsor",
				"pm_informed_coordinated": 1,
				"internal_team_informed": 1,
				"startup_conditions_reviewed": 1,
				"contractual_legal_ready": 1,
				"start_authorization_confirmed": 1,
			}
		)
		hof.insert(ignore_permissions=True)
		hof.submit()
		# Handoff fijó el compromiso inicial en el Project.
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-03-31")
		# Cambio posterior del vigente.
		change_committed_end_date(p, "2026-09-30", "Extensión aprobada por dirección")
		hof.reload()
		# El Handoff (compromiso inicial autorizado) NO cambia.
		self.assertEqual(str(hof.committed_end_date), "2026-03-31")
		self.assertEqual(json.loads(hof.snapshot)["project"]["committed_end_date"], "2026-03-31")
		# El Project ahora refleja el compromiso vigente nuevo.
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-09-30")
