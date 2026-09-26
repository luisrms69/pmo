# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D9 — Workspace independiente "PMO Governance" + item de barra lateral.

Landing de gobierno a nivel portafolio: reutiliza el Custom HTML Block "PMO Governance"
(pmo.dashboard.governance_block) + navegación nativa a los artefactos de gobierno; NO copia contenido
funcional ni crea motores/métricas. Valida el Workspace y el item de Workspace Sidebar (sincronizados por
migrate; este test corre tras migrate)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

GOV_DOCTYPE_LINKS = {
	"PMO Project Handoff",
	"PMO Project Baseline",
	"PMO Change Request",
	"PMO Project Closure",
	"PMO Post-Project Review",
}


class TestGovernanceWorkspace(IntegrationTestCase):
	def test_workspace_exists_public(self):
		self.assertTrue(frappe.db.exists("Workspace", "PMO Governance"))
		ws = frappe.get_doc("Workspace", "PMO Governance")
		self.assertTrue(ws.public)
		self.assertEqual(ws.module, "PMO")

	def test_reuses_custom_block_panel(self):
		ws = frappe.get_doc("Workspace", "PMO Governance")
		self.assertIn("PMO Governance", {b.custom_block_name for b in ws.custom_blocks})
		content = json.loads(ws.content)
		blocks = [c["data"].get("custom_block_name") for c in content if c.get("type") == "custom_block"]
		self.assertIn("PMO Governance", blocks)

	def test_navigation_to_governance_doctypes_and_project_control(self):
		ws = frappe.get_doc("Workspace", "PMO Governance")
		doctype_links = {link.link_to for link in ws.links if link.link_type == "DocType"}
		self.assertTrue(GOV_DOCTYPE_LINKS.issubset(doctype_links))
		page_links = {link.link_to for link in ws.links if link.link_type == "Page"}
		self.assertIn("pmo_project_control", page_links)

	def test_sidebar_has_governance_item(self):
		sb = frappe.get_doc("Workspace Sidebar", "PMO")
		items = [(i.label, i.link_type, i.link_to) for i in sb.items]
		self.assertIn(("PMO Governance", "Workspace", "PMO Governance"), items)

	def test_main_workspace_no_longer_embeds_panel(self):
		# El panel completo vive solo en su landing; el Workspace PMO no lo duplica como custom_block.
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertNotIn("PMO Governance", {b.custom_block_name for b in ws.custom_blocks})
