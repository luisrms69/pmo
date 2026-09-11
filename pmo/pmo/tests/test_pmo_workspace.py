# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Workspace landing "PMO" (ronda product-readiness). Solo navegación.

Verifica que el landing existe, enlaza (shortcuts + cards) las capacidades ya implementadas, no materializa
métricas (sin charts/number_cards), y **no altera** los workspaces `PMO Capacity` / `PMO Control`."""

import frappe
from frappe.tests import IntegrationTestCase

HERO_SHORTCUTS = {"PMO Portfolio", "PMO Status Report", "PMO Capacity Planning"}
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

	def test_hero_shortcuts_open_reports(self):
		ws = frappe.get_doc("Workspace", "PMO")
		got = {s.link_to for s in ws.shortcuts if s.type == "Report"}
		self.assertEqual(got, HERO_SHORTCUTS)

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
		# todos los reportes enlazados existen (sin enlaces rotos)
		for r in REPORT_LINKS:
			self.assertTrue(frappe.db.exists("Report", r), f"Report inexistente: {r}")
		# card breaks presentes
		cards = {link.label for link in ws.links if link.type == "Card Break"}
		self.assertEqual(cards, {"Portfolio & control", "Capacity", "PMO configuration"})

	def test_no_cached_metrics(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual(list(ws.charts), [])
		self.assertEqual(list(ws.number_cards), [])

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
