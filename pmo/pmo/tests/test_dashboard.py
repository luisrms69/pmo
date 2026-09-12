# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.dashboard (agregadores del Workspace PMO híbrido).

Number Cards nativas (Custom) -> portfolio_kpi / resource_kpi. Custom Blocks -> attention_block /
customers_block. Todo reutiliza motores existentes (P4); aquí se verifica el contrato del payload."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from pmo.dashboard import (
	_KPI_METRICS,
	_RESOURCE_METRICS,
	attention_block,
	customers_block,
	portfolio_kpi,
	resource_kpi,
)


class TestPMODashboard(IntegrationTestCase):
	def test_kpi_metrics(self):
		for m in _KPI_METRICS:
			res = portfolio_kpi(json.dumps({"metric": m}))
			self.assertIn("value", res)
			self.assertGreaterEqual(res["value"], 0)

	def test_resource_metrics(self):
		for m in _RESOURCE_METRICS:
			res = resource_kpi(json.dumps({"metric": m}))
			self.assertIn("value", res)
			self.assertGreaterEqual(res["value"], 0)

	def test_unknown_metrics_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			portfolio_kpi(json.dumps({"metric": "nope"}))
		with self.assertRaises(frappe.ValidationError):
			resource_kpi(json.dumps({"metric": "nope"}))

	def test_attention_block(self):
		d = attention_block()
		self.assertIn("attention", d)
		self.assertIn("delayed_tasks", d)
		# atención: nunca proyectos sanos sin excepción
		for a in d["attention"]:
			self.assertTrue(
				a["health_key"] in ("at_risk", "deviated") or a["overdue"] or a["forecast_exceeds"]
			)
		# tareas atrasadas: siempre con fin esperado y atraso >= 0
		for t in d["delayed_tasks"]:
			self.assertIsNotNone(t["exp_end_date"])
			self.assertGreaterEqual(t["delay_days"], 0)

	def test_customers_block(self):
		d = customers_block()
		self.assertIn("customers", d)
		self.assertIsInstance(d["customers"], list)
