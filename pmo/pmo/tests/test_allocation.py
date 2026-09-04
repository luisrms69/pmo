# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 — lógica pura de distribución diaria (`build_allocation_days`). Datos ficticios.

Reparte horas de forma uniforme sobre los días laborables (no-Holiday) de un rango. Esta lógica se
reutiliza para distribuir el esfuerzo de una Task (expected_time por asignado) sobre sus fechas; NO
depende de ningún DocType de asignación (el plan es derivado de Task + Assignment, ver ADR-0003).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from pmo.allocation import build_allocation_days

HL = "PMO-HL-TEST"


def _holiday_list():
	if not frappe.db.exists("Holiday List", HL):
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HL,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [{"holiday_date": "2026-01-06", "description": "Festivo"}],
			}
		).insert(ignore_permissions=True)
	return HL


class TestBuildAllocationDays(IntegrationTestCase):
	def setUp(self):
		_holiday_list()

	def test_even_respects_holidays(self):
		# rango 05..09 con 06 festivo → 4 días laborables → 20/4 = 5h
		rows = build_allocation_days("2026-01-05", "2026-01-09", 20, HL)
		self.assertEqual(len(rows), 4)
		self.assertNotIn(getdate("2026-01-06"), [r["date"] for r in rows])
		self.assertTrue(all(r["hours"] == 5.0 for r in rows))
		self.assertEqual(flt(sum(r["hours"] for r in rows), 2), 20.0)

	def test_rounding_absorbed_by_last_day(self):
		# rango 05..08 con 06 festivo → 3 días → 10h → 3.33, 3.33, 3.34 (suma exacta 10)
		rows = build_allocation_days("2026-01-05", "2026-01-08", 10, HL)
		self.assertEqual(len(rows), 3)
		self.assertEqual(flt(sum(r["hours"] for r in rows), 2), 10.0)

	def test_no_working_days_raises(self):
		with self.assertRaises(frappe.ValidationError):
			build_allocation_days("2026-01-06", "2026-01-06", 8, HL)  # único día es festivo

	def test_invalid_range_raises(self):
		with self.assertRaises(frappe.ValidationError):
			build_allocation_days("2026-01-09", "2026-01-05", 8, HL)
