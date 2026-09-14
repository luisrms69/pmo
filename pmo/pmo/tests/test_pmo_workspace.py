# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Workspace landing "PMO" (arquitectura híbrida native-first).

Nativo por defecto: Number Cards (KPIs + recursos), un Dashboard Chart **Report-type** (seguro para
P4, sin cache_source global), Quick List de cambios, Shortcuts y Cards (Governance/Reports). Custom
Blocks solo para lo derivado sin equivalente nativo: "PMO Attention" y "PMO Customers"."""

import frappe
from frappe.tests import IntegrationTestCase

HERO_PAGE_SHORTCUTS = {"pmo_portfolio", "pmo_project_control", "capacity_planning"}
NUMBER_CARDS = {
	"PMO Active Projects",
	"PMO Active Tasks",
	"PMO People Involved",
	"PMO Requiring Attention",
	"PMO Overdue Tasks",
	"PMO Active Clients",
	"PMO Projects Without Baseline",
}
CHARTS = {"PMO Portfolio Health", "PMO Capacity Snapshot", "PMO Top Projects by Effort"}
CUSTOM_BLOCKS = {"PMO Attention", "PMO Customers"}
REPORT_LINKS = {
	"PMO Portfolio",
	"PMO Status Report",
	"PMO Planned vs Actual",
	"PMO Baseline Comparison",
	"PMO Change Register",
	"PMO Capacity Planning",
	"PMO Resource Capacity",
	"PMO Resource Usage by Project",
	"PMO Work by Resource",
}
GOVERNANCE_LINKS = {"PMO Project Baseline", "PMO Change Request", "PMO Capacity"}
ROLES = {"Projects User", "Employee", "PMO Manager", "PMO Executive Access", "System Manager"}


class TestPMOWorkspace(IntegrationTestCase):
	def test_landing_exists_public_and_first(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO"))
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual(ws.public, 1)
		self.assertEqual({r.role for r in ws.roles}, ROLES)
		self.assertLess(ws.sequence_id, 20)

	def test_hero_shortcuts_are_the_three_experiences(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual({s.link_to for s in ws.shortcuts if s.type == "Report"}, set())
		self.assertEqual({s.link_to for s in ws.shortcuts if s.type == "Page"}, HERO_PAGE_SHORTCUTS)

	def test_native_number_cards(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual({c.number_card_name for c in ws.number_cards}, NUMBER_CARDS)
		pqc = frappe.get_hooks("permission_query_conditions") or {}
		for nc in NUMBER_CARDS:
			self.assertTrue(frappe.db.exists("Number Card", nc), f"Number Card inexistente: {nc}")
			doc = frappe.get_doc("Number Card", nc)
			if doc.type == "Custom":
				# KPI derivado via método server-side P4 (nunca get_all/ignore_permissions).
				self.assertIn(doc.method, ("pmo.dashboard.portfolio_kpi", "pmo.dashboard.resource_kpi"))
				# document_type declarado (legible por roles PMO) para pasar el pqc del widget.
				self.assertIn(doc.document_type, pqc, f"{nc}: Custom sin document_type con P4")
			else:
				# Document Type nativo → cuenta directa con permission_query_conditions.
				self.assertEqual(doc.type, "Document Type")
				self.assertIn(doc.document_type, pqc, f"{nc}: DocType sin P4")

	def test_charts_are_report_type_p4_safe(self):
		# Todos los charts son Report-type (query_report.run, sin cache_source global). No Group By/Count.
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual({c.chart_name for c in ws.charts}, CHARTS)
		for name in CHARTS:
			chart = frappe.get_doc("Dashboard Chart", name)
			self.assertEqual(chart.chart_type, "Report", f"{name} no es Report-type")
			self.assertTrue(frappe.db.exists("Report", chart.report_name), f"{name}: report inexistente")

	def test_custom_blocks_are_the_two_justified(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual({c.custom_block_name for c in ws.custom_blocks}, CUSTOM_BLOCKS)
		for cb in CUSTOM_BLOCKS:
			self.assertTrue(frappe.db.exists("Custom HTML Block", cb))

	def test_open_changes_is_native_quick_list(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertIn("PMO Change Request", {q.document_type for q in ws.quick_lists})

	def test_links_group_reports_and_governance(self):
		ws = frappe.get_doc("Workspace", "PMO")
		report_links = {li.link_to for li in ws.links if li.type == "Link" and li.link_type == "Report"}
		doctype_links = {li.link_to for li in ws.links if li.type == "Link" and li.link_type == "DocType"}
		self.assertEqual(report_links, REPORT_LINKS)
		self.assertEqual(doctype_links, GOVERNANCE_LINKS)
		page_links = {li.link_to for li in ws.links if li.type == "Link" and li.link_type == "Page"}
		self.assertIn("tag_import", page_links)
		cards = {li.label for li in ws.links if li.type == "Card Break"}
		self.assertEqual(cards, {"PMO Governance", "Reports"})

	def test_existing_workspaces_untouched(self):
		cap = {s.link_to for s in frappe.get_doc("Workspace", "PMO Capacity").shortcuts if s.type == "Report"}
		self.assertEqual(
			cap, {"PMO Capacity Planning", "PMO Resource Usage by Project", "PMO Work by Resource"}
		)
		ctl = {s.link_to for s in frappe.get_doc("Workspace", "PMO Control").shortcuts if s.type == "Report"}
		self.assertEqual(
			ctl,
			{"PMO Planned vs Actual", "PMO Status Report", "PMO Baseline Comparison", "PMO Change Register"},
		)
