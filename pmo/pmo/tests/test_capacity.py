# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Capacity Paso 4 - capacidad = jornada neta (HRMS Shift) + fallback PMO Settings. Datos ficticios.

HRMS es **dependencia requerida** de pmo (instalado en el site de tests). Se prueban (a) la fórmula neta
**pura**, (b) el **fallback** a `PMO Settings.default_capacity_hours_per_day` para Employees sin turno
resoluble (origin default/missing) y (c) el **path real de Shift** (Shift Type + default_shift). **No** se
usa `PMO Capacity` (deprecado)."""

import datetime
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.capacity import (
	get_capacity,
	get_capacity_detail,
	get_employee_daily_capacity,
	net_shift_hours,
)

EMP1 = "EMP-CAP-0001"


def _set_default(hours):
	frappe.db.set_single_value("PMO Settings", "default_capacity_hours_per_day", hours)


class TestNetShiftHours(unittest.TestCase):
	"""Fórmula pura de jornada neta (sin DocType ni HRMS)."""

	def test_normal_shift_no_break(self):
		# 09:00-17:00 = 8h
		self.assertEqual(net_shift_hours(datetime.timedelta(hours=9), datetime.timedelta(hours=17), 0), 8.0)

	def test_shift_with_break(self):
		# 09:00-18:00 (9h) - 60 min de descanso = 8h
		self.assertEqual(net_shift_hours(datetime.timedelta(hours=9), datetime.timedelta(hours=18), 60), 8.0)

	def test_shift_crossing_midnight(self):
		# 22:00-06:00 = 8h (cruza medianoche)
		self.assertEqual(net_shift_hours(datetime.timedelta(hours=22), datetime.timedelta(hours=6), 0), 8.0)

	def test_break_greater_than_span_clamps_zero(self):
		# 09:00-10:00 (1h) - 120 min = 0 (nunca negativo)
		self.assertEqual(net_shift_hours(datetime.timedelta(hours=9), datetime.timedelta(hours=10), 120), 0.0)

	def test_accepts_time_and_str(self):
		self.assertEqual(net_shift_hours(datetime.time(9, 0), datetime.time(17, 30), 30), 8.0)
		self.assertEqual(net_shift_hours("09:00:00", "17:00:00", 0), 8.0)


class TestCapacityFallback(IntegrationTestCase):
	"""Employee sin turno resoluble (empleado ficticio, sin Shift): capacidad = default de PMO Settings."""

	def setUp(self):
		_set_default(0)

	def tearDown(self):
		_set_default(0)

	def test_no_shift_uses_settings_default(self):
		_set_default(8.0)
		cap = get_employee_daily_capacity(EMP1, "2026-06-15")
		self.assertEqual(cap["hours"], 8.0)
		self.assertEqual(cap["origin"], "default")
		self.assertTrue(cap["missing_shift"])
		self.assertIsNone(cap["shift_type"])
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 8.0)

	def test_no_shift_no_default_is_missing(self):
		_set_default(0)
		cap = get_employee_daily_capacity(EMP1, "2026-06-15")
		self.assertIsNone(cap["hours"])
		self.assertEqual(cap["origin"], "missing")
		self.assertTrue(cap["missing_shift"])
		self.assertIsNone(get_capacity(EMP1, "2026-06-15"))

	def test_detail_none_when_missing_and_throw(self):
		_set_default(0)
		self.assertIsNone(get_capacity_detail(EMP1, "2026-06-15"))
		with self.assertRaises(frappe.ValidationError):
			get_capacity(EMP1, "2026-06-15", throw=True)

	def test_detail_carries_origin_and_missing_shift(self):
		_set_default(6.0)
		d = get_capacity_detail(EMP1, "2026-06-15")
		self.assertEqual(d["hours"], 6.0)
		self.assertEqual(d["origin"], "default")
		self.assertTrue(d["missing_shift"])
		self.assertIsNone(d["from_date"])

	# --- Patch de inicialización del default (sitios existentes) ------------

	def test_patch_initializes_default_when_unset(self):
		from pmo.patches.v0_0_1.init_default_capacity_hours import execute

		_set_default(0)
		execute()
		self.assertEqual(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"), 8)

	def test_patch_does_not_overwrite_configured(self):
		from pmo.patches.v0_0_1.init_default_capacity_hours import execute

		_set_default(6)
		execute()
		self.assertEqual(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"), 6)


class TestCapacityShiftPath(IntegrationTestCase):
	"""Path real de Shift (jornada neta desde HRMS). HRMS es dependencia requerida: corre siempre."""

	def setUp(self):
		_set_default(0)

	def tearDown(self):
		_set_default(0)

	def _shift_type(self, name, start, end, brk=0):
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"name": name,
					"start_time": start,
					"end_time": end,
					"pmo_unpaid_break_minutes": brk,
				}
			).insert(ignore_permissions=True)
		return name

	def _employee(self, display):
		return frappe.db.exists("Employee", {"employee_name": display}) or (
			frappe.get_doc({"doctype": "Employee", "first_name": display, "status": "Active"})
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)

	def test_shift_net_capacity_from_default_shift(self):
		# Shift 09:00-18:00 con 60 min de descanso → 8h netas; asignado como default_shift del Employee.
		st = self._shift_type("PMO-CAP-SHIFT-0900-1800", "09:00:00", "18:00:00", 60)
		emp = self._employee("PMO Cap Shift Emp")
		frappe.db.set_value("Employee", emp, "default_shift", st)
		cap = get_employee_daily_capacity(emp, "2026-06-15")
		self.assertEqual(cap["origin"], "shift")
		self.assertFalse(cap["missing_shift"])
		self.assertEqual(cap["shift_type"], st)
		self.assertEqual(cap["hours"], 8.0)

	def test_midnight_shift_via_default_shift(self):
		# Shift 22:00-06:00 (cruza medianoche) sin descanso → 8h netas.
		st = self._shift_type("PMO-CAP-SHIFT-2200-0600", "22:00:00", "06:00:00", 0)
		emp = self._employee("PMO Cap Midnight Emp")
		frappe.db.set_value("Employee", emp, "default_shift", st)
		cap = get_employee_daily_capacity(emp, "2026-06-15")
		self.assertEqual(cap["origin"], "shift")
		self.assertEqual(cap["hours"], 8.0)

	def test_shift_via_dated_shift_assignment(self):
		# Shift Assignment datado (submitted/Active) tiene prioridad sobre el default_shift del Employee.
		st = self._shift_type("PMO-CAP-SHIFT-0800-1600", "08:00:00", "16:00:00", 0)  # 8h, sin descanso
		emp = self._employee("PMO Cap Assign Emp")
		if not frappe.get_all(
			"Shift Assignment", filters={"employee": emp, "shift_type": st, "docstatus": 1}, limit=1
		):
			sa = frappe.get_doc(
				{
					"doctype": "Shift Assignment",
					"employee": emp,
					"shift_type": st,
					"status": "Active",
					"start_date": "2026-06-01",
					"end_date": "2026-06-30",
				}
			)
			sa.insert(ignore_permissions=True, ignore_mandatory=True)
			sa.submit()
		cap = get_employee_daily_capacity(emp, "2026-06-15")
		self.assertEqual(cap["origin"], "shift")
		self.assertEqual(cap["shift_type"], st)
		self.assertEqual(cap["hours"], 8.0)
