# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 — PMO Project Charter. Datos ficticios.

Cubre: congelado autoritativo en before_submit (snapshot canonico + hash + issued_by/at), invariante de
un-Charter-por-Project, autosuficiencia (sin dependencia de Risk: el snapshot no contiene estructura de
riesgo), y P4 (read = visibilidad del Project; write/submit = solo owner; Executive read-only).
"""

import json

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_charter
from pmo.pmo.doctype.pmo_project_charter.pmo_project_charter import build_charter_snapshot


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
	if committed:
		frappe.db.set_value("Project", pid, "pmo_committed_end_date", committed, update_modified=False)
	return pid


def _charter(project, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Charter",
			"project": project,
			"title": kw.get("title", "Charter"),
			"objective": kw.get("objective", "Deliver X"),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestProjectCharter(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_submit_freezes_snapshot(self):
		p = _project("CHT Freeze", committed="2026-03-31")
		doc = _charter(p)
		self.assertFalse(doc.snapshot_hash)  # nada congelado antes del submit
		doc.submit()
		# snapshot + hash + issued_by/at congelados
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], 1)
		self.assertEqual(snap["project"]["name"], p)
		# fecha comprometida congelada desde el Project (no capturada a mano)
		self.assertEqual(str(doc.committed_end_date), "2026-03-31")
		self.assertEqual(snap["project"]["committed_end_date"], "2026-03-31")

	def test_snapshot_hash_reproducible(self):
		from pmo.pmo.doctype.pmo_project_charter.pmo_project_charter import (
			snapshot_hash as _sh,
		)

		p = _project("CHT Hash")
		doc = _charter(p)
		doc.submit()
		# recomputar el hash sobre el snapshot canonico reproduce el valor congelado
		self.assertEqual(doc.snapshot_hash, _sh(build_charter_snapshot(p)))

	def test_no_risk_structure_in_snapshot(self):
		# Autosuficiencia (ADR-0014 D3/D6): el snapshot NO contiene estructura de riesgo.
		p = _project("CHT NoRisk")
		snap = build_charter_snapshot(p)
		self.assertNotIn("risk", snap)
		self.assertNotIn("risks", snap)
		self.assertNotIn("initial_risks", snap)

	def test_one_charter_per_project(self):
		p = _project("CHT Unique")
		doc = _charter(p)
		doc.submit()
		# un segundo Charter (no enmienda) para el mismo Project se rechaza
		with self.assertRaises(ValidationError):
			_charter(p, title="Second")

	def test_p4_read_and_write(self):
		owner = _user("cht_owner@example.com")
		stranger = _user("cht_stranger@example.com")
		p = _project("CHT P4", owner=owner)
		doc = _charter(p)
		# READ: visible al owner, no al extraño (sin share ni global read)
		self.assertTrue(has_permission_charter(doc, "read", owner))
		self.assertFalse(has_permission_charter(doc, "read", stranger))
		# WRITE/SUBMIT: solo el owner del Project
		self.assertTrue(has_permission_charter(doc, "write", owner))
		self.assertFalse(has_permission_charter(doc, "write", stranger))
		self.assertTrue(has_permission_charter(doc, "submit", owner))
		self.assertFalse(has_permission_charter(doc, "submit", stranger))
		# SHARE denegado incluso al owner
		self.assertFalse(has_permission_charter(doc, "share", owner))
