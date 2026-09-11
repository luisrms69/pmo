# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.dashboard.portfolio_kpi (agregador de presentación de los Number Cards del Workspace).

No es un motor nuevo: reutiliza pmo_portfolio.execute (P4 dentro). Aquí se verifica el contrato:
devuelve {"value": <int>} para cada métrica soportada y rechaza métricas desconocidas."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from pmo.dashboard import _METRICS, portfolio_kpi


class TestPMODashboardKPI(IntegrationTestCase):
	def test_known_metrics_return_value(self):
		for metric in _METRICS:
			res = portfolio_kpi(json.dumps({"metric": metric}))
			self.assertIn("value", res)
			self.assertIsNotNone(res["value"])
			self.assertGreaterEqual(res["value"], 0)

	def test_accepts_dict_filters(self):
		# el card puede pasar filtros ya deserializados
		res = portfolio_kpi({"metric": "projects"})
		self.assertIn("value", res)

	def test_unknown_metric_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			portfolio_kpi(json.dumps({"metric": "not_a_metric"}))
