# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 (modelo definitivo) — PMO Project Risk Assessment: cribado vivo, Save nativo genera riesgos.

Cubre: precarga+snapshot, exposición as-identified, **validación obligatoria** (description/probability/impact al
aplicar), limpieza al No aplicar, **Project inmutable**, **Save de fila aplicable completa genera 1 Risk**,
idempotencia (2º Save no duplica ni toca el Risk existente), No aplica no genera, riesgo manual, reevaluación
(nueva identificación genera solo el nuevo), uno por Project, y P4."""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_risk_assessment
from pmo.pmo.doctype.pmo_project_risk_assessment.pmo_project_risk_assessment import (
	derive_exposure,
	get_active_catalog_questions,
)
from pmo.setup.risk_catalog import seed_risk_questions


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


def _apply(a, idx=0, description="Riesgo", probability="High likelihood", impact="High", **extra):
	row = a.questions[idx]
	row.applies = "Yes"
	row.description = description
	row.probability = probability
	row.impact = impact
	for k, v in extra.items():
		setattr(row, k, v)
	a.save()
	a.reload()
	return a.questions[idx]


class TestProjectRiskAssessment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		seed_risk_questions()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_exposure_matrix(self):
		self.assertEqual(derive_exposure("High likelihood", "High"), "High exposure")
		self.assertEqual(derive_exposure("Low likelihood", "High"), "Medium exposure")
		self.assertIsNone(derive_exposure("High likelihood", None))

	def test_questionnaire_preloaded_from_catalog(self):
		a = _assessment(_project("RA Preload"))
		catalog = get_active_catalog_questions()
		self.assertEqual(len(a.questions), len(catalog))
		self.assertTrue(all(q.question and q.section for q in a.questions))
		self.assertTrue(all(q.applies == "No" for q in a.questions))

	def test_snapshot_immutable_to_catalog_edits(self):
		a = _assessment(_project("RA Snapshot"))
		row = next(q for q in a.questions if q.question_code == "EXT-01")
		original = row.question
		q = frappe.get_doc("PMO Risk Question", "EXT-01")
		q.question = "TEXTO CAMBIADO"
		q.save(ignore_permissions=True)
		a.reload()
		row2 = next(q for q in a.questions if q.question_code == "EXT-01")
		self.assertEqual(row2.question, original)

	def test_exposure_as_identified_server_side(self):
		a = _assessment(_project("RA Exposure"))
		row = _apply(a, probability="High likelihood", impact="Medium", exposure="Low exposure")
		self.assertEqual(row.exposure, "High exposure")  # derivada, gana server-side

	# --- validación obligatoria al aplicar ---

	def test_missing_description_blocks_save(self):
		a = _assessment(_project("RA NoDesc"))
		r = a.questions[0]
		r.applies = "Yes"
		r.probability = "High likelihood"
		r.impact = "High"
		with self.assertRaises(frappe.exceptions.MandatoryError):
			a.save()

	def test_missing_probability_blocks_save(self):
		a = _assessment(_project("RA NoProb"))
		r = a.questions[0]
		r.applies = "Yes"
		r.description = "x"
		r.impact = "High"
		with self.assertRaises(frappe.exceptions.MandatoryError):
			a.save()

	def test_missing_impact_blocks_save(self):
		a = _assessment(_project("RA NoImp"))
		r = a.questions[0]
		r.applies = "Yes"
		r.description = "x"
		r.probability = "High likelihood"
		with self.assertRaises(frappe.exceptions.MandatoryError):
			a.save()

	def test_cleared_when_not_applies(self):
		a = _assessment(_project("RA Clear"))
		row = a.questions[0]
		row.applies = "Yes"
		row.description = "temp"
		row.probability = "High likelihood"
		row.impact = "High"
		row.applies = "No"
		a.save()
		a.reload()
		cleared = a.questions[0]
		self.assertIsNone(cleared.exposure)
		self.assertIsNone(cleared.description)
		self.assertFalse(cleared.risk)

	def test_project_is_immutable(self):
		p1 = _project("RA Imm1")
		p2 = _project("RA Imm2")
		a = _assessment(p1)
		a.project = p2
		with self.assertRaises(frappe.exceptions.ValidationError):
			a.save()

	# --- generación por Save ---

	def test_applies_no_generates_no_risk(self):
		p = _project("RA No")
		_assessment(p)  # todas No
		self.assertEqual(frappe.db.count("PMO Project Risk", {"project": p}), 0)

	def test_save_generates_one_risk(self):
		p = _project("RA Gen")
		a = _assessment(p)
		row = _apply(a, description="Dependencia externa", probability="High likelihood", impact="High")
		self.assertTrue(row.risk)
		self.assertEqual(frappe.db.count("PMO Project Risk", {"project": p}), 1)
		risk = frappe.get_doc("PMO Project Risk", row.risk)
		self.assertEqual(risk.exposure, "High exposure")
		self.assertEqual(int(risk.is_manual or 0), 0)

	def test_second_save_idempotent_and_risk_untouched(self):
		p = _project("RA Idem")
		a = _assessment(p)
		row = _apply(a, probability="Low likelihood", impact="High")
		frappe.db.set_value("PMO Project Risk", row.risk, "status", "Managing")  # el Risk evoluciona aparte
		a.save()  # segundo save del Assessment
		a.save()  # tercero
		self.assertEqual(frappe.db.count("PMO Project Risk", {"project": p}), 1)  # sin duplicar
		self.assertEqual(
			frappe.db.get_value("PMO Project Risk", row.risk, "status"), "Managing"
		)  # no lo toca

	def test_manual_row_generates_manual_risk(self):
		p = _project("RA Manual")
		a = _assessment(p)
		a.append(
			"questions",
			{
				"applies": "Yes",
				"description": "Riesgo no anticipado",
				"probability": "High likelihood",
				"impact": "High",
			},
		)
		a.save()
		a.reload()
		manual_item = next(q for q in a.questions if int(q.is_manual or 0) == 1)
		self.assertTrue(manual_item.risk)
		risk = frappe.get_doc("PMO Project Risk", manual_item.risk)
		self.assertEqual(int(risk.is_manual or 0), 1)
		self.assertFalse(risk.source_question_code)

	def test_reevaluation_generates_only_new_risk(self):
		p = _project("RA Reeval")
		a = _assessment(p)
		row0 = _apply(a, idx=0, description="Primero", probability="High likelihood", impact="High")
		self.assertEqual(frappe.db.count("PMO Project Risk", {"project": p}), 1)
		# Reevaluación posterior: otra pregunta pasa a aplicable → solo genera ESE nuevo risk.
		_apply(a, idx=1, description="Segundo", probability="Low likelihood", impact="High")
		self.assertEqual(frappe.db.count("PMO Project Risk", {"project": p}), 2)
		# El primer risk no se reabre ni cambia por el Assessment.
		self.assertTrue(row0.risk)

	def test_as_identified_preserved_when_risk_evolves(self):
		p = _project("RA Frozen")
		a = _assessment(p)
		row = _apply(a, description="riesgo", probability="High likelihood", impact="High")
		risk = frappe.get_doc("PMO Project Risk", row.risk)
		risk.probability = "Low likelihood"
		risk.status = "Managing"
		risk.update_note = "Reevaluación."
		risk.save()
		a.reload()
		item = a.questions[0]
		self.assertEqual(item.probability, "High likelihood")
		self.assertEqual(item.exposure, "High exposure")

	def test_one_per_project_unique(self):
		p = _project("RA Unique")
		_assessment(p)
		with self.assertRaises(frappe.exceptions.ValidationError):
			_assessment(p)

	def test_p4_read_and_write(self):
		owner = _user("ra_owner@example.com")
		stranger = _user("ra_stranger@example.com")
		p = _project("RA P4", owner=owner)
		doc = _assessment(p)
		self.assertTrue(has_permission_risk_assessment(doc, "read", owner))
		self.assertFalse(has_permission_risk_assessment(doc, "read", stranger))
		self.assertTrue(has_permission_risk_assessment(doc, "write", owner))
		self.assertFalse(has_permission_risk_assessment(doc, "share", owner))
