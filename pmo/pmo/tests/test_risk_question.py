# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 Risk Analysis (R1) — catálogo PMO Risk Question. Datos ficticios.

Cubre: autogeneración de `sort_order` (pasos de 10 por sección, no obligatorio, override manual) y que el
contenido seed se almacena en español (idioma de trabajo), con el campo marcado translatable."""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.setup.risk_catalog import RISK_QUESTION_SEED, seed_risk_questions


class TestRiskQuestionCatalog(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		seed_risk_questions()  # idempotente: garantiza el catálogo inicial (IT con 10..50)

	def _new(self, **kw):
		return frappe.get_doc({"doctype": "PMO Risk Question", **kw}).insert(ignore_permissions=True)

	def test_sort_order_auto_next_in_section(self):
		# Information Technology tiene el seed 10..50 → el siguiente disponible es 60.
		q = self._new(code="IT-TEST-AUTO", section="Information Technology", question="Pregunta de prueba")
		self.assertEqual(q.sort_order, 60)

	def test_sort_order_not_mandatory(self):
		# Crear sin sort_order NO debe fallar (se autogenera).
		q = self._new(code="SCH-TEST-AUTO", section="Schedule", question="Otra prueba")
		self.assertTrue(q.sort_order and q.sort_order > 0)

	def test_sort_order_manual_respected(self):
		q = self._new(
			code="RES-TEST-MANUAL", section="Resources & team", question="Prueba manual", sort_order=15
		)
		self.assertEqual(q.sort_order, 15)

	def test_seed_source_is_spanish(self):
		texts = {code: question for code, _s, question, _o in RISK_QUESTION_SEED}
		self.assertTrue(texts["EXT-01"].startswith("¿"))
		self.assertTrue(texts["IT-01"].startswith("¿"))

	def test_question_field_is_translatable(self):
		meta = frappe.get_meta("PMO Risk Question")
		self.assertTrue(meta.get_field("question").translatable)
