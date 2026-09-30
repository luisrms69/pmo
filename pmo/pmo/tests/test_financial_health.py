# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del compositor PURO de Financial Health (pmo.financial_health) — ADR-0013b.

Valida la matriz QA aprobada (avance vs costo → estado/brecha) y todos los casos especiales."""

import unittest

from pmo.financial_health import compute_financial_health


def _sig(progress_pct, cost_pct, has_authorized=True, inconsistent=False, authorized=100.0):
	"""Señales con autorizado=100 → cost_pct% mapea directo a cost_consumption; progress_pct = percent_complete."""
	return {
		"financial_inconsistent": inconsistent,
		"has_authorized": has_authorized,
		"authorized_cost": authorized,
		"comparable_cost": cost_pct,  # sobre authorized=100 → cost_pct%
		"percent_complete": progress_pct,  # avance nativo (0..100)
	}


class TestFinancialHealthMatrix(unittest.TestCase):
	def test_qa_matrix(self):
		# (avance%, costo%, estado esperado)
		matrix = [
			(10, 10, "healthy"),
			(10, 25, "cost_pressure"),  # gap +15 (borde)
			(25, 50, "unfavorable"),
			(50, 55, "healthy"),  # gap +5 (borde)
			(50, 65, "cost_pressure"),  # gap +15 (borde)
			(50, 75, "unfavorable"),
			(80, 85, "healthy"),
			(100, 95, "healthy"),
			(100, 110, "over_budget"),
			(0, 0, "na"),
			(0, 5, "unfavorable"),
		]
		for progress, cost, expected in matrix:
			with self.subTest(progress=progress, cost=cost):
				r = compute_financial_health(_sig(progress, cost))
				self.assertEqual(r["state"], expected, f"{progress}%/{cost}% → {r}")

	def test_cost_gap_values(self):
		r = compute_financial_health(_sig(40, 52))  # ejemplo del prompt: +12 pp
		self.assertEqual(r["cost_gap"], 12.0)
		self.assertEqual(r["state"], "cost_pressure")
		self.assertEqual(r["physical_progress"], 0.4)
		self.assertEqual(r["cost_consumption"], 0.52)

	def test_boundaries(self):
		self.assertEqual(compute_financial_health(_sig(50, 55))["state"], "healthy")  # +5 exacto
		self.assertEqual(compute_financial_health(_sig(50, 56))["state"], "cost_pressure")  # +6
		self.assertEqual(compute_financial_health(_sig(50, 65))["state"], "cost_pressure")  # +15 exacto
		self.assertEqual(compute_financial_health(_sig(50, 66))["state"], "unfavorable")  # +16


class TestFinancialHealthSpecialCases(unittest.TestCase):
	def test_inconsistent(self):
		r = compute_financial_health(_sig(50, 50, inconsistent=True))
		self.assertEqual(r["state"], "unavailable")
		self.assertEqual(r["reason"], "inconsistent")
		self.assertFalse(r["applicable"])

	def test_no_authorized_reference(self):
		r = compute_financial_health(_sig(50, 50, has_authorized=False))
		self.assertEqual(r["state"], "na")
		self.assertEqual(r["reason"], "no_authorized")
		self.assertFalse(r["applicable"])

	def test_not_started(self):
		r = compute_financial_health(_sig(0, 0))
		self.assertEqual(r["state"], "na")
		self.assertEqual(r["reason"], "not_started")

	def test_progress_zero_with_cost_is_unfavorable(self):
		r = compute_financial_health(_sig(0, 3))
		self.assertEqual(r["state"], "unfavorable")
		self.assertTrue(r["applicable"])

	def test_authorized_zero_with_cost_is_over_budget(self):
		r = compute_financial_health(_sig(50, 10, authorized=0.0))  # authorized 0, comp 10 > 0
		self.assertEqual(r["state"], "over_budget")
		self.assertIsNone(r["cost_consumption"])  # ratio indefinido con autorizado 0

	def test_completed_project_over_budget(self):
		r = compute_financial_health(_sig(100, 110))
		self.assertEqual(r["state"], "over_budget")

	def test_completed_project_on_budget(self):
		r = compute_financial_health(_sig(100, 95))
		self.assertEqual(r["state"], "healthy")

	def test_favorable_under_cost_is_healthy(self):
		r = compute_financial_health(_sig(60, 40))  # gap -20 → healthy
		self.assertEqual(r["state"], "healthy")
		self.assertEqual(r["cost_gap"], -20.0)


if __name__ == "__main__":
	unittest.main()
