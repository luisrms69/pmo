# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 — Planned Load derivado de Task + Assignment. Datos ficticios.

Cubre: reparto de horas por asignado (D3: 1/N/overrides/Σ), estados de Task incluidos/excluidos,
mapeo User↔Employee (unmapped, ambiguo, sin user_id), Tasks sin expected_time / sin fechas / fechas
inválidas, distribución diaria respetando Holiday List, y retornos ESTRUCTURADOS (hours/issues/
unscheduled/unmapped) que nunca ocultan esfuerzo excluido.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from pmo.planned_load import get_planned_hours_per_assignee, get_planned_load, get_planned_load_range

HL = "PMO-HL-TEST"


def _hl():
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


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	return email


def _employee(name, user_id=None, with_hl=True):
	existing = frappe.db.exists("Employee", {"employee_name": name})
	emp = existing or (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": name,
				"status": "Active",
				"holiday_list": _hl() if with_hl else None,
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	# user_id por set_value: crearlo en el insert dispara validación de user-permission que toca Company.
	if user_id:
		frappe.db.set_value("Employee", emp, "user_id", user_id)
	return emp


def _task(subject, expected_time, start=None, end=None, status="Open"):
	t = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"expected_time": expected_time,
			"exp_start_date": start,
			"exp_end_date": end,
			"status": status,
		}
	)
	t.insert(ignore_permissions=True, ignore_mandatory=True)
	return t.name


def _assign(task, user, hours=None):
	todo = {
		"doctype": "ToDo",
		"allocated_to": user,
		"reference_type": "Task",
		"reference_name": task,
		"status": "Open",
		"description": f"Asignación {task}",
	}
	if hours is not None:
		todo["pmo_planned_hours"] = hours
	frappe.get_doc(todo).insert(ignore_permissions=True)


class TestPlannedLoad(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_hl()
		cls.u1 = _user("pl-u1@example.com")
		cls.u2 = _user("pl-u2@example.com")
		cls.u_noemp = _user("pl-noemp@example.com")
		cls.emp1 = _employee("PL Emp1", user_id=cls.u1)
		cls.emp2 = _employee("PL Emp2", user_id=cls.u2)
		cls.emp_nouser = _employee("PL NoUser", user_id=None)

	def setUp(self):
		frappe.db.delete("ToDo", {"reference_type": "Task"})  # aislamiento de asignaciones

	# --- get_planned_hours_per_assignee (D3) --------------------------------

	def test_one_assignee_gets_expected_time(self):
		t = _task("PL-one", 8)
		_assign(t, self.u1)
		res = get_planned_hours_per_assignee(t)
		self.assertTrue(res["consistent"])
		self.assertEqual(res["per_assignee"], {self.u1: 8.0})

	def test_n_assignees_even_split(self):
		t = _task("PL-even", 10)
		_assign(t, self.u1)
		_assign(t, self.u2)
		res = get_planned_hours_per_assignee(t)
		self.assertEqual(res["per_assignee"], {self.u1: 5.0, self.u2: 5.0})

	def test_partial_override_distributes_remainder(self):
		t = _task("PL-partial", 10)
		_assign(t, self.u1, hours=6)
		_assign(t, self.u2)  # sin override → remanente 4
		res = get_planned_hours_per_assignee(t)
		self.assertEqual(res["per_assignee"], {self.u1: 6.0, self.u2: 4.0})

	def test_overrides_exceed_expected_is_inconsistent(self):
		t = _task("PL-exceed", 10)
		_assign(t, self.u1, hours=12)
		res = get_planned_hours_per_assignee(t)
		self.assertFalse(res["consistent"])
		self.assertIn("overrides_exceed_expected", res["issues"])
		self.assertEqual(res["per_assignee"], {})

	def test_all_overrides_sum_equals_expected(self):
		t = _task("PL-allok", 10)
		_assign(t, self.u1, hours=6)
		_assign(t, self.u2, hours=4)
		res = get_planned_hours_per_assignee(t)
		self.assertTrue(res["consistent"])
		self.assertEqual(res["per_assignee"], {self.u1: 6.0, self.u2: 4.0})

	def test_all_overrides_mismatch_is_inconsistent(self):
		t = _task("PL-mismatch", 10)
		_assign(t, self.u1, hours=6)
		_assign(t, self.u2, hours=2)  # Σ=8 ≠ 10
		res = get_planned_hours_per_assignee(t)
		self.assertFalse(res["consistent"])
		self.assertIn("all_overrides_mismatch", res["issues"])

	def test_no_expected_time_is_reported(self):
		t = _task("PL-noeffort", 0)
		_assign(t, self.u1)
		res = get_planned_hours_per_assignee(t)
		self.assertFalse(res["consistent"])
		self.assertIn("no_expected_time", res["issues"])

	def test_unmapped_assignee_without_employee(self):
		t = _task("PL-unmapped", 8)
		_assign(t, self.u_noemp)
		res = get_planned_hours_per_assignee(t)
		self.assertIn(self.u_noemp, res["unmapped"])

	# --- get_planned_load ---------------------------------------------------

	def test_load_distributes_on_single_day(self):
		t = _task("PL-day", 8, start="2026-01-05", end="2026-01-05")
		_assign(t, self.u1)
		res = get_planned_load(self.emp1, "2026-01-05")
		self.assertEqual(res["hours"], 8.0)
		self.assertEqual(res["issues"], [])

	def test_task_without_dates_is_unscheduled(self):
		t = _task("PL-nodate", 8)
		_assign(t, self.u1)
		res = get_planned_load(self.emp1, "2026-01-05")
		self.assertEqual(res["hours"], 0.0)
		self.assertEqual(len(res["unscheduled"]), 1)
		self.assertEqual(res["unscheduled"][0]["task"], t)

	def test_invalid_dates_reported_as_issue(self):
		# Task valida nativamente end > start; forzamos el estado inválido (datos corruptos) por
		# set_value para ejercer la defensa de planned_load.
		t = _task("PL-baddate", 8, start="2026-01-05", end="2026-01-09")
		frappe.db.set_value("Task", t, "exp_end_date", "2026-01-04 00:00:00")  # end < start
		_assign(t, self.u1)
		res = get_planned_load(self.emp1, "2026-01-05")
		self.assertEqual(res["hours"], 0.0)
		self.assertTrue(any("invalid_dates" in i["reasons"] for i in res["issues"]))

	def test_employee_without_user_id_unmapped(self):
		t = _task("PL-nouser", 8, start="2026-01-05", end="2026-01-05")
		# asignar a alguien no importa: el employee consultado no tiene user_id
		_assign(t, self.u1)
		res = get_planned_load(self.emp_nouser, "2026-01-05")
		self.assertTrue(any(x["reason"] == "no_user_id" for x in res["unmapped"]))

	def test_ambiguous_user_mapping_excluded(self):
		amb_user = _user("pl-amb@example.com")
		e_a = _employee("PL Amb A", user_id=amb_user)
		_employee("PL Amb B", user_id=amb_user)  # 2 Active con el mismo user_id → ambiguo
		t = _task("PL-amb", 8, start="2026-01-05", end="2026-01-05")
		_assign(t, amb_user)
		res = get_planned_load(e_a, "2026-01-05")
		self.assertEqual(res["hours"], 0.0)
		self.assertTrue(any(x["reason"] == "ambiguous_user_mapping" for x in res["unmapped"]))

	def test_inconsistent_task_in_issues_not_hours(self):
		t = _task("PL-inc", 10, start="2026-01-05", end="2026-01-05")
		_assign(t, self.u1, hours=12)  # override > expected
		res = get_planned_load(self.emp1, "2026-01-05")
		self.assertEqual(res["hours"], 0.0)
		self.assertTrue(any(i["task"] == t for i in res["issues"]))

	def test_completed_task_excluded(self):
		t = _task("PL-done", 8, start="2026-01-05", end="2026-01-05", status="Completed")
		_assign(t, self.u1)
		res = get_planned_load(self.emp1, "2026-01-05")
		self.assertEqual(res["hours"], 0.0)
		self.assertEqual(res["issues"], [])
		self.assertEqual(res["unscheduled"], [])

	# --- get_planned_load_range ---------------------------------------------

	def test_range_distributes_over_working_days(self):
		t = _task("PL-range", 10, start="2026-01-05", end="2026-01-09")  # 06 festivo → 4 días
		_assign(t, self.u1)
		res = get_planned_load_range(self.emp1, "2026-01-05", "2026-01-09")
		self.assertEqual(len(res["days"]), 4)
		self.assertNotIn(getdate("2026-01-06"), res["days"])
		self.assertEqual(flt(sum(res["days"].values()), 2), 10.0)
