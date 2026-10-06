# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Workspace landing "PMO" (rescate BLOQUE 1, 2ª pasada de presentación).

Composición ejecutiva coherente (autorizada): Custom HTML Blocks de composición + un Dashboard Chart
nativo. La Home tiene SOLO, en este orden:
1. Encabezado.
2. Resumen ejecutivo (Custom Block): Proyectos activos · Valor autorizado · Facturado · Costo real.
3. Resumen visual: Salud del portafolio (Dashboard Chart nativo) + Situación económica (Custom Block).
4. Panorama operativo (Custom Block): En riesgo/desviados · Tareas vencidas · Utilización.
5. Cartera por cliente (Custom Block): salud + económicos gateados.

Nada más: SIN number cards sueltos, SIN shortcuts, SIN quick lists, SIN links (reportes) y SIN
Gobernanza en la Home (la navegación vive en el Workspace Sidebar). Solo presentación: las fuentes,
métricas y endpoints (portfolio_kpi / resource_kpi / economics_block / customers_block) no cambian."""

import json

import frappe
from frappe.tests import IntegrationTestCase

HOME_BLOCKS = {
	"PMO Resumen Ejecutivo",
	"PMO Situación Económica",
	"PMO Panorama Operativo",
	"PMO Customers",
}
CHARTS = {"PMO Portfolio Health"}
ROLES = {"Projects User", "Employee", "PMO Manager", "PMO Executive Access", "System Manager"}


class TestPMOWorkspace(IntegrationTestCase):
	def test_landing_exists_public_and_first(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO"))
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual(ws.public, 1)
		self.assertEqual({r.role for r in ws.roles}, ROLES)
		self.assertLess(ws.sequence_id, 20)

	def test_home_is_only_composition_blocks_and_health_chart(self):
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual({c.custom_block_name for c in ws.custom_blocks}, HOME_BLOCKS)
		self.assertEqual({c.chart_name for c in ws.charts}, CHARTS)
		for cb in HOME_BLOCKS:
			self.assertTrue(frappe.db.exists("Custom HTML Block", cb), f"bloque inexistente: {cb}")

	def test_health_chart_is_report_type(self):
		chart = frappe.get_doc("Dashboard Chart", "PMO Portfolio Health")
		self.assertEqual(chart.chart_type, "Report")
		self.assertTrue(frappe.db.exists("Report", chart.report_name))

	def test_home_has_no_native_widgets_or_nav(self):
		# La Home termina después de Cartera: sin cards sueltos, shortcuts, quick lists ni links (reportes).
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertEqual(list(ws.number_cards), [])
		self.assertEqual(list(ws.shortcuts), [])
		self.assertEqual(list(ws.quick_lists), [])
		self.assertEqual(list(ws.links), [])

	def test_content_sections_order_and_composition(self):
		# El content refleja exactamente las 5 secciones (headers + widgets), sin nada más.
		ws = frappe.get_doc("Workspace", "PMO")
		content = json.loads(ws.content)
		types = [c["type"] for c in content]
		self.assertEqual(
			types,
			[
				"header",  # PMO — Oficina de proyectos
				"header",  # Resumen ejecutivo
				"custom_block",  # PMO Resumen Ejecutivo
				"header",  # Resumen visual
				"chart",  # Salud del portafolio
				"custom_block",  # PMO Situación Económica
				"header",  # Panorama operativo
				"custom_block",  # PMO Panorama Operativo
				"header",  # Cartera por cliente
				"custom_block",  # PMO Customers
			],
		)
		blocks = [c["data"].get("custom_block_name") for c in content if c["type"] == "custom_block"]
		self.assertEqual(
			blocks,
			["PMO Resumen Ejecutivo", "PMO Situación Económica", "PMO Panorama Operativo", "PMO Customers"],
		)

	def test_reusable_endpoints_preserved(self):
		# Solo presentación: los endpoints reutilizables siguen existiendo y son invocables.
		from pmo import dashboard

		for fn in ("portfolio_kpi", "resource_kpi", "economic_kpi", "economics_block", "customers_block"):
			self.assertTrue(callable(getattr(dashboard, fn, None)), f"endpoint faltante: {fn}")
