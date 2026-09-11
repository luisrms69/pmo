# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Status Report (ADR-0006 + ADR-0009, presentación). Capa pura: dado el resultado de
`build_status_report`, se validan columnas, la tabla única por Task (baseline vs forecast, slip, deadline,
vencida) y las tarjetas de resumen (incluye forecast vigente y desviaciones vs Baseline/compromiso).
La validación integrada real (Project/Baseline/Timesheet en un site con Company) es un E2E aparte."""

import unittest

from pmo.pmo.report.pmo_status_report.pmo_status_report import _columns, _rows, _summary

_REPORT = {
	"project": "PROJ-X",
	"status_date": "2026-03-31",
	"baseline": {"name": "PMO-BL-X", "expected_end_date": "2026-06-30"},
	"current": {"expected_end_date": "2026-07-11"},
	"committed_end_date": "2026-06-20",
	"note": None,
	"indicators": {
		"final_date_slip_days": 11,
		"slip_vs_committed_days": 21,
		"forecast_exceeds_commitment": {"count": 2},
		"tasks_overdue_at_cutoff": {
			"count": 1,
			"tasks": [{"name": "T2", "subject": "T2 subj", "baseline_exp_end_date": "2026-03-20"}],
		},
		"tasks_vs_baseline": [
			{
				"name": "T1",
				"subject": "T1 subj",
				"baseline_exp_end_date": "2026-05-01",
				"current_exp_end_date": "2026-05-10",
				"slip_days": 9,
				"pmo_deadline": "2026-05-05",
				"overdue_at_status_date": False,
				"completed_at_status_date": False,
			},
			{
				"name": "T2",
				"subject": "T2 subj",
				"baseline_exp_end_date": "2026-03-20",
				"current_exp_end_date": "2026-04-30",
				"slip_days": 41,
				"pmo_deadline": None,
				"overdue_at_status_date": True,
				"completed_at_status_date": False,
			},
		],
		"actual_hours_to_date": 40.0,
		"counts": {"baseline_due_by_cutoff": 2, "completed_by_cutoff": 1},
	},
}


class TestStatusReportPresentation(unittest.TestCase):
	def test_columns(self):
		cols = _columns()
		self.assertEqual(
			[c["fieldname"] for c in cols],
			[
				"name",
				"subject",
				"baseline_exp_end_date",
				"current_exp_end_date",
				"slip_days",
				"pmo_deadline",
				"overdue",
			],
		)
		name_col = cols[0]
		self.assertEqual(name_col["fieldtype"], "Link")
		self.assertEqual(name_col["options"], "Task")

	def test_rows_are_all_baseline_tasks_sorted_by_slip(self):
		rows = _rows(_REPORT)
		self.assertEqual(len(rows), 2)  # tabla única: todas las Tasks con baseline
		# ordenadas por slip descendente: T2 (41) antes que T1 (9)
		self.assertEqual([r["name"] for r in rows], ["T2", "T1"])
		self.assertEqual(rows[0]["slip_days"], 41)
		self.assertEqual(rows[0]["overdue"], "Yes")  # T2 vencida al corte
		self.assertEqual(rows[1]["overdue"], "")  # T1 no vencida (aunque tenga slip)
		self.assertEqual(rows[1]["current_exp_end_date"], "2026-05-10")
		self.assertEqual(rows[1]["pmo_deadline"], "2026-05-05")

	def test_summary_cards(self):
		cards = {c["label"]: c for c in _summary(_REPORT)}
		self.assertEqual(cards["Current forecast (plan): end"]["value"], "2026-07-11")
		self.assertEqual(cards["Slip vs Baseline (days)"]["value"], 11)
		self.assertEqual(cards["Slip vs Baseline (days)"]["indicator"], "Red")
		self.assertEqual(cards["Slip vs commitment (days)"]["value"], 21)
		self.assertEqual(cards["Slip vs commitment (days)"]["indicator"], "Red")
		self.assertEqual(cards["Tasks: forecast exceeds commitment"]["value"], 2)
		self.assertEqual(cards["Tasks: forecast exceeds commitment"]["indicator"], "Orange")
		self.assertEqual(cards["Overdue unfinished tasks"]["value"], 1)
		self.assertEqual(cards["Actual hours to date"]["value"], 40.0)
		self.assertEqual(cards["Completed / due to date"]["value"], "1 / 2")
		self.assertEqual(cards["Effective baseline"]["value"], "PMO-BL-X")

	def test_summary_no_baseline_and_no_committed(self):
		report = dict(_REPORT)
		report["baseline"] = None
		report["indicators"] = dict(
			_REPORT["indicators"], final_date_slip_days=None, slip_vs_committed_days=None
		)
		cards = {c["label"]: c for c in _summary(report)}
		self.assertEqual(cards["Effective baseline"]["indicator"], "Gray")
		self.assertEqual(cards["Slip vs Baseline (days)"]["value"], "N/A")
		self.assertEqual(cards["Slip vs commitment (days)"]["value"], "N/A")
		self.assertEqual(cards["Slip vs commitment (days)"]["indicator"], "Green")
