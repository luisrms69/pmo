# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 — PMO Project Handoff. Datos ficticios.

Cubre: naturaleza submittable + un-Handoff-por-Project, congelado autoritativo en before_submit (snapshot +
hash + issued_by/at), obligatoriedad del resumen de handoff, toma/congelado del responsable operativo interno
y del contacto principal del cliente desde el Project (cambios posteriores en el Project no alteran el Handoff
ya emitido), y P4 (read = visibilidad del Project; write/submit = solo owner; Executive read-only)."""

import json

import frappe
from frappe.exceptions import MandatoryError, ValidationError
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_handoff
from pmo.pmo.doctype.pmo_project_handoff.pmo_project_handoff import build_handoff_snapshot


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
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _employee(name):
	existing = frappe.db.exists("Employee", {"employee_name": name})
	if existing:
		return existing
	return (
		frappe.get_doc({"doctype": "Employee", "employee_name": name, "first_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _contact(name):
	existing = frappe.db.exists("Contact", {"first_name": name})
	if existing:
		return existing
	return (
		frappe.get_doc({"doctype": "Contact", "first_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _project(name, owner="Administrator", committed=None, operational_owner=None, customer_contact=None):
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
	if committed:
		frappe.db.set_value("Project", pid, "pmo_committed_end_date", committed, update_modified=False)
	if operational_owner:
		frappe.db.set_value("Project", pid, "pmo_operational_owner", operational_owner, update_modified=False)
	if customer_contact:
		frappe.db.set_value("Project", pid, "pmo_customer_contact", customer_contact, update_modified=False)
	return pid


def _handoff(project, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Handoff",
			"project": project,
			"handoff_summary": kw.get("handoff_summary", "Se transfiere a ejecución con kickoff acordado."),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestProjectHandoff(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_is_submittable_and_freezes_snapshot(self):
		p = _project("HOF Freeze", committed="2026-03-31")
		doc = _handoff(p)
		self.assertEqual(doc.docstatus, 0)
		self.assertFalse(doc.snapshot_hash)  # nada congelado antes del submit
		doc.submit()
		self.assertEqual(doc.docstatus, 1)  # sigue siendo submittable
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], 1)
		self.assertEqual(snap["project"]["name"], p)
		self.assertEqual(str(doc.committed_end_date), "2026-03-31")

	def test_handoff_summary_is_mandatory(self):
		p = _project("HOF Summary")
		doc = frappe.get_doc({"doctype": "PMO Project Handoff", "project": p})
		with self.assertRaises(MandatoryError):
			doc.insert(ignore_permissions=True)

	def test_one_handoff_per_project(self):
		p = _project("HOF Unique")
		doc = _handoff(p)
		doc.submit()
		with self.assertRaises(ValidationError):
			_handoff(p)  # un segundo Handoff (no enmienda) para el mismo Project se rechaza

	def test_operational_owner_frozen_from_project(self):
		emp = _employee("Op Owner HOF")
		p = _project("HOF OpOwner", operational_owner=emp)
		doc = _handoff(p)
		doc.submit()
		self.assertEqual(doc.operational_owner, emp)
		self.assertEqual(json.loads(doc.snapshot)["operational_owner"], emp)
		# Cambiar el Project DESPUÉS del submit NO altera el Handoff ya emitido.
		emp2 = _employee("Op Owner HOF 2")
		frappe.db.set_value("Project", p, "pmo_operational_owner", emp2, update_modified=False)
		doc.reload()
		self.assertEqual(doc.operational_owner, emp)
		self.assertEqual(json.loads(doc.snapshot)["operational_owner"], emp)

	def test_customer_contact_frozen_from_project(self):
		ct = _contact("Primary Contact HOF")
		p = _project("HOF Contact", customer_contact=ct)
		doc = _handoff(p)
		doc.submit()
		self.assertEqual(doc.customer_contact, ct)
		self.assertEqual(json.loads(doc.snapshot)["customer_contact"], ct)
		# Cambio posterior en el Project no altera el Handoff emitido.
		ct2 = _contact("Primary Contact HOF 2")
		frappe.db.set_value("Project", p, "pmo_customer_contact", ct2, update_modified=False)
		doc.reload()
		self.assertEqual(doc.customer_contact, ct)

	def test_snapshot_hash_matches_frozen_json_not_live(self):
		import hashlib

		p = _project("HOF Hash", committed="2026-03-31")
		doc = _handoff(p)
		doc.submit()
		self.assertEqual(doc.snapshot_hash, hashlib.sha256(doc.snapshot.encode("utf-8")).hexdigest())
		frozen = doc.snapshot
		# Cambiar el Project no altera el snapshot congelado (evidencia histórica, no vivo).
		frappe.db.set_value("Project", p, "pmo_committed_end_date", "2027-12-31", update_modified=False)
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(json.loads(doc.snapshot)["project"]["committed_end_date"], "2026-03-31")

	def test_team_derived_from_p4_sources(self):
		owner = _user("hof_team_owner@example.com")
		p = _project("HOF Team", owner=owner)
		snap = build_handoff_snapshot(p)
		self.assertIn(owner, {m["user"] for m in snap["team"]})

	def test_p4_read_write_submit_share(self):
		owner = _user("hof_owner@example.com")
		stranger = _user("hof_stranger@example.com")
		p = _project("HOF P4", owner=owner)
		doc = _handoff(p)
		# READ: visible al owner, no al extraño (sin share ni global read)
		self.assertTrue(has_permission_handoff(doc, "read", owner))
		self.assertFalse(has_permission_handoff(doc, "read", stranger))
		# WRITE/SUBMIT: solo el owner del Project
		self.assertTrue(has_permission_handoff(doc, "write", owner))
		self.assertFalse(has_permission_handoff(doc, "write", stranger))
		self.assertTrue(has_permission_handoff(doc, "submit", owner))
		self.assertFalse(has_permission_handoff(doc, "submit", stranger))
		# SHARE denegado incluso al owner
		self.assertFalse(has_permission_handoff(doc, "share", owner))
