# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Resource Capacity (cobertura/mantenimiento de PMO Capacity, ADR-0003 D1).

Resolver único `get_capacity_detail` (override > global > faltante) + presentación pura (_summary /
_origin_label) + alcance por observador (normal → su Employee)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.capacity import get_capacity, get_capacity_detail
from pmo.pmo.report.pmo_resource_capacity.pmo_resource_capacity import (
	_origin_label,
	_summary,
	execute,
)


def _cap(hours, from_date, employee=None):
	doc = {"doctype": "PMO Capacity", "from_date": from_date, "capacity_hours_per_day": hours}
	if employee:
		doc["employee"] = employee
	frappe.get_doc(doc).insert(ignore_permissions=True, ignore_links=True)


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
		self.assertEqual(_origin_label(None), "Faltante")
		self.assertEqual(_origin_label({"origin": "override"}), "Override")
		self.assertEqual(_origin_label({"origin": "global"}), "Global")

	def test_summary_counts(self):
		data = [
			{"capacity_hours_per_day": None, "origin": "Faltante"},
			{"capacity_hours_per_day": 8.0, "origin": "Override"},
			{"capacity_hours_per_day": 8.0, "origin": "Global"},
		]
		cards = {c["label"]: c for c in _summary(data)}
		self.assertEqual(cards["Recursos"]["value"], 3)
		self.assertEqual(cards["Sin capacidad configurada"]["value"], 1)
		self.assertEqual(cards["Sin capacidad configurada"]["indicator"], "Orange")
		self.assertEqual(cards["Con override individual"]["value"], 1)


class TestResourceCapacityResolver(IntegrationTestCase):
	def setUp(self):
		# fechas 2027 aisladas para no chocar con capacidades globales de otros módulos de test
		frappe.db.delete("PMO Capacity", {"from_date": (">=", "2027-01-01")})

	def test_override_beats_global(self):
		emp = _employee("RC Emp Override")
		_cap(8.0, "2027-01-01")  # global
		_cap(5.0, "2027-01-01", employee=emp)  # override
		detail = get_capacity_detail(emp, "2027-06-01")
		self.assertEqual(detail["hours"], 5.0)
		self.assertEqual(detail["origin"], "override")
		self.assertEqual(str(detail["from_date"]), "2027-01-01")
		self.assertEqual(get_capacity(emp, "2027-06-01"), 5.0)  # wrapper coincide

	def test_falls_back_to_global(self):
		emp = _employee("RC Emp Global")
		_cap(7.0, "2027-02-01")  # solo global
		detail = get_capacity_detail(emp, "2027-06-01")
		self.assertEqual(detail["hours"], 7.0)
		self.assertEqual(detail["origin"], "global")

	def test_missing_returns_none(self):
		emp = _employee("RC Emp Missing")
		# sin filas 2027 para este scope → antes de cualquier from_date
		self.assertIsNone(get_capacity_detail(emp, "2027-01-01"))
		self.assertIsNone(get_capacity(emp, "2027-01-01"))

	def test_execute_reports_faltante_for_employee_without_capacity(self):
		emp = _employee("RC Emp Report")
		frappe.set_user("Administrator")
		try:
			_cols, data, _m, _c, summary = execute({"as_of": "2027-01-01", "employee": emp})
		finally:
			frappe.set_user("Administrator")
		row = next(r for r in data if r["employee"] == emp)
		self.assertIsNone(row["capacity_hours_per_day"])
		self.assertEqual(row["origin"], "Faltante")
		miss = next(s for s in summary if s["label"] == "Sin capacidad configurada")
		self.assertEqual(miss["value"], 1)

	def test_normal_tier_sees_only_own(self):
		u = _user("rc-normal@example.com")
		own = _employee("RC Normal Own", user_id=u)
		_employee("RC Normal Other")  # otro empleado que NO debe ver
		frappe.set_user(u)
		try:
			_cols, data, _m, _c, _s = execute({"as_of": "2027-01-01"})
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(all(r["employee"] == own for r in data))
