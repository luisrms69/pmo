# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D7/D8 — estado de ciclo de vida DERIVADO + índice de expediente. Datos ficticios.

Cubre: derivación del estado documental desde hechos (sin workflow en Project), resiliencia cuando
Closure/Review aún no existen como DocType, y la sección `governance` opt-in en build_project_control
(índice de existencia/fechas, no en DEFAULT_SECTIONS).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.governance import (
	LIFECYCLE_CLOSING,
	LIFECYCLE_INITIATION,
	LIFECYCLE_PLANNING,
	build_expediente,
	derive_lifecycle_state,
)
from pmo.project_control import DEFAULT_SECTIONS, SECTION_GOVERNANCE


def _project(name, status="Open"):
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
	frappe.db.set_value("Project", pid, "status", status, update_modified=False)
	return pid


def _prepare_handoff_parties(project):
	"""El Handoff exige responsable operativo interno + contacto del cliente en el Project para emitirse."""
	emp = frappe.db.exists("Employee", {"employee_name": "Gov Op Owner"}) or (
		frappe.get_doc({"doctype": "Employee", "employee_name": "Gov Op Owner", "first_name": "Gov"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	ct = frappe.db.exists("Contact", {"first_name": "Gov Contact"}) or (
		frappe.get_doc({"doctype": "Contact", "first_name": "Gov Contact"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", project, "pmo_operational_owner", emp, update_modified=False)
	frappe.db.set_value("Project", project, "pmo_customer_contact", ct, update_modified=False)


def _handoff(project):
	_prepare_handoff_parties(project)
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Handoff",
			"project": project,
			"handoff_summary": "Transferencia X",
			"contractual_legal_ready": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


class TestGovernanceLifecycle(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_initiation_without_artifacts(self):
		p = _project("GOV Init")
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_INITIATION)

	def test_planning_after_handoff(self):
		p = _project("GOV Plan")
		_handoff(p)
		# Handoff emitido, sin baseline vigente → Planning.
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_PLANNING)

	def test_closing_when_completed_without_closure(self):
		p = _project("GOV Closing", status="Completed")
		# Project Completed y (aún) sin DocType de Closure → Closing (no rompe: Closure es bloque futuro).
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSING)

	def test_closing_when_cancelled_without_closure(self):
		p = _project("GOV Cancelled", status="Cancelled")
		# Un Project terminal Cancelled sin Closure también requiere cierre formal → Closing.
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSING)

	def test_expediente_index_shape_and_pending(self):
		p = _project("GOV Exp")
		_handoff(p)
		exp = build_expediente(p)
		self.assertEqual(exp["lifecycle_state"], LIFECYCLE_PLANNING)
		self.assertTrue(exp["handoff"]["available"])
		self.assertTrue(exp["handoff"]["reference"])
		# Handoff/Closure/Review ya existen como DocTypes (BLOQUES 2/4/5); sin doc para este Project →
		# disponible False y sin pending (pending es solo para DocTypes aún inexistentes).
		self.assertFalse(exp["closure"]["available"])
		self.assertFalse(exp["closure"]["pending"])
		self.assertFalse(exp["review"]["available"])
		self.assertFalse(exp["review"]["pending"])
		self.assertIn("open", exp["change_requests"])

	def test_artifact_pending_when_doctype_absent(self):
		# Mecanismo forward-compatible (desacoplado de doctypes reales): un artefacto cuyo DocType no existe
		# se marca pending, sin romper.
		from pmo.governance import _artifact

		p = _project("GOV Absent")
		art = _artifact("PMO Nonexistent Artifact", p, "creation")
		self.assertTrue(art["pending"])
		self.assertFalse(art["available"])

	def test_governance_is_optin_not_default(self):
		# La sección governance NO viaja por defecto (no en DEFAULT_SECTIONS); es opt-in.
		self.assertNotIn(SECTION_GOVERNANCE, DEFAULT_SECTIONS)
