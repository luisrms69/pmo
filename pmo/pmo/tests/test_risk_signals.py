# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 — señales de riesgo derivadas (workflow accionable). Datos ficticios.

Cubre: Project sin/ con Assessment, sin riesgos, Open/Managing/Closed, exposición alta, sin responsable, sin
tratamiento, P4 del endpoint, y que Project Control reutiliza las MISMAS señales (fuente única de cálculo)."""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.project_control import SECTION_RISK, build_project_control
from pmo.risk_signals import compute_risk_signals, get_risk_signals


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


def _project(name, owner="Administrator"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Open"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	return pid


def _assessment(project):
	return frappe.get_doc({"doctype": "PMO Project Risk Assessment", "project": project}).insert(
		ignore_permissions=True
	)


def _risk(project, status="Open", high=True, risk_owner=None, response=None):
	doc = {
		"doctype": "PMO Project Risk",
		"project": project,
		"description": "Riesgo de prueba",
		"probability": "High likelihood" if high else "Low likelihood",
		"impact": "High" if high else "Low",
		"status": status,
	}
	if risk_owner:
		doc["risk_owner"] = risk_owner
	if response:
		doc["response"] = response
	return frappe.get_doc(doc).insert(ignore_permissions=True)


class TestRiskSignals(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_no_assessment_no_risks(self):
		s = compute_risk_signals(_project("RS Empty"))
		self.assertFalse(s["assessment_exists"])
		self.assertEqual(s["assessment_state"], "none")
		self.assertEqual(s["total"], 0)
		self.assertEqual(s["open"], 0)
		self.assertFalse(s["needs_attention"])

	def test_assessment_state_assessed(self):
		p = _project("RS Assessed")
		_assessment(p)
		s = compute_risk_signals(p)
		self.assertTrue(s["assessment_exists"])
		self.assertEqual(s["assessment_state"], "assessed")

	def test_open_managing_closed_counts(self):
		p = _project("RS Counts")
		_risk(p, status="Open")
		_risk(p, status="Managing")
		_risk(p, status="Closed")
		s = compute_risk_signals(p)
		self.assertEqual(s["total"], 3)
		self.assertEqual(s["open"], 2)  # Open + Managing (no Closed)

	def test_high_exposure(self):
		p = _project("RS High")
		_risk(p, status="Open", high=True)  # High likelihood x High → High exposure
		_risk(p, status="Open", high=False)  # Low → no cuenta como alta
		s = compute_risk_signals(p)
		self.assertEqual(s["high_exposure"], 1)
		self.assertTrue(s["needs_attention"])

	def test_high_exposure_closed_excluded(self):
		p = _project("RS HighClosed")
		_risk(p, status="Closed", high=True)  # cerrada → no cuenta
		self.assertEqual(compute_risk_signals(p)["high_exposure"], 0)

	def test_no_owner(self):
		p = _project("RS Owner")
		_risk(p, status="Open", high=False)  # sin responsable
		_risk(p, status="Open", high=False, risk_owner="Administrator")  # con responsable
		self.assertEqual(compute_risk_signals(p)["no_owner"], 1)

	def test_no_response(self):
		p = _project("RS Resp")
		_risk(p, status="Open", high=False)  # sin tratamiento
		_risk(p, status="Open", high=False, response="Plan A")  # con tratamiento
		self.assertEqual(compute_risk_signals(p)["no_response"], 1)

	def test_p4_authorized(self):
		owner = _user("rs_owner@example.com", roles=("Projects User",))
		p = _project("RS P4ok", owner=owner)
		frappe.set_user(owner)
		try:
			self.assertIsInstance(get_risk_signals(p), dict)
		finally:
			frappe.set_user("Administrator")

	def test_p4_unauthorized(self):
		owner = _user("rs_owner2@example.com", roles=("Projects User",))
		stranger = _user("rs_stranger@example.com", roles=("Projects User",))
		p = _project("RS P4no", owner=owner)
		frappe.set_user(stranger)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_risk_signals(p)
		finally:
			frappe.set_user("Administrator")

	def test_project_control_uses_same_signals(self):
		p = _project("RS PC")
		_assessment(p)
		_risk(p, status="Open", high=True)
		ctx = build_project_control(p, sections=[SECTION_RISK])
		self.assertIn(SECTION_RISK, ctx)
		self.assertEqual(dict(ctx[SECTION_RISK]), compute_risk_signals(p))
