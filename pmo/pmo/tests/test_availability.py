# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 Incremento 3 — Availability derivada. Datos ficticios.

Cubre: Availability = Capacity en día laborable; 0 en festivo (Holiday List real); None cuando no hay
capacidad (incluso en festivo); rango por día; y la clasificación de Leave (unit, sin depender de HRMS,
que no está instalado en el site de tests).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.availability import _classify_leave, get_availability, get_availability_range

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


def _employee():
	existing = frappe.db.exists("Employee", {"employee_name": "PMO Avail Emp"})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "PMO Avail Emp",
				"holiday_list": _holiday_list(),
				"status": "Active",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _global_capacity(hours, from_date="2026-01-01"):
	frappe.get_doc(
		{"doctype": "PMO Capacity", "from_date": from_date, "capacity_hours_per_day": hours}
	).insert(ignore_permissions=True, ignore_links=True)


class TestAvailability(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("PMO Capacity")  # aislamiento
		_holiday_list()
		self.emp = _employee()

	# --- clasificación de Leave (unit, sin HRMS) ---------------------------

	def test_classify_leave_full_day(self):
		leaves = [{"half_day": 0, "half_day_date": None}]
		self.assertEqual(_classify_leave(leaves, "2026-01-05"), "full")

	def test_classify_leave_half_day_on_date(self):
		leaves = [{"half_day": 1, "half_day_date": "2026-01-05"}]
		self.assertEqual(_classify_leave(leaves, "2026-01-05"), "half")

	def test_classify_leave_half_day_other_date_is_full(self):
		# el medio día aplica a otra fecha → ese día es baja completa
		leaves = [{"half_day": 1, "half_day_date": "2026-01-07"}]
		self.assertEqual(_classify_leave(leaves, "2026-01-05"), "full")

	def test_classify_leave_none(self):
		self.assertIsNone(_classify_leave([], "2026-01-05"))

	# --- get_availability ---------------------------------------------------

	def test_availability_equals_capacity_on_working_day(self):
		_global_capacity(8.0)
		self.assertEqual(get_availability(self.emp, "2026-01-05"), 8.0)

	def test_availability_zero_on_holiday(self):
		_global_capacity(8.0)
		self.assertEqual(get_availability(self.emp, "2026-01-06"), 0.0)  # festivo

	def test_none_when_no_capacity_configured(self):
		# sin capacidad → None, aunque sea día laborable
		self.assertIsNone(get_availability(self.emp, "2026-01-05"))

	def test_none_on_holiday_when_no_capacity(self):
		# decisión 2: sin capacidad, ni siquiera el festivo la convierte en 0 → None
		self.assertIsNone(get_availability(self.emp, "2026-01-06"))

	# --- get_availability_range --------------------------------------------

	def test_range_marks_holiday_zero_and_workdays_capacity(self):
		_global_capacity(8.0)
		result = get_availability_range(self.emp, "2026-01-05", "2026-01-07")
		self.assertEqual(result[frappe.utils.getdate("2026-01-05")], 8.0)
		self.assertEqual(result[frappe.utils.getdate("2026-01-06")], 0.0)  # festivo
		self.assertEqual(result[frappe.utils.getdate("2026-01-07")], 8.0)

	def test_range_invalid_raises(self):
		with self.assertRaises(frappe.ValidationError):
			get_availability_range(self.emp, "2026-01-07", "2026-01-05")
