# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D4 — PMO Project Closure. Datos ficticios.

Cubre: congelado autoritativo al submit (snapshot canonico + hash + issued_by/at), integridad del hash
contra el JSON congelado (no vivo), invariante un-Closure-por-Project, y P4 (read = visibilidad del Project;
write/submit = solo owner).
"""

import hashlib
import json

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_closure


def _user(email):
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
	return email


def _project(name, owner="Administrator", status="Completed"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": status,
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	frappe.db.set_value("Project", pid, "status", status, update_modified=False)
	return pid


def _closure(project, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Closure",
			"project": project,
			"closure_date": kw.get("closure_date", "2026-03-31"),
			"final_result": kw.get("final_result", "Delivered"),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestProjectClosure(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_submit_freezes_snapshot(self):
		p = _project("CLS Freeze")
		doc = _closure(p)
		self.assertFalse(doc.snapshot_hash)
		doc.submit()
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], 1)
		self.assertIn("schedule", snap)
		self.assertIn("economics", snap)
		self.assertIn("effort", snap)

	def test_hash_matches_frozen_json_not_live(self):
		p = _project("CLS Hash")
		doc = _closure(p)
		doc.submit()
		# Integridad contra la EVIDENCIA CONGELADA: hash == sha256 del JSON almacenado.
		self.assertEqual(doc.snapshot_hash, hashlib.sha256(doc.snapshot.encode("utf-8")).hexdigest())
		frozen, frozen_hash = doc.snapshot, doc.snapshot_hash
		# Cambiar el Project despues del submit NO altera el snapshot ni el hash.
		frappe.db.set_value("Project", p, "expected_end_date", "2027-12-31", update_modified=False)
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(doc.snapshot_hash, frozen_hash)

	def test_completed_with_closure_is_closed(self):
		from pmo.governance import LIFECYCLE_CLOSED, derive_lifecycle_state

		p = _project("CLS Completed", status="Completed")
		_closure(p).submit()
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSED)

	def test_cancelled_with_closure_is_closed(self):
		from pmo.governance import LIFECYCLE_CLOSED, derive_lifecycle_state

		p = _project("CLS Cancelled", status="Cancelled")
		_closure(p).submit()
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSED)

	def test_one_closure_per_project(self):
		p = _project("CLS Unique")
		doc = _closure(p)
		doc.submit()
		with self.assertRaises(ValidationError):
			_closure(p)

	def test_p4_read_and_write(self):
		owner = _user("cls_owner@example.com")
		stranger = _user("cls_stranger@example.com")
		p = _project("CLS P4", owner=owner)
		doc = _closure(p)
		self.assertTrue(has_permission_closure(doc, "read", owner))
		self.assertFalse(has_permission_closure(doc, "read", stranger))
		self.assertTrue(has_permission_closure(doc, "submit", owner))
		self.assertFalse(has_permission_closure(doc, "submit", stranger))
		self.assertFalse(has_permission_closure(doc, "share", owner))
