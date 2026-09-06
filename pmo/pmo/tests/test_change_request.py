# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0005 — PMO Change Request (Bloque 2). Datos ficticios.

Cubre las invariantes BASE del bloque (independientes del Workflow): defaults, `impact_summary`,
moneda por company, integridad de baselines (mismo Project + orden de effective_date), aprobacion fijada
en `before_submit`, guard de `before_cancel`; y P4 (read = visibilidad del Project; create/write = writer
owner/member con write de member solo en docstatus 0; submit/cancel/amend = owner; Executive read-only;
share denegado).
"""

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo.permissions import has_permission_change_request


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


def _project(name, owner="Administrator", members=(), company=None):
	pid = frappe.db.exists("Project", {"project_name": name})
	if not pid:
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": "Open",
				"company": company,
			}
		)
		for m in members:
			doc.append("pmo_members", {"member": m})
		pid = doc.insert(ignore_permissions=True, ignore_mandatory=True).name
	frappe.db.set_value("Project", pid, "owner", owner)
	return pid


def _cr(project, title="Cambio", reason="Motivo", submit=False, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Change Request",
			"project": project,
			"title": title,
			"reason": reason,
			**kw,
		}
	).insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _baseline(project, revision, effective=None, submit=True):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,
			"baseline_type": "Original",
			"effective_date": effective or today(),
		}
	).insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


class TestChangeRequest(IntegrationTestCase):
	# --- comportamiento base -----------------------------------------------------

	def test_defaults_and_impact_summary(self):
		p = _project("CR-P1")
		cr = _cr(p, impacts_scope=1, impacts_commercial=1)
		self.assertTrue(cr.raised_by)  # default sesion
		self.assertEqual(str(cr.request_date), today())
		self.assertEqual(cr.priority, "Media")  # default del schema
		self.assertEqual(cr.impact_summary, "Alcance, Comercial")  # orden estable

	def test_currency_default_from_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		expected = frappe.db.get_value("Company", company, "default_currency")
		p = _project("CR-P2", company=company)
		cr = _cr(p)
		self.assertEqual(cr.currency, expected)

	def test_baseline_before_must_match_project(self):
		p1 = _project("CR-P3")
		p2 = _project("CR-P3B")
		other_bl = _baseline(p2, "BL-001")
		with self.assertRaises(ValidationError):
			_cr(p1, baseline_before=other_bl.name)

	def test_baseline_after_effective_order(self):
		p = _project("CR-P4")
		b1 = _baseline(p, "BL-001", effective="2026-01-01")
		# sucesora mas nueva en la cadena (monotonia ADR-0004): 2026-02-01 >= 2026-01-01
		b2 = frappe.get_doc(
			{
				"doctype": "PMO Project Baseline",
				"project": p,
				"revision": "BL-002",
				"baseline_type": "Replan",
				"supersedes_baseline": b1.name,
				"effective_date": "2026-02-01",
			}
		).insert(ignore_permissions=True)
		b2.submit()
		with self.assertRaises(ValidationError):
			# before (b2, mas nueva) despues que after (b1, mas vieja) -> inconsistente
			_cr(p, baseline_before=b2.name, baseline_after=b1.name)

	def test_before_submit_sets_approval(self):
		p = _project("CR-P5")
		cr = _cr(p, submit=True)
		cr.reload()
		self.assertEqual(cr.docstatus, 1)
		self.assertTrue(cr.approved_by)
		self.assertTrue(cr.approved_at)

	def test_before_cancel_blocked_when_applied(self):
		p = _project("CR-P6")
		cr = _cr(p, submit=True)
		frappe.db.set_value("PMO Change Request", cr.name, "applied_to_project", 1)
		cr.reload()
		with self.assertRaises(ValidationError):
			cr.cancel()

	# --- P4 ----------------------------------------------------------------------

	def test_permissions_read_write_submit(self):
		owner = _user("cr-owner@example.com")
		member = _user("cr-member@example.com")
		other = _user("cr-other@example.com")
		execu = _user("cr-exec@example.com", ["PMO Executive Access"])
		p = _project("CR-P7", owner=owner, members=[member])
		cr = _cr(p)  # docstatus 0

		# READ = visibilidad del Project
		self.assertTrue(has_permission_change_request(cr, "read", owner))
		self.assertTrue(has_permission_change_request(cr, "read", member))
		self.assertTrue(has_permission_change_request(cr, "read", execu))  # executive global
		self.assertFalse(has_permission_change_request(cr, "read", other))  # ajeno

		# CREATE/WRITE = writer (owner o member) con CR editable
		self.assertTrue(has_permission_change_request(cr, "write", owner))
		self.assertTrue(has_permission_change_request(cr, "write", member))
		self.assertFalse(has_permission_change_request(cr, "write", other))
		self.assertFalse(has_permission_change_request(cr, "write", execu))  # executive read-only

		# SUBMIT/CANCEL/AMEND = owner-only
		self.assertTrue(has_permission_change_request(cr, "submit", owner))
		self.assertFalse(has_permission_change_request(cr, "submit", member))
		self.assertFalse(has_permission_change_request(cr, "submit", execu))
		self.assertFalse(has_permission_change_request(cr, "cancel", member))

		# SHARE denegado (incluso owner)
		self.assertFalse(has_permission_change_request(cr, "share", owner))

	def test_member_write_denied_after_submit(self):
		owner = _user("cr-owner2@example.com")
		member = _user("cr-member2@example.com")
		p = _project("CR-P8", owner=owner, members=[member])
		cr = _cr(p, submit=True)  # docstatus 1
		cr.reload()
		# tras aprobar (submit), el member ya NO escribe; el owner si (campos allow_on_submit)
		self.assertFalse(has_permission_change_request(cr, "write", member))
		self.assertTrue(has_permission_change_request(cr, "write", owner))
