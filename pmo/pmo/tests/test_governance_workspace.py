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

	def test_sidebar_includes_governance(self):
		# Modelo Frappe v16.5+: el sidebar de la app es una DEFINICIÓN estándar
		# (`workspace_sidebar/pmo.json`) que el runtime ensambla en boot; no un registro materializado
		# por install. Validamos esa metadata estándar (navegación de gobierno + accesos conservados) y
		# que el Workspace de gobierno destino exista.
		import os

		path = os.path.join(frappe.get_app_path("pmo"), "workspace_sidebar", "pmo.json")
		self.assertTrue(os.path.exists(path), "falta la definición estándar del Workspace Sidebar PMO")
		with open(path) as f:
			sb = json.load(f)

		self.assertEqual(sb.get("title"), "PMO")
		self.assertEqual(sb.get("module"), "PMO")
		self.assertTrue(sb.get("standard"))

		items = sb.get("items", [])
		labels = [i.get("label") for i in items]
		self.assertIn("Gobernanza PMO", labels)
		gov = next(i for i in items if i.get("label") == "Gobernanza PMO")
		self.assertEqual(gov.get("link_type"), "Workspace")
		self.assertEqual(gov.get("link_to"), "PMO Governance")

		# Accesos conservados (incluye las Pages de capacidad y control que permanecen).
		for expected in ["PMO", "Portafolio", "Control de Proyecto", "Planificación de capacidad"]:
			self.assertIn(expected, labels)

		# No quedan referencias a los Workspaces legacy retirados en v16.5+.
		link_targets = {i.get("link_to") for i in items}
		self.assertNotIn("PMO Capacity", link_targets)
		self.assertNotIn("PMO Control", link_targets)

		# El Workspace de gobierno destino sí se materializa.
		self.assertTrue(frappe.db.exists("Workspace", "PMO Governance"))

	def test_legacy_sections_removed_from_content(self):
		# El dashboard no debe volver a parecer un Workspace genérico: el `content` deja solo header + bloque.
		ws = frappe.get_doc("Workspace", "PMO Governance")
		content = json.loads(ws.content)
		types = [c.get("type") for c in content]
		self.assertEqual(types, ["header", "custom_block"])
		raw = ws.content
		for legacy in [
			"Governance documents",
			"Project file",
			"Risk management",
			"Risk configuration",
			"Continuous improvement",
		]:
			self.assertNotIn(legacy, raw)

	def test_dashboard_cards_hide_not_applicable_but_engine_keeps_it(self):
		# Decisión de presentación: las tarjetas muestran solo Completos/Pendientes; "No aplica" se retira de
		# la UI pero el motor lo sigue calculando (contrato interno intacto).
		blk = frappe.get_doc("Custom HTML Block", "PMO Governance")
		self.assertIn("Complete", blk.script)
		self.assertIn("Pending", blk.script)
		self.assertNotIn("Not applicable", blk.script)
		# El motor conserva no_aplica en el payload agregado.
		from pmo.governance_inbox import governance_board

		stages = governance_board()["stages"]
		self.assertTrue(all("no_aplica" in s for s in stages))

	def test_main_workspace_no_longer_embeds_panel(self):
		# El panel completo vive solo en su landing; el Workspace PMO no lo duplica como custom_block.
		ws = frappe.get_doc("Workspace", "PMO")
		self.assertNotIn("PMO Governance", {b.custom_block_name for b in ws.custom_blocks})
