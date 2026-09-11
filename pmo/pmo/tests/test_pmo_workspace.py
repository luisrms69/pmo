# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Workspace landing "PMO" (dashboard informativo).

Verifica que el landing existe, presenta métricas nativas (Number Cards + Dashboard Charts + Quick
List) además de los accesos (shortcuts a las 3 experiencias) y las cards de Informes/Configuración,
no rompe enlaces, y **no altera** los workspaces `PMO Capacity` / `PMO Control`."""

import frappe
from frappe.tests import IntegrationTestCase

# Zona superior = 3 experiencias (Pages); el dashboard informa antes de permitir profundizar.
HERO_PAGE_SHORTCUTS = {"pmo_portfolio", "pmo_project_control", "capacity_planning"}
NUMBER_CARDS = {
	"PMO Projects",
	"PMO Deviated Projects",
	"PMO At Risk Projects",
	"PMO Projects Without Baseline",
	"PMO Overdue Tasks",
	"PMO Forecast Exceeds Commitment",
	"PMO Open Change Requests",
}
CHARTS = {"PMO Projects by Status", "PMO Change Requests by State"}
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
CONFIG_LINKS = {"PMO Capacity", "PMO Project Baseline", "PMO Change Request"}
ROLES = {"Projects User", "Employee", "PMO Manager", "PMO Executive Access", "System Manager"}


class TestPMOWorkspace(IntegrationTestCase):
	def test_landing_exists_public_and_first(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO"))
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual(ws.public, 1)
		self.assertEqual({r.role for r in ws.roles}, ROLES)
		self.assertLess(ws.sequence_id, 20)  # aparece antes que PMO Capacity(20)/PMO Control(30)

	def test_hero_shortcuts_are_the_three_experiences(self):
		ws = frappe.get_doc("Workspace", "PMO")
		# Solo Pages (no shortcuts de Script Report); los reportes viven en la card Reports.
		self.assertEqual({s.link_to for s in ws.shortcuts if s.type == "Report"}, set())
		self.assertEqual({s.link_to for s in ws.shortcuts if s.type == "Page"}, HERO_PAGE_SHORTCUTS)

	def test_dashboard_has_native_metrics(self):
		ws = frappe.get_doc("Workspace", "PMO")
		got_cards = {c.number_card_name for c in ws.number_cards}
		got_charts = {c.chart_name for c in ws.charts}
		self.assertEqual(got_cards, NUMBER_CARDS)
		self.assertEqual(got_charts, CHARTS)
		# los docs referenciados existen (sin widgets rotos)
		for nc in NUMBER_CARDS:
			self.assertTrue(frappe.db.exists("Number Card", nc), f"Number Card inexistente: {nc}")
		for ch in CHARTS:
			self.assertTrue(frappe.db.exists("Dashboard Chart", ch), f"Dashboard Chart inexistente: {ch}")
		# quick list actionable de cambios abiertos
		self.assertIn("PMO Change Request", {q.document_type for q in ws.quick_lists})

	def test_number_cards_are_p4_safe(self):
		# Los cards derivados reutilizan el motor PMO Portfolio (P4 dentro); el card nativo apunta a
		# un DocType con permission_query_conditions. Ninguno usa ignore_permissions.
		pqc = frappe.get_hooks("permission_query_conditions") or {}
		for nc in NUMBER_CARDS:
			doc = frappe.get_doc("Number Card", nc)
			if doc.type == "Custom":
				self.assertEqual(doc.method, "pmo.dashboard.portfolio_kpi")
			elif doc.type == "Document Type":
				self.assertIn(doc.document_type, pqc, f"{nc}: DocType sin P4 (pqc)")

	def test_links_group_all_reports_and_config(self):
		ws = frappe.get_doc("Workspace", "PMO")
		report_links = {
			link.link_to for link in ws.links if link.type == "Link" and link.link_type == "Report"
		}
		doctype_links = {
			link.link_to for link in ws.links if link.type == "Link" and link.link_type == "DocType"
		}
		self.assertEqual(report_links, REPORT_LINKS)
		self.assertEqual(doctype_links, CONFIG_LINKS)
		for r in REPORT_LINKS:
			self.assertTrue(frappe.db.exists("Report", r), f"Report inexistente: {r}")
		# Import Tags como utilidad administrativa (Page) dentro de configuración
		page_links = {link.link_to for link in ws.links if link.type == "Link" and link.link_type == "Page"}
		self.assertIn("tag_import", page_links)
		cards = {link.label for link in ws.links if link.type == "Card Break"}
		self.assertEqual(cards, {"Reports", "PMO configuration"})

	def test_existing_workspaces_untouched(self):
		# PMO Capacity mantiene sus 3 shortcuts; PMO Control sus 4. El landing no los modifica.
		cap = {s.link_to for s in frappe.get_doc("Workspace", "PMO Capacity").shortcuts if s.type == "Report"}
		self.assertEqual(
			cap, {"PMO Capacity Planning", "PMO Resource Usage by Project", "PMO Work by Resource"}
		)
		ctl = {s.link_to for s in frappe.get_doc("Workspace", "PMO Control").shortcuts if s.type == "Report"}
		self.assertEqual(
			ctl,
			{"PMO Planned vs Actual", "PMO Status Report", "PMO Baseline Comparison", "PMO Change Register"},
		)
