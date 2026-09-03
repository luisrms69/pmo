# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 Incremento 4 — Actual (derivado de Timesheet). Datos ficticios.

Verifica que Actual coincide con la semántica oficial de daily_timesheet_summary: suma Timesheet
Detail.hours de Timesheets Submitted (docstatus=1), con los bornes from_time/to_time; Draft/Cancelled
no cuentan; filtro por project; rango por día; y que una línea que cruza medianoche queda fuera del día
(igual que el reporte oficial).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.actual import get_actual, get_actual_range


def _employee():
	existing = frappe.db.exists("Employee", {"employee_name": "PMO Actual Emp"})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "PMO Actual Emp",
				"status": "Active",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _project(name):
	existing = frappe.db.exists("Project", {"project_name": name})
	if existing:
		return existing
	return (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _activity_type():
	if not frappe.db.exists("Activity Type", "PMO-ACT"):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": "PMO-ACT"}).insert(
			ignore_permissions=True
		)
	return "PMO-ACT"


def _timesheet(employee, logs, submit=True):
	"""Crea un Timesheet con sus líneas. `submit=True` lo marca Submitted a nivel BD (docstatus=1).

	Se marca docstatus por BD en vez de `ts.submit()` porque el `on_submit` nativo recalcula y guarda
	el Project (requiere Company/almacenes de stock, no configurables en este site mínimo). Actual solo
	consume `Timesheet.docstatus = 1`, así que este atajo de andamiaje reproduce el estado oficial sin
	el acoplamiento del submit. No altera la semántica que valida el test.
	"""
	act = _activity_type()
	for log in logs:
		log.setdefault("activity_type", act)
	ts = frappe.get_doc({"doctype": "Timesheet", "employee": employee, "time_logs": logs})
	ts.insert(ignore_permissions=True, ignore_mandatory=True)
	if submit:
		frappe.db.set_value("Timesheet", ts.name, "docstatus", 1)
	return ts.name


class TestActual(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")
		self.emp = _employee()
		self.projA = _project("PMO-ACTUAL-A")
		self.projB = _project("PMO-ACTUAL-B")

	def test_sums_submitted_hours_of_the_day(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 13:00:00",
					"hours": 4,
					"project": self.projA,
				},
				{
					"from_time": "2026-01-05 13:00:00",
					"to_time": "2026-01-05 16:00:00",
					"hours": 3,
					"project": self.projA,
				},
			],
		)
		self.assertEqual(get_actual(self.emp, "2026-01-05"), 7.0)

	def test_draft_not_counted(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 14:00:00",
					"hours": 5,
					"project": self.projA,
				}
			],
			submit=False,
		)
		self.assertEqual(get_actual(self.emp, "2026-01-05"), 0.0)

	def test_project_filter(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 13:00:00",
					"hours": 4,
					"project": self.projA,
				},
				{
					"from_time": "2026-01-05 13:00:00",
					"to_time": "2026-01-05 15:00:00",
					"hours": 2,
					"project": self.projB,
				},
			],
		)
		self.assertEqual(get_actual(self.emp, "2026-01-05", project=self.projA), 4.0)
		self.assertEqual(get_actual(self.emp, "2026-01-05", project=self.projB), 2.0)
		self.assertEqual(get_actual(self.emp, "2026-01-05"), 6.0)

	def test_range_per_day(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 13:00:00",
					"hours": 4,
					"project": self.projA,
				},
				{
					"from_time": "2026-01-07 09:00:00",
					"to_time": "2026-01-07 12:00:00",
					"hours": 3,
					"project": self.projA,
				},
			],
		)
		result = get_actual_range(self.emp, "2026-01-05", "2026-01-07")
		self.assertEqual(result[frappe.utils.getdate("2026-01-05")], 4.0)
		self.assertEqual(result[frappe.utils.getdate("2026-01-06")], 0.0)
		self.assertEqual(result[frappe.utils.getdate("2026-01-07")], 3.0)

	def test_midnight_crossing_excluded_like_official(self):
		# línea 05 22:00 → 06 02:00: fuera de ambos días individuales (mismos bornes que el reporte)
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-01-05 22:00:00",
					"to_time": "2026-01-06 02:00:00",
					"hours": 4,
					"project": self.projA,
				}
			],
		)
		self.assertEqual(get_actual(self.emp, "2026-01-05"), 0.0)
		self.assertEqual(get_actual(self.emp, "2026-01-06"), 0.0)

	def test_range_invalid_raises(self):
		with self.assertRaises(frappe.ValidationError):
			get_actual_range(self.emp, "2026-01-07", "2026-01-05")
