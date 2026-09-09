# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Status Report (ADR-0006, bloque 3). Capa de presentación (pura): dado el resultado de
`build_status_report`, se validan columnas, filas de detalle (tareas vencidas) y tarjetas de resumen D5.
La validación integrada real (con Project/Baseline/Timesheet en un site con Company) es un E2E aparte."""

import unittest

from pmo.pmo.report.pmo_status_report.pmo_status_report import _columns, _rows, _summary

_REPORT = {
	"project": "PROJ-X",
	"status_date": "2026-03-31",
	"baseline": {"name": "PMO-BL-X", "expected_end_date": "2026-06-30"},
	"current": {"expected_end_date": "2026-07-11"},
	"note": None,
	"indicators": {
		"final_date_slip_days": 11,
		"tasks_overdue_at_cutoff": {
			"count": 1,
			"tasks": [{"name": "T2", "subject": "T2 subj", "baseline_exp_end_date": "2026-03-20"}],
		},
		"actual_hours_to_date": 40.0,
		"counts": {"baseline_due_by_cutoff": 2, "completed_by_cutoff": 1},
	},
}


class TestStatusReportPresentation(unittest.TestCase):
	def test_columns(self):
		cols = _columns()
		self.assertEqual([c["fieldname"] for c in cols], ["name", "subject", "baseline_exp_end_date"])
		name_col = cols[0]
		self.assertEqual(name_col["fieldtype"], "Link")
		self.assertEqual(name_col["options"], "Task")

	def test_rows_are_overdue_tasks(self):
		rows = _rows(_REPORT)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["name"], "T2")
		self.assertEqual(rows[0]["baseline_exp_end_date"], "2026-03-20")

	def test_summary_cards(self):
		cards = {c["label"]: c for c in _summary(_REPORT)}
		self.assertEqual(cards["Deslizamiento fecha final (días)"]["value"], 11)
		self.assertEqual(cards["Deslizamiento fecha final (días)"]["indicator"], "Red")
		self.assertEqual(cards["Tareas vencidas no terminadas"]["value"], 1)
		self.assertEqual(cards["Tareas vencidas no terminadas"]["indicator"], "Orange")
		self.assertEqual(cards["Horas reales a la fecha"]["value"], 40.0)
		self.assertEqual(cards["Completadas / previstas a la fecha"]["value"], "1 / 2")
		self.assertEqual(cards["Línea base vigente"]["value"], "PMO-BL-X")

	def test_summary_no_baseline(self):
		report = dict(_REPORT)
		report["baseline"] = None
		report["indicators"] = dict(_REPORT["indicators"], final_date_slip_days=None)
		cards = {c["label"]: c for c in _summary(report)}
		self.assertEqual(cards["Línea base vigente"]["indicator"], "Gray")
		self.assertEqual(cards["Deslizamiento fecha final (días)"]["value"], "N/D")
