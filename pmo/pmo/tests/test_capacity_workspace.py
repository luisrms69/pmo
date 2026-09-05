# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 vistas — Workspace PMO Capacity (solo navegación). Datos ficticios.

El Workspace solo agrupa shortcuts a los 3 reports; NO materializa métricas P4 (los KPIs/chart viven
dentro de cada Script Report, per-usuario, sin caché compartida). Requiere migrate para existir.
"""

import frappe
from frappe.tests import IntegrationTestCase

REPORTS = {
	"PMO Capacity Planning",
	"PMO Resource Usage by Project",
	"PMO Work by Resource",
}
ROLES = {"Employee", "PMO Manager", "PMO Executive Access", "System Manager"}


class TestCapacityWorkspace(IntegrationTestCase):
	def test_workspace_exists(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO Capacity"))

	def test_shortcuts_open_the_three_reports(self):
		ws = frappe.get_doc("Workspace", "PMO Capacity")
		report_shortcuts = {s.link_to for s in ws.shortcuts if s.type == "Report"}
		self.assertEqual(report_shortcuts, REPORTS)
		for report in report_shortcuts:
			self.assertTrue(frappe.db.exists("Report", report), f"Report inexistente: {report}")

	def test_visibility_restricted_by_roles_not_public_to_everyone(self):
		ws = frappe.get_doc("Workspace", "PMO Capacity")
		self.assertEqual(ws.public, 1)  # workspace compartido de app
		self.assertEqual({r.role for r in ws.roles}, ROLES)  # pero restringido a estos roles

	def test_workspace_has_no_cached_metric_components(self):
		# Regla P4: el Workspace solo navega; no debe materializar métricas vía caché compartida.
		ws = frappe.get_doc("Workspace", "PMO Capacity")
		self.assertEqual(list(ws.charts), [])
		self.assertEqual(list(ws.number_cards), [])
