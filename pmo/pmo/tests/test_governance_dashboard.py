# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D9 — señales de gobierno (governance_flags) + sección Project Governance del Dashboard.

Datos ficticios. Cubre: semántica canónica de needs_closure ({Completed, Cancelled} sin Closure),
has_handoff/needs_review/open_change_requests, y que el bloque del Dashboard consume esas señales (P4).
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


def _handoff(project):
	# El Handoff exige responsable operativo interno + contacto del cliente en el Project para emitirse.
	emp = frappe.db.exists("Employee", {"employee_name": "GD Op Owner"}) or (
		frappe.get_doc({"doctype": "Employee", "employee_name": "GD Op Owner", "first_name": "GD"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	ct = frappe.db.exists("Contact", {"first_name": "GD Contact"}) or (
		frappe.get_doc({"doctype": "Contact", "first_name": "GD Contact"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", project, "pmo_operational_owner", emp, update_modified=False)
	frappe.db.set_value("Project", project, "pmo_customer_contact", ct, update_modified=False)
	d = frappe.get_doc(
		{"doctype": "PMO Project Handoff", "project": project, "handoff_summary": "Transferencia X"}
	)
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

	def test_has_handoff_signal(self):
		p = _project("GD Handoff")
		self.assertFalse(governance_flags(p)["has_handoff"])
		_handoff(p)
		self.assertTrue(governance_flags(p)["has_handoff"])

	def test_open_change_request_only_appears_in_items(self):
		from pmo.dashboard import governance_block

		p = _project("GD CROnly", status="Open")  # no terminal, con Handoff → único pendiente = CR abierto
		_handoff(p)
		cr = frappe.get_doc(
			{
				"doctype": "PMO Change Request",
				"project": p,
				"title": "Scope change",
				"reason": "Client request",
			}
		)
		cr.insert(ignore_permissions=True)  # docstatus 0 → workflow_state Draft (abierto)
		f = governance_flags(p)
		self.assertEqual(f["open_change_requests"], 1)
		self.assertFalse(f["needs_closure"])
		self.assertFalse(f["needs_review"])
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		items = governance_block()["governance"]["items"]
		self.assertTrue(any(it["project"] == p for it in items))  # aparece por CR abierto

	def test_portfolio_row_exposes_governance_flags(self):
		from pmo.pmo.report.pmo_portfolio.pmo_portfolio import execute

		_project("GD PortFlags", status="Open")
		_cols, rows, *_ = execute({})
		self.assertTrue(rows)
		for r in rows:
			self.assertIn("has_handoff", r)
			self.assertIn("needs_closure", r)
			self.assertIn("open_change_requests", r)

	def test_dashboard_governance_block_consumes_signals(self):
		from pmo.dashboard import governance_block

		p = _project("GD Dash", status="Completed")  # terminal sin Closure → aparece en la sección
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		gov = governance_block()["governance"]
		self.assertIn("counts", gov)
		self.assertIn("items", gov)
		self.assertGreaterEqual(gov["counts"]["needs_closure"], 1)
		self.assertTrue(any(it["project"] == p for it in gov["items"]))
