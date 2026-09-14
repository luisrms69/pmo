# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 Risk (R1) — PMO Project Risk Assessment. Datos ficticios.

Cubre: cuestionario precargado (6 preguntas), uno por Project (unique), exposición derivada server-side
(matriz 3x3) e ignorando input del cliente, limpieza de campos cuando Applies=No, y P4 heredado del Project
(read=visible; write=project writer; Executive read-only; share denegado)."""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_risk_assessment
from pmo.pmo.doctype.pmo_project_risk_assessment.pmo_project_risk_assessment import (
	RISK_QUESTIONS,
	derive_exposure,
)


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


class TestProjectRiskAssessment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_exposure_matrix(self):
		self.assertEqual(derive_exposure("High", "High"), "High")
		self.assertEqual(derive_exposure("Low", "High"), "Medium")
		self.assertEqual(derive_exposure("Low", "Low"), "Low")
		self.assertIsNone(derive_exposure("High", None))

	def test_questionnaire_preloaded(self):
		a = _assessment(_project("RA Preload"))
		self.assertEqual(len(a.questions), len(RISK_QUESTIONS))
		self.assertEqual([q.question_code for q in a.questions], [c for c, _ in RISK_QUESTIONS])
		self.assertTrue(all(q.question for q in a.questions))
		self.assertTrue(all(q.applies == "No" for q in a.questions))

	def test_exposure_derived_server_side(self):
		a = _assessment(_project("RA Exposure"))
		row = a.questions[0]
		row.applies = "Yes"
		row.probability = "High"
		row.impact = "Medium"
		row.exposure = "Low"  # intento de fijar exposición desde el cliente
		a.save()
		self.assertEqual(a.questions[0].exposure, "High")  # server-side gana

	def test_cleared_when_not_applies(self):
		a = _assessment(_project("RA Clear"))
		row = a.questions[0]
		row.applies = "Yes"
		row.probability = "High"
		row.impact = "High"
		row.action = "mitigate"
		row.may_affect_controlled = "Yes"
		a.save()
		self.assertEqual(a.questions[0].exposure, "High")
		# Cambia a No: se limpian los campos dependientes.
		a.questions[0].applies = "No"
		a.save()
		self.assertIsNone(a.questions[0].exposure)
		self.assertIsNone(a.questions[0].probability)
		self.assertIsNone(a.questions[0].action)
		self.assertIsNone(a.questions[0].may_affect_controlled)

	def test_one_per_project_unique(self):
		p = _project("RA Unique")
		_assessment(p)
		with self.assertRaises(frappe.exceptions.ValidationError):
			_assessment(p)  # 'project' unique → segundo assessment rechazado

	def test_p4_read_and_write(self):
		owner = _user("ra_owner@example.com")
		stranger = _user("ra_stranger@example.com")
		p = _project("RA P4", owner=owner)
		doc = _assessment(p)
		self.assertTrue(has_permission_risk_assessment(doc, "read", owner))
		self.assertFalse(has_permission_risk_assessment(doc, "read", stranger))
		self.assertTrue(has_permission_risk_assessment(doc, "write", owner))
		self.assertFalse(has_permission_risk_assessment(doc, "write", stranger))
		self.assertFalse(has_permission_risk_assessment(doc, "share", owner))
