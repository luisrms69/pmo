# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del orden jerárquico (nested set) del Gantt de Task.

Cubren lo verificable desde backend/configuración: nested set, `lft`, fechas
desordenadas, registro del hook y contenido del asset. NO pretenden demostrar el
comportamiento visual del navegador — esa aceptación es funcional en Desk.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo import hooks

MARKER = "PMO-GANTT-TEST"


class TestGanttTaskOrder(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.names = {}
		# Fechas deliberadamente desordenadas: el orden por fecha NO coincide con lft.
		hierarchy = [
			("A", True, None, "2026-01-10"),  # Categoría A
			("A1", True, "A", "2026-01-05"),  # Subtarea A1 (antes que su padre)
			("A1.1", False, "A1", "2026-03-01"),  # tardía
			("A1.2", False, "A1", "2026-01-01"),  # la más temprana de todas
			("A2", True, "A", "2026-02-01"),
			("A2.1", False, "A2", "2026-01-03"),
		]
		for subject, is_group, parent, start in hierarchy:
			doc = frappe.get_doc(
				{
					"doctype": "Task",
					"subject": f"{MARKER} {subject}",
					"is_group": 1 if is_group else 0,
					"parent_task": cls.names.get(parent),
					"exp_start_date": start,
				}
			).insert(ignore_permissions=True)
			cls.names[subject] = doc.name
		cls.rev = {v: k for k, v in cls.names.items()}

	def _ordered(self, order_by, extra=None):
		names = set(self.names.values()) | set(extra or [])
		rows = frappe.get_all("Task", filters={"name": ["in", list(names)]}, order_by=order_by, pluck="name")
		return [self.rev.get(n, n) for n in rows]

	# --- Nested set / lft ---------------------------------------------------

	def test_lft_order_is_hierarchical_preorder(self):
		"""El orden por lft ASC es el recorrido pre-orden del árbol, no el de fechas."""
		self.assertEqual(
			self._ordered("lft asc"),
			["A", "A1", "A1.1", "A1.2", "A2", "A2.1"],
		)

	def test_date_order_differs_from_lft_order(self):
		"""Ordenar por fecha produce un orden DISTINTO → demuestra que lft es lo que importa."""
		self.assertNotEqual(self._ordered("lft asc"), self._ordered("exp_start_date asc"))

	def test_branches_stay_together(self):
		"""Las hijas de A1 quedan contiguas y dentro del rango de A1 (no se mezclan con A2)."""
		order = self._ordered("lft asc")
		self.assertEqual(order.index("A1.2"), order.index("A1.1") + 1)
		self.assertLess(order.index("A1"), order.index("A1.1"))
		self.assertLess(order.index("A1.2"), order.index("A2"))

	def test_changing_child_date_does_not_change_lft_order(self):
		"""Cambiar la fecha de una hija no altera el orden por lft (no la saca de su rama)."""
		before = self._ordered("lft asc")
		frappe.db.set_value("Task", self.names["A1.2"], "exp_start_date", "2026-12-31")
		self.assertEqual(self._ordered("lft asc"), before)

	def test_new_task_with_parent_lands_inside_branch(self):
		"""Una Task nueva con Parent Task = A1 cae dentro del rango lft..rgt de A1."""
		new = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": f"{MARKER} A1.3",
				"parent_task": self.names["A1"],
				"exp_start_date": "2026-06-01",
			}
		).insert(ignore_permissions=True)
		a1 = frappe.db.get_value("Task", self.names["A1"], ["lft", "rgt"], as_dict=True)
		new_lft = frappe.db.get_value("Task", new.name, "lft")
		self.assertTrue(a1.lft < new_lft < a1.rgt)

	# --- Configuración / asset ---------------------------------------------

	def test_hook_registers_task_calendar_js(self):
		self.assertEqual(hooks.doctype_calendar_js.get("Task"), "public/js/task_calendar_pmo.js")

	def test_asset_sets_gantt_order_by_lft(self):
		content = frappe.read_file(frappe.get_app_path("pmo", "public", "js", "task_calendar_pmo.js"))
		self.assertIn('frappe.views.calendar["Task"]', content)
		self.assertIn("order_by", content)
		self.assertIn('"lft"', content)

	def test_list_and_tree_not_overridden(self):
		"""pmo no registra JS de List ni Tree para Task → esas vistas no se alteran."""
		self.assertNotIn("Task", getattr(hooks, "doctype_list_js", {}) or {})
		self.assertNotIn("Task", getattr(hooks, "doctype_tree_js", {}) or {})
