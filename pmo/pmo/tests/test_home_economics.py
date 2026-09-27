# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — agregación económica de la Home PMO (BLOQUE 1). Reglas críticas aprobadas:

- Gate económico: sin rol económico → `has_access=False` (KPIs devuelven None; no se expone economía).
- `authorized_revenue=None` (proyecto sin propuesta) se EXCLUYE de la suma, nunca se convierte en 0.
- Estados `inconsistent` se cuentan aparte (trazabilidad) y no falsean el agregado.
- Costo real = comparable_cost (labor + externo, sin material), misma semántica que Project Control.
- Agregación por cliente respeta las mismas reglas.

Se mockean los seams de módulo (`_project_native`, `can_see_project_economics`,
`get_authorized_economics`) — deterministas y fiables — en vez de `frappe.db.get_value`."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from pmo import dashboard

_ROWS = [{"project": "P1"}, {"project": "P2"}, {"project": "P3"}]
_CUST = {"P1": "CustA", "P2": "CustA", "P3": "CustB"}

# Reales nativos ya compuestos (billed / comparable_cost / currency), como los devuelve _project_native.
_NATIVE = {
	"P1": {"billed": 500.0, "comparable_cost": 150.0, "currency": "MXN"},
	"P2": {"billed": 200.0, "comparable_cost": 0.0, "currency": "MXN"},
	"P3": {"billed": 0.0, "comparable_cost": 15.0, "currency": "MXN"},
}
_AUTH = {
	"P1": {"available": True, "reason": None, "data": {"authorized_revenue": 1000, "authorized_margin": 200}},
	"P2": {"available": False, "reason": "no_proposal", "data": None},
	"P3": {"available": False, "reason": "inconsistent", "data": None},
}


def _mocks(auth=None, gate=None):
	auth = auth or _AUTH
	return (
		patch.object(dashboard, "can_see_project_economics", side_effect=gate or (lambda p: True)),
		patch.object(dashboard, "get_authorized_economics", side_effect=lambda p: auth[p]),
		patch.object(dashboard, "_project_native", side_effect=lambda p: _NATIVE[p]),
	)


class TestHomeEconomics(IntegrationTestCase):
	def test_no_access_without_economic_role(self):
		with patch.object(frappe, "get_roles", return_value=["Projects User", "Employee"]):
			self.assertEqual(dashboard._economics(_ROWS, _CUST), {"has_access": False})

	def test_aggregate_excludes_none_and_counts_states(self):
		m1, m2, m3 = _mocks()
		with m1, m2, m3:
			econ = dashboard._economics(_ROWS, _CUST)
		self.assertTrue(econ["has_access"])
		self.assertEqual(econ["authorized_revenue"], 1000.0)  # solo P1 disponible; P2/P3 excluidos
		self.assertEqual(econ["authorized_margin"], 200.0)
		self.assertEqual(econ["billed"], 700.0)  # 500 + 200 + 0
		self.assertEqual(econ["real_cost"], 165.0)  # 150 + 0 + 15
		self.assertEqual(econ["projects_counted"], 3)
		self.assertEqual(econ["authorized_count"], 1)
		self.assertEqual(econ["excluded_no_proposal"], 1)
		self.assertEqual(econ["inconsistent"], 1)
		self.assertEqual(econ["currency"], "MXN")

	def test_authorized_none_when_no_available(self):
		auth_none = {p: {"available": False, "reason": "no_proposal", "data": None} for p in _NATIVE}
		m1, m2, m3 = _mocks(auth=auth_none)
		with m1, m2, m3:
			econ = dashboard._economics(_ROWS, _CUST)
		# Ningún autorizado disponible → None (NO 0), para no falsear.
		self.assertIsNone(econ["authorized_revenue"])
		self.assertIsNone(econ["authorized_margin"])
		self.assertEqual(econ["billed"], 700.0)  # billed/real cost son reales nativos (0 legítimo)

	def test_per_customer_aggregation(self):
		m1, m2, m3 = _mocks()
		with m1, m2, m3:
			econ = dashboard._economics(_ROWS, _CUST)
		pc = econ["per_customer"]
		self.assertEqual(pc["CustA"]["authorized"], 1000.0)  # P1 aporta; P2 no_proposal no suma
		self.assertEqual(pc["CustA"]["billed"], 700.0)
		self.assertIsNone(pc["CustB"]["authorized"])  # P3 inconsistente → sin autorizado
		self.assertEqual(pc["CustB"]["billed"], 0.0)

	def test_gate_skips_non_visible_projects(self):
		# can_see_project_economics False para P2 → no cuenta en ningún agregado.
		m1, m2, m3 = _mocks(gate=lambda p: p != "P2")
		with m1, m2, m3:
			econ = dashboard._economics(_ROWS, _CUST)
		self.assertEqual(econ["projects_counted"], 2)  # P1 y P3
		self.assertEqual(econ["billed"], 500.0)  # solo P1 (P3 billed 0)
		# CustA queda solo con P1 (P2 saltado por el gate): billed 500, no 700.
		self.assertEqual(econ["per_customer"]["CustA"]["billed"], 500.0)
		self.assertEqual(econ["per_customer"]["CustA"]["authorized"], 1000.0)
