# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0008 D4 — Workspace PMO Control (solo navegación). Datos ficticios.

Agrupa shortcuts a los 4 reportes de control (Planificado vs Real, Status Report, Baseline Comparison,
Change Register). NO materializa métricas (los KPIs viven dentro de cada Script Report, P4). No toca
`PMO Capacity`. Requiere migrate para existir.
"""

import frappe
from frappe.tests import IntegrationTestCase

REPORTS = {
	"PMO Planned vs Actual",
	"PMO Status Report",
	"PMO Baseline Comparison",
	"PMO Change Register",
}
ROLES = {"Projects User", "PMO Executive Access", "System Manager"}


class TestControlWorkspace(IntegrationTestCase):
	def test_workspace_exists(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO Control"))

	def test_shortcuts_open_the_four_reports(self):
		ws = frappe.get_doc("Workspace", "PMO Control")
		report_shortcuts = {s.link_to for s in ws.shortcuts if s.type == "Report"}
		self.assertEqual(report_shortcuts, REPORTS)
		for report in report_shortcuts:
			self.assertTrue(frappe.db.exists("Report", report), f"Report inexistente: {report}")

	def test_visibility_restricted_by_roles_not_public_to_everyone(self):
		ws = frappe.get_doc("Workspace", "PMO Control")
		self.assertEqual(ws.public, 1)  # workspace compartido de app
		self.assertEqual({r.role for r in ws.roles}, ROLES)  # restringido a estos roles

	def test_workspace_has_no_cached_metric_components(self):
		# Regla: el Workspace solo navega; sin charts ni number_cards (no duplica lógica/métricas).
		ws = frappe.get_doc("Workspace", "PMO Control")
		self.assertEqual(list(ws.charts), [])
		self.assertEqual(list(ws.number_cards), [])

	def test_capacity_workspace_untouched(self):
		# ADR-0008 D4: PMO Capacity queda dedicado a capacidad; PMO Control no lo altera.
		cap = frappe.get_doc("Workspace", "PMO Capacity")
		cap_reports = {s.link_to for s in cap.shortcuts if s.type == "Report"}
		self.assertEqual(
			cap_reports,
			{"PMO Capacity Planning", "PMO Resource Usage by Project", "PMO Work by Resource"},
		)
