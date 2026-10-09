# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Resource Capacity (cobertura de jornada, Capacity Paso 4).

Reutiliza `pmo.capacity.get_employee_daily_capacity`. El site de tests no tiene HRMS → el origen es
`default`/`missing` y `missing_shift` siempre True (sirve para validar el resaltado rojo y los contadores).
Presentación pura (`_origin_label`/`_summary`) + alcance por observador (normal → su Employee)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.pmo.report.pmo_resource_capacity.pmo_resource_capacity import (
	_origin_label,
	_summary,
	execute,
)


def _set_default(hours):
	frappe.db.set_single_value("PMO Settings", "default_capacity_hours_per_day", hours)


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


def _employee(name, user_id=None):
	emp = frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "first_name": name, "status": "Active"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	if user_id:
		frappe.db.set_value("Employee", emp, "user_id", user_id)
	return emp


class TestResourceCapacityPure(unittest.TestCase):
	def test_origin_label(self):
		self.assertEqual(_origin_label("shift"), "Shift")
		self.assertEqual(_origin_label("default"), "Default")
		self.assertEqual(_origin_label("missing"), "Missing")

	def test_summary_counts(self):
		data = [
			{"capacity_hours_per_day": 8.0, "missing_shift": 0},  # Shift ok
			{"capacity_hours_per_day": 8.0, "missing_shift": 1},  # sin turno, con default
			{"capacity_hours_per_day": None, "missing_shift": 1},  # sin turno, sin capacidad
		]
		cards = {c["label"]: c for c in _summary(data)}
		self.assertEqual(cards["Resources"]["value"], 3)
		self.assertEqual(cards["Without assigned shift"]["value"], 2)
		self.assertEqual(cards["Without assigned shift"]["indicator"], "Red")
		self.assertEqual(cards["Without resolvable capacity"]["value"], 1)
		self.assertEqual(cards["Without resolvable capacity"]["indicator"], "Red")


class TestResourceCapacityExecute(IntegrationTestCase):
	def setUp(self):
		_set_default(0)

	def tearDown(self):
		_set_default(0)

	def _row(self, data, emp):
		return next(r for r in data if r["employee"] == emp)

	def test_default_origin_marks_missing_shift(self):
		emp = _employee("RC Default Emp")
		_set_default(8.0)
		frappe.set_user("Administrator")
		_cols, data, _m, _c, summary = execute({"as_of": "2026-06-15", "employee": emp})
		row = self._row(data, emp)
		self.assertEqual(row["capacity_hours_per_day"], 8.0)
		self.assertEqual(row["origin_key"], "default")
		self.assertTrue(row["missing_shift"])  # sin turno → rojo (aunque haya default)
		self.assertIn("default", row["status"].lower())
		miss = next(s for s in summary if s["label"] == "Without assigned shift")
		self.assertGreaterEqual(miss["value"], 1)

	def test_missing_capacity_when_no_default(self):
		emp = _employee("RC Missing Emp")
		_set_default(0)
		frappe.set_user("Administrator")
		_cols, data, _m, _c, _s = execute({"as_of": "2026-06-15", "employee": emp})
		row = self._row(data, emp)
		self.assertIsNone(row["capacity_hours_per_day"])
		self.assertEqual(row["origin_key"], "missing")
		self.assertTrue(row["missing_shift"])

	def test_normal_tier_sees_only_own(self):
		u = _user("rc-normal@example.com")
		own = _employee("RC Normal Own", user_id=u)
		_employee("RC Normal Other")  # otro empleado que NO debe ver
		frappe.set_user(u)
		try:
			_cols, data, _m, _c, _s = execute({"as_of": "2026-06-15"})
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(all(r["employee"] == own for r in data))
