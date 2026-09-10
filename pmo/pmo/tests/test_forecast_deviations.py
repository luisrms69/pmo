# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Forecast vigente y desviaciones (ADR-0009). Composición pura de `compute_status` (sin BD).

Cubre las señales nuevas: desviación Current/Forecast End vs fecha comprometida; conteo de Tasks cuyo
forecast excede `pmo_deadline` (distinto de "vencida al corte", puede ser fecha futura); tabla ampliada por
Task (baseline vs forecast, slip, deadline, marca de vencida); y retrocompatibilidad de la firma anterior.
"""

import unittest

from pmo.status_date import compute_status


def _snap(end_date, tasks):
	return {"project": {"expected_end_date": end_date}, "tasks": tasks}


def _btask(name, exp_end_date, is_group=0):
	return {"name": name, "subject": name, "exp_end_date": exp_end_date, "is_group": is_group}


class TestForecastDeviations(unittest.TestCase):
	def test_slip_vs_committed_days(self):
		# Current end 2026-07-10 vs compromiso 2026-06-20 => +20 (el forecast excede el compromiso).
		r = compute_status(
			None, _snap("2026-07-10", []), 0, {}, "2026-06-30", committed_end_date="2026-06-20"
		)
		self.assertEqual(r["slip_vs_committed_days"], 20)

	def test_slip_vs_committed_negative_and_none(self):
		# Forecast antes del compromiso => negativo (mejor). Sin compromiso => None.
		r = compute_status(
			None, _snap("2026-06-10", []), 0, {}, "2026-06-30", committed_end_date="2026-06-20"
		)
		self.assertEqual(r["slip_vs_committed_days"], -10)
		r2 = compute_status(None, _snap("2026-07-10", []), 0, {}, "2026-06-30")
		self.assertIsNone(r2["slip_vs_committed_days"])

	def test_forecast_exceeds_commitment_count(self):
		# Grupo se ignora; T1 (futuro) excede su deadline aunque NO esté vencida; T2 no excede.
		current_task_map = {
			"G": {"exp_end_date": "2026-12-31", "pmo_deadline": "2026-01-01", "is_group": 1},
			"T1": {"exp_end_date": "2026-08-01", "pmo_deadline": "2026-07-01", "is_group": 0},
			"T2": {"exp_end_date": "2026-06-10", "pmo_deadline": "2026-06-15", "is_group": 0},
		}
		r = compute_status(
			None, _snap("2026-07-10", []), 0, {}, "2026-06-30", current_task_map=current_task_map
		)
		self.assertEqual(r["forecast_exceeds_commitment"]["count"], 1)  # solo T1

	def test_expanded_table_and_overdue_differentiation(self):
		# sd=2026-06-30. T1: baseline futuro (no vencida) pero forecast excede deadline.
		#               T2: baseline pasado y sin completar => vencida al corte.
		baseline = _snap(
			"2026-07-15",
			[_btask("T1", "2026-07-15"), _btask("T2", "2026-06-10"), _btask("G", "2026-01-01", is_group=1)],
		)
		current_task_map = {
			"T1": {"exp_end_date": "2026-08-01", "pmo_deadline": "2026-07-01", "is_group": 0},
			"T2": {"exp_end_date": "2026-06-10", "pmo_deadline": "2026-06-15", "is_group": 0},
		}
		r = compute_status(
			baseline,
			_snap("2026-08-01", []),
			0,
			{},  # T2 sin completed_on => vencida
			"2026-06-30",
			committed_end_date="2026-07-01",
			current_task_map=current_task_map,
		)
		rows = {t["name"]: t for t in r["tasks_vs_baseline"]}
		self.assertEqual(set(rows), {"T1", "T2"})  # grupo excluido

		self.assertEqual(rows["T1"]["baseline_exp_end_date"], "2026-07-15")
		self.assertEqual(rows["T1"]["current_exp_end_date"], "2026-08-01")
		self.assertEqual(rows["T1"]["slip_days"], 17)  # 08-01 - 07-15
		self.assertEqual(rows["T1"]["pmo_deadline"], "2026-07-01")
		self.assertFalse(rows["T1"]["overdue_at_status_date"])  # baseline futuro => NO vencida...

		self.assertEqual(rows["T2"]["slip_days"], 0)  # 06-10 - 06-10
		self.assertTrue(rows["T2"]["overdue_at_status_date"])  # baseline pasado, sin completar

		# ...pero T1 SÍ cuenta como "forecast excede compromiso" (distinto de vencida).
		self.assertEqual(r["forecast_exceeds_commitment"]["count"], 1)  # T1
		self.assertEqual(r["tasks_overdue_at_cutoff"]["count"], 1)  # T2

	def test_no_current_data_slip_none(self):
		# Baseline con fecha pero sin plan vigente para esa Task => current/slip None; sigue en la tabla.
		baseline = _snap("2026-07-15", [_btask("T1", "2026-07-15")])
		r = compute_status(baseline, _snap("2026-07-15", []), 0, {}, "2026-06-30")
		row = r["tasks_vs_baseline"][0]
		self.assertIsNone(row["current_exp_end_date"])
		self.assertIsNone(row["slip_days"])
		self.assertIsNone(row["pmo_deadline"])

	def test_backward_compatible_signature(self):
		# Llamada antigua de 5 args (sin ADR-0009) sigue devolviendo lo previo + nuevas claves por defecto.
		r = compute_status(None, _snap("2026-07-11", []), 12.5, {}, "2026-06-30")
		self.assertIsNone(r["final_date_slip_days"])
		self.assertEqual(r["actual_hours_to_date"], 12.5)
		self.assertIsNone(r["slip_vs_committed_days"])
		self.assertEqual(r["forecast_exceeds_commitment"]["count"], 0)
		self.assertEqual(r["tasks_vs_baseline"], [])
