# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Status Date (ADR-0006).

- Bloque 1: validación de `Project.pmo_status_date` (<= today, D2), sobre un `Project` en memoria.
- Bloque 2: motor — `compute_status` (indicadores D5, composición pura) y `_resolve_status_date` (D2/D3),
  probados en aislamiento sin depender de Company (el site de tests tiene 0 Companies).
"""

import unittest

import frappe
from frappe.exceptions import ValidationError
from frappe.utils import add_days, getdate, today

from pmo.status_date import (
	_resolve_status_date,
	compute_status,
	validate_project_status_date,
)


class TestStatusDateValidation(unittest.TestCase):
	def _project(self, status_date):
		doc = frappe.new_doc("Project")
		doc.project_name = "SD Test " + frappe.generate_hash(length=6)
		doc.pmo_status_date = status_date
		return doc

	def test_future_status_date_rejected(self):
		doc = self._project(add_days(today(), 1))
		with self.assertRaises(ValidationError):
			validate_project_status_date(doc)

	def test_today_status_date_allowed(self):
		doc = self._project(today())
		validate_project_status_date(doc)  # no debe lanzar

	def test_past_status_date_allowed(self):
		doc = self._project(add_days(today(), -30))
		validate_project_status_date(doc)  # no debe lanzar

	def test_empty_status_date_allowed(self):
		doc = self._project(None)
		validate_project_status_date(doc)  # vacío = sin corte, válido


def _snap(end_date, tasks):
	return {"project": {"expected_end_date": end_date}, "tasks": tasks}


def _task(name, exp_end_date, is_group=0):
	return {"name": name, "subject": name, "exp_end_date": exp_end_date, "is_group": is_group}


class TestStatusDateEngine(unittest.TestCase):
	"""Bloque 2 — composición pura de indicadores D5 y resolución de la fecha (D2/D3)."""

	def test_resolve_future_rejected(self):
		with self.assertRaises(ValidationError):
			_resolve_status_date("ANY", add_days(today(), 1))

	def test_resolve_past_ok(self):
		past = add_days(today(), -10)
		self.assertEqual(_resolve_status_date("ANY", past), getdate(past))

	def test_final_date_slip_days(self):
		# D5.1: Current termina 11 días después que Baseline.
		r = compute_status(_snap("2026-06-30", []), _snap("2026-07-11", []), 0, {}, today())
		self.assertEqual(r["final_date_slip_days"], 11)

	def test_no_baseline_none_slip_zero_counts_actual_passthrough(self):
		r = compute_status(None, _snap("2026-07-11", []), 12.5, {}, today())
		self.assertIsNone(r["final_date_slip_days"])
		self.assertEqual(r["counts"]["baseline_due_by_cutoff"], 0)
		self.assertEqual(r["actual_hours_to_date"], 12.5)

	def test_overdue_and_completed_counts(self):
		sd = "2026-03-31"
		# T1 vencía y se completó a tiempo; T2 vencía y no; T3 vence después (ignorada); G1 group (ignorada).
		baseline = _snap(
			"2026-06-30",
			[
				_task("T1", "2026-03-10"),
				_task("T2", "2026-03-20"),
				_task("T3", "2026-04-15"),
				_task("G1", "2026-03-01", is_group=1),
			],
		)
		completed = {"T1": getdate("2026-03-09"), "T2": None}
		r = compute_status(baseline, _snap("2026-06-30", []), 40, completed, sd)
		self.assertEqual(r["counts"]["baseline_due_by_cutoff"], 2)  # T1, T2
		self.assertEqual(r["counts"]["completed_by_cutoff"], 1)  # T1
		self.assertEqual(r["tasks_overdue_at_cutoff"]["count"], 1)  # T2
		self.assertEqual(r["tasks_overdue_at_cutoff"]["tasks"][0]["name"], "T2")

	def test_completed_after_cutoff_counts_as_overdue(self):
		sd = "2026-03-31"
		baseline = _snap("2026-06-30", [_task("T1", "2026-03-10")])
		completed = {"T1": getdate("2026-04-05")}  # completada, pero después del corte
		r = compute_status(baseline, _snap("2026-06-30", []), 0, completed, sd)
		self.assertEqual(r["counts"]["completed_by_cutoff"], 0)
		self.assertEqual(r["tasks_overdue_at_cutoff"]["count"], 1)
