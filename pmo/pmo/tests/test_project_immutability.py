# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Auditoría de integridad — `project` inmutable tras crear en los DocTypes pmo con Link estructural a Project.

Regla estructural compartida (`pmo.project_link.enforce_immutable_project`, vía doc_events + `set_only_once`).
Cubre: wiring en los 7 DocTypes, y enforcement end-to-end en representantes submittable (Change Request, Baseline).
Risk y Risk Assessment se cubren en sus propios módulos. La suite completa cubre create/submit sin regresión."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

_PROJECT_DOCTYPES = (
	"PMO Project Risk",
	"PMO Project Risk Assessment",
	"PMO Project Baseline",
	"PMO Change Request",
	"PMO Project Closure",
	"PMO Project Handoff",
	"PMO Post-Project Review",
)


def _project(name):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Open"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", "Administrator", update_modified=False)
	return pid


class TestProjectImmutability(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_hooks_registered_for_all_project_doctypes(self):
		from pmo import hooks

		for dt in _PROJECT_DOCTYPES:
			handler = str(hooks.doc_events.get(dt, {}).get("validate", ""))
			self.assertIn("pmo.project_link.enforce_immutable_project", handler, f"falta wiring en {dt}")

	def test_change_request_project_immutable(self):
		p1, p2 = _project("PI CR1"), _project("PI CR2")
		cr = frappe.get_doc(
			{"doctype": "PMO Change Request", "project": p1, "title": "Cambio", "reason": "Motivo"}
		).insert(ignore_permissions=True)
		self.assertEqual(cr.project, p1)  # seleccionable al crear
		cr.project = p2
		with self.assertRaises(frappe.exceptions.ValidationError):
			cr.save()  # inmutable incluso en Draft

	def test_baseline_project_immutable(self):
		p1, p2 = _project("PI B1"), _project("PI B2")
		b = frappe.get_doc(
			{
				"doctype": "PMO Project Baseline",
				"project": p1,
				"revision": "R1",
				"baseline_type": "Original",
				"effective_date": today(),
				"reason": "Inicial",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(b.project, p1)
		b.project = p2
		with self.assertRaises(frappe.exceptions.ValidationError):
			b.save()
