# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Planned vs Actual (ADR-0008, bloque 1).

- Puros (`TestPlannedVsActual`): `_rows`/`_pct`/`_columns` — Planned=`expected_time`, Actual nativo o map
  as-of, Variance, % Consumed, exclusión de `is_group`. Sin DB.
- Integración (`TestPlannedVsActualAsOf`): corte as-of por Timesheet — incluye horas del propio
  `status_date`, excluye el día siguiente, solo submitted.
- Integración (`TestPlannedVsActualReport`): `execute()` end-to-end + P4 (bloquea a no-miembros)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.actual import get_actual_hours_asof, get_actual_hours_by_task_asof
from pmo.pmo.report.pmo_planned_vs_actual.pmo_planned_vs_actual import (
	_columns,
	_pct,
	_rows,
	execute,
)


def _t(name, expected_time, actual_time=0, is_group=0, subject=None):
	return {
		"name": name,
		"subject": subject or name,
		"expected_time": expected_time,
		"actual_time": actual_time,
		"is_group": is_group,
	}


class TestPlannedVsActual(unittest.TestCase):
	def test_pct_consumed(self):
		self.assertEqual(_pct(8, 10), 80.0)
		self.assertEqual(_pct(15, 10), 150.0)
		self.assertIsNone(_pct(5, 0))  # sin plan → None (no divide por 0)

	def test_columns(self):
		cols = _columns()
		self.assertEqual(
			[c["fieldname"] for c in cols],
			["task", "subject", "planned_hours", "actual_hours", "variance_hours", "pct_consumed"],
		)
		self.assertEqual(cols[0]["fieldtype"], "Link")
		self.assertEqual(cols[0]["options"], "Task")

	def test_rows_native_actual_excludes_group(self):
		# G1 (grupo) se excluye; T1 y T2 hoja usan actual_time nativo.
		tasks = [_t("G1", 100, 0, is_group=1), _t("T1", 10, 8), _t("T2", 5, 6)]
		data, planned, actual = _rows(tasks, None)
		self.assertEqual([r["task"] for r in data], ["T1", "T2"])  # grupo excluido
		self.assertEqual(planned, 15.0)
		self.assertEqual(actual, 14.0)
		self.assertEqual(data[0]["variance_hours"], -2.0)  # 8 - 10
		self.assertEqual(data[0]["pct_consumed"], 80.0)
		self.assertEqual(data[1]["variance_hours"], 1.0)  # 6 - 5

	def test_rows_asof_map_overrides_actual_time(self):
		# Con map as-of, se ignora actual_time nativo; tarea sin entrada en el map → 0.
		tasks = [_t("T1", 10, 999), _t("T2", 4, 999)]
		actual_by_task = {"T1": 3}
		data, planned, actual = _rows(tasks, actual_by_task)
		self.assertEqual(planned, 14.0)
		self.assertEqual(actual, 3.0)  # T1=3, T2 ausente=0
		self.assertEqual(data[0]["actual_hours"], 3.0)
		self.assertEqual(data[1]["actual_hours"], 0.0)

	def test_rows_no_plan_variance_and_pct(self):
		tasks = [_t("T1", 0, 4)]  # sin plan, con actual
		data, planned, actual = _rows(tasks, None)
		self.assertEqual(planned, 0.0)
		self.assertEqual(actual, 4.0)
		self.assertEqual(data[0]["variance_hours"], 4.0)
		self.assertIsNone(data[0]["pct_consumed"])


# --- Scaffolding de integración (reusa el patrón de test_actual.py) -------------------


def _employee():
	existing = frappe.db.exists("Employee", {"employee_name": "PMO PvA Emp"})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "PMO PvA Emp",
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


def _task(subject, project):
	existing = frappe.db.exists("Task", {"subject": subject, "project": project})
	if existing:
		return existing
	return (
		frappe.get_doc({"doctype": "Task", "subject": subject, "project": project})
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
	"""Timesheet con líneas; docstatus=1 por BD (mismo atajo que test_actual: Actual solo lee docstatus=1)."""
	act = _activity_type()
	for log in logs:
		log.setdefault("activity_type", act)
	ts = frappe.get_doc({"doctype": "Timesheet", "employee": employee, "time_logs": logs})
	ts.insert(ignore_permissions=True, ignore_mandatory=True)
	if submit:
		frappe.db.set_value("Timesheet", ts.name, "docstatus", 1)
	return ts.name


class TestPlannedVsActualAsOf(IntegrationTestCase):
	"""Corte as-of (ADR-0008/0006): incluye horas registradas DURANTE el propio `status_date`; excluye
	las del día siguiente; solo cuenta Timesheets submitted."""

	def setUp(self):
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")
		self.emp = _employee()
		self.proj = _project("PMO-PVA-ASOF")
		self.t1 = _task("PVA Task 1", self.proj)
		self.t2 = _task("PVA Task 2", self.proj)

	def test_asof_includes_same_day_hours(self):
		# status_date = 2026-09-09. Tres líneas ese mismo día (inicio, media mañana, casi medianoche)
		# + una del día siguiente que NO debe contar.
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-09-09 00:00:00",
					"to_time": "2026-09-09 02:00:00",
					"hours": 2,
					"project": self.proj,
					"task": self.t1,
				},
				{
					"from_time": "2026-09-09 09:30:00",
					"to_time": "2026-09-09 12:30:00",
					"hours": 3,
					"project": self.proj,
					"task": self.t1,
				},
				{
					"from_time": "2026-09-09 22:00:00",
					"to_time": "2026-09-09 23:00:00",
					"hours": 1,
					"project": self.proj,
					"task": self.t2,
				},
				{
					"from_time": "2026-09-10 08:00:00",
					"to_time": "2026-09-10 10:00:00",
					"hours": 2,
					"project": self.proj,
					"task": self.t2,
				},
			],
		)
		# Total as-of 2026-09-09: 2 + 3 + 1 = 6 (la línea del 09-10 queda fuera).
		self.assertEqual(get_actual_hours_asof(self.proj, "2026-09-09"), 6.0)
		by_task = get_actual_hours_by_task_asof(self.proj, "2026-09-09")
		self.assertEqual(by_task.get(self.t1), 5.0)  # 2 + 3, ambas del propio día
		self.assertEqual(by_task.get(self.t2), 1.0)  # solo la de 23:00; excluye 09-10

	def test_asof_next_day_includes_all(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-09-09 09:00:00",
					"to_time": "2026-09-09 13:00:00",
					"hours": 4,
					"project": self.proj,
					"task": self.t1,
				},
				{
					"from_time": "2026-09-10 08:00:00",
					"to_time": "2026-09-10 10:00:00",
					"hours": 2,
					"project": self.proj,
					"task": self.t1,
				},
			],
		)
		self.assertEqual(get_actual_hours_asof(self.proj, "2026-09-09"), 4.0)
		self.assertEqual(get_actual_hours_asof(self.proj, "2026-09-10"), 6.0)

	def test_asof_draft_not_counted(self):
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-09-09 09:00:00",
					"to_time": "2026-09-09 14:00:00",
					"hours": 5,
					"project": self.proj,
					"task": self.t1,
				}
			],
			submit=False,
		)
		self.assertEqual(get_actual_hours_asof(self.proj, "2026-09-09"), 0.0)
		self.assertEqual(get_actual_hours_by_task_asof(self.proj, "2026-09-09"), {})


class TestPlannedVsActualReport(IntegrationTestCase):
	"""`execute()` end-to-end: Project/Task/Timesheet, rollup que excluye `is_group`, indicadores as-of, y
	P4 (Script Report impone permisos en execute)."""

	def setUp(self):
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")
		frappe.set_user("Administrator")
		self.emp = _employee()
		self.proj = _project("PMO-PVA-REPORT")
		# grupo con plan alto: debe quedar FUERA del rollup (envelope)
		self.grp = (
			frappe.get_doc(
				{
					"doctype": "Task",
					"subject": "PVA Group",
					"project": self.proj,
					"is_group": 1,
					"expected_time": 100,
				}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
		self.t1 = (
			frappe.get_doc(
				{"doctype": "Task", "subject": "PVA Leaf 1", "project": self.proj, "expected_time": 10}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
		self.t2 = (
			frappe.get_doc(
				{"doctype": "Task", "subject": "PVA Leaf 2", "project": self.proj, "expected_time": 4}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
		_timesheet(
			self.emp,
			[
				{
					"from_time": "2026-09-09 09:00:00",
					"to_time": "2026-09-09 15:00:00",  # 6h el día del corte
					"hours": 6,
					"project": self.proj,
					"task": self.t1,
				},
				{
					"from_time": "2026-09-10 09:00:00",
					"to_time": "2026-09-10 11:00:00",  # 2h día siguiente (fuera del corte)
					"hours": 2,
					"project": self.proj,
					"task": self.t1,
				},
			],
		)

	def test_execute_asof_excludes_group_and_indicators(self):
		cols, data, _msg, _chart, summary = execute({"project": self.proj, "status_date": "2026-09-09"})
		self.assertEqual([c["fieldname"] for c in cols][:2], ["task", "subject"])
		rows = {r["task"]: r for r in data}
		self.assertNotIn(self.grp, rows)  # grupo excluido del rollup
		self.assertEqual(set(rows), {self.t1, self.t2})
		self.assertEqual(rows[self.t1]["planned_hours"], 10.0)
		self.assertEqual(rows[self.t1]["actual_hours"], 6.0)  # solo el 09-09, no el 09-10
		self.assertEqual(rows[self.t1]["variance_hours"], -4.0)
		self.assertEqual(rows[self.t1]["pct_consumed"], 60.0)
		self.assertEqual(rows[self.t2]["planned_hours"], 4.0)
		self.assertEqual(rows[self.t2]["actual_hours"], 0.0)
		self.assertEqual(rows[self.t2]["pct_consumed"], 0.0)
		self.assertTrue(summary)  # report_summary con cards

	def test_execute_requires_project(self):
		with self.assertRaises(frappe.ValidationError):
			execute({})

	def test_execute_p4_blocks_non_member(self):
		ghost = "pva-ghost@example.com"
		if not frappe.db.exists("User", ghost):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": ghost,
					"first_name": "PVA Ghost",
					"roles": [{"role": "Projects User"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(ghost)
		try:
			with self.assertRaises(frappe.PermissionError):
				execute({"project": self.proj, "status_date": "2026-09-09"})
		finally:
			frappe.set_user("Administrator")
