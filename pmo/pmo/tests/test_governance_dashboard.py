# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D9 — señales de gobierno (governance_flags) + sección Project Governance del Dashboard.

Datos ficticios. Cubre: semántica canónica de needs_closure ({Completed, Cancelled} sin Closure),
has_charter/needs_review/open_change_requests, y que el bloque del Dashboard consume esas señales (P4).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.governance import governance_flags


def _project(name, status="Open"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": status})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "status", status, update_modified=False)
	return pid


def _charter(project):
	d = frappe.get_doc({"doctype": "PMO Project Charter", "project": project, "objective": "X"})
	d.insert(ignore_permissions=True)
	d.submit()
	return d


def _closure(project):
	d = frappe.get_doc(
		{
			"doctype": "PMO Project Closure",
			"project": project,
			"closure_date": "2026-03-31",
			"final_result": "ok",
		}
	)
	d.insert(ignore_permissions=True)
	d.submit()
	return d


class TestGovernanceDashboard(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_needs_closure_includes_cancelled(self):
		# Semántica canónica: terminal (Completed O Cancelled) sin Closure → needs_closure.
		pc = _project("GD Completed", status="Completed")
		self.assertTrue(governance_flags(pc)["needs_closure"])
		px = _project("GD Cancelled", status="Cancelled")
		self.assertTrue(governance_flags(px)["needs_closure"])
		po = _project("GD Open", status="Open")
		self.assertFalse(governance_flags(po)["needs_closure"])  # no terminal

	def test_needs_closure_false_after_closure(self):
		p = _project("GD Closed", status="Completed")
		_closure(p)
		f = governance_flags(p)
		self.assertFalse(f["needs_closure"])
		self.assertTrue(f["needs_review"])  # cerrado sin Review

	def test_has_charter_signal(self):
		p = _project("GD Charter")
		self.assertFalse(governance_flags(p)["has_charter"])
		_charter(p)
		self.assertTrue(governance_flags(p)["has_charter"])

	def test_dashboard_governance_block_consumes_signals(self):
		from pmo.dashboard import governance_block

		p = _project("GD Dash", status="Completed")  # terminal sin Closure → aparece en la sección
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		gov = governance_block()["governance"]
		self.assertIn("counts", gov)
		self.assertIn("items", gov)
		self.assertGreaterEqual(gov["counts"]["needs_closure"], 1)
		self.assertTrue(any(it["project"] == p for it in gov["items"]))
