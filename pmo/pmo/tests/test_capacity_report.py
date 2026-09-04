# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 D6 / ADR-0002 P4 — Reporte PMO Capacity Planning. Datos ficticios.

Verifica el enmascarado P4 server-side por observador (normal/manager/executive), el split
visible/confidencial (bucket = total - Sigma visibles, sin identidad), los KPIs (libre, sobreasignación,
utilizaciones), la separación estricta Planned!=Actual y la granularidad.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.pmo.report.pmo_capacity_planning.pmo_capacity_planning import execute

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


def _user(email, roles=()):
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
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _employee(name, user_id):
	emp = frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "first_name": name, "status": "Active", "holiday_list": _hl()})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Employee", emp, "user_id", user_id)
	return emp


def _capacity_global(hours=8.0):
	if not frappe.get_all("PMO Capacity", filters={"employee": ("in", ("", None))}, limit=1):
		frappe.get_doc(
			{"doctype": "PMO Capacity", "from_date": "2026-01-01", "capacity_hours_per_day": hours}
		).insert(ignore_permissions=True, ignore_links=True)


def _project(name, owner):
	p = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", p, "owner", owner)
	return p


def _task(subject, project, expected, start, end):
	existing = frappe.db.exists("Task", {"subject": subject, "project": project})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"expected_time": expected,
				"exp_start_date": start,
				"exp_end_date": end,
				"status": "Open",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _assign(task, user):
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"reference_type": "Task",
			"reference_name": task,
			"status": "Open",
			"description": f"Asignación {task}",
		}
	).insert(ignore_permissions=True)


def _activity_type():
	if not frappe.db.exists("Activity Type", "PMO-ACT"):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": "PMO-ACT"}).insert(
			ignore_permissions=True
		)
	return "PMO-ACT"


def _timesheet(employee, project, hours):
	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": employee,
			"time_logs": [
				{
					"activity_type": _activity_type(),
					"from_time": "2026-01-05 09:00:00",
					"to_time": "2026-01-05 14:00:00",
					"hours": hours,
					"project": project,
				}
			],
		}
	)
	ts.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value("Timesheet", ts.name, "docstatus", 1)  # Submitted a nivel BD (ver test_actual)


class TestCapacityReport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_hl()
		_activity_type()
		_capacity_global(8.0)
		cls.exec_user = _user("cr-exec@example.com", ["PMO Executive Access"])
		cls.mgr_user = _user("cr-mgr@example.com", ["PMO Manager"])

	def setUp(self):
		frappe.db.delete("ToDo", {"reference_type": "Task"})
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")

	def _run(self, observer, **filters):
		return self._run_full(observer, **filters)[0]

	def _run_full(self, observer, **filters):
		"""Devuelve (data, chart, report_summary) con la sesión del observador."""
		frappe.set_user(observer)
		try:
			res = execute(filters)
		finally:
			frappe.set_user("Administrator")
		return res[1], res[3], res[4]

	def _p4_scenario(self):
		subj = _user("cr-subj@example.com")
		emp = _employee("CR Subject", subj)
		p_open = _project("CR-P-OPEN", owner=subj)  # visible al propio subj (owner)
		p_conf = _project("CR-P-CONF", owner="Administrator")  # confidencial para subj
		_assign(_task("CR-T-OPEN", p_open, 4, "2026-01-05", "2026-01-05"), subj)
		_assign(_task("CR-T-CONF", p_conf, 4, "2026-01-05", "2026-01-05"), subj)
		return subj, emp, p_open, p_conf

	def _row(self, data, emp):
		rows = [r for r in data if r["employee"] == emp]
		self.assertEqual(len(rows), 1, f"esperaba 1 fila para {emp}, hay {len(rows)}")
		return rows[0]

	# --- P4 por observador --------------------------------------------------

	def test_normal_sees_only_own_row_with_split(self):
		subj, emp, _po, _pc = self._p4_scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05")
		row = self._row(data, emp)  # también verifica que solo hay su fila
		self.assertEqual(row["planned_visible"], 4.0)
		self.assertEqual(row["confidential"], 4.0)
		self.assertEqual(row["planned_total"], 8.0)
		self.assertEqual(row["availability"], 8.0)

	def test_executive_sees_full_breakdown(self):
		_subj, emp, _po, _pc = self._p4_scenario()
		data = self._run(self.exec_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		row = self._row(data, emp)
		self.assertEqual(row["planned_visible"], 8.0)  # executive ve ambos proyectos
		self.assertEqual(row["confidential"], 0.0)

	def test_manager_quantitative_with_confidential(self):
		_subj, emp, _po, _pc = self._p4_scenario()
		data = self._run(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		row = self._row(data, emp)
		self.assertEqual(row["planned_total"], 8.0)  # cuantitativo completo
		self.assertEqual(row["planned_visible"], 0.0)  # no es owner/member -> confidencial
		self.assertEqual(row["confidential"], 8.0)

	def test_no_project_identity_leaks(self):
		_subj, _emp, _po, p_conf = self._p4_scenario()
		data = self._run(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05")
		blob = frappe.as_json(data)
		self.assertNotIn(p_conf, blob)  # el nombre real del proyecto confidencial no aparece

	def test_normal_does_not_see_other_employees(self):
		subj, emp, _po, _pc = self._p4_scenario()
		other_user = _user("cr-other@example.com")
		other_emp = _employee("CR Other", other_user)
		_assign(
			_task("CR-T-OTHER", _project("CR-P-OTHER", owner=other_user), 4, "2026-01-05", "2026-01-05"),
			other_user,
		)
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05")
		self.assertTrue(all(r["employee"] == emp for r in data))
		self.assertFalse(any(r["employee"] == other_emp for r in data))

	# --- KPIs ---------------------------------------------------------------

	def test_overallocation_and_free(self):
		over_user = _user("cr-over@example.com")
		emp = _employee("CR Over", over_user)
		_assign(
			_task("CR-T-OVER", _project("CR-P-OVER", owner=over_user), 16, "2026-01-05", "2026-01-05"),
			over_user,
		)
		data = self._run(self.exec_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		row = self._row(data, emp)
		self.assertEqual(row["planned_total"], 16.0)
		self.assertEqual(row["availability"], 8.0)
		self.assertEqual(row["free"], -8.0)
		self.assertEqual(row["overallocation"], 8.0)
		self.assertEqual(row["util_planned"], 200.0)

	def test_planned_and_actual_never_summed(self):
		_subj, emp, p_open, _pc = self._p4_scenario()
		_timesheet(emp, p_open, 5)  # 5h reales en proyecto visible
		data = self._run(self.exec_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		row = self._row(data, emp)
		self.assertEqual(row["planned_total"], 8.0)
		self.assertEqual(row["actual_total"], 5.0)  # separado, nunca 13
		self.assertEqual(row["util_planned"], 100.0)
		self.assertEqual(row["util_actual"], 62.5)

	# --- granularidad -------------------------------------------------------

	def test_week_granularity_aggregates_days(self):
		wk_user = _user("cr-week@example.com")
		emp = _employee("CR Week", wk_user)
		# 10h sobre 05..09 (06 festivo) -> 4 días laborables; misma semana ISO -> 1 bucket
		_assign(
			_task("CR-T-WEEK", _project("CR-P-WEEK", owner=wk_user), 10, "2026-01-05", "2026-01-09"), wk_user
		)
		data = self._run(
			self.exec_user, from_date="2026-01-05", to_date="2026-01-09", employee=emp, granularity="Week"
		)
		row = self._row(data, emp)
		self.assertEqual(row["planned_total"], 10.0)

	# --- Incremento 1: Total / designation-department / chart / report_summary ----

	def test_total_granularity_one_row_per_employee(self):
		_subj, emp, _po, _pc = self._p4_scenario()
		data = self._run(
			self.exec_user, from_date="2026-01-05", to_date="2026-01-09", employee=emp, granularity="Total"
		)
		row = self._row(data, emp)  # exactamente una fila
		self.assertEqual(row["period"], "Total")
		self.assertEqual(row["planned_total"], 8.0)  # agregado del rango

	def test_designation_department_columns_present(self):
		_subj, emp, _po, _pc = self._p4_scenario()
		row = self._row(
			self._run(self.exec_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp), emp
		)
		self.assertIn("designation", row)  # presentes aunque el Employee no las tenga
		self.assertIn("department", row)

	def test_total_includes_confidential_in_kpis(self):
		# Observador normal (subj): ve 4h visibles + 4h confidenciales; el KPI NO debe subestimar.
		subj, emp, _po, _pc = self._p4_scenario()
		data, _chart, summary = self._run_full(
			subj, from_date="2026-01-05", to_date="2026-01-05", granularity="Total"
		)
		row = self._row(data, emp)
		self.assertEqual(row["planned_total"], 8.0)  # Total = visible(4) + confidencial(4)
		self.assertEqual(row["confidential"], 4.0)  # el confidencial NO se elimina
		util = next(s for s in summary if s["datatype"] == "Percent")
		self.assertEqual(util["value"], 100.0)  # 8/8 → utilización sobre Total, no 4/8=50

	def test_report_summary_and_chart_no_identity_leak(self):
		_subj, _emp, _po, p_conf = self._p4_scenario()
		_data, chart, summary = self._run_full(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05")
		self.assertNotIn(p_conf, frappe.as_json(summary))  # KPIs sin identidad confidencial
		self.assertNotIn(p_conf, frappe.as_json(chart))  # labels/datasets sin identidad de proyecto

	def test_chart_aggregates_by_employee_without_filter(self):
		# Sin filtro employee → una barra por Employee (labels = employees), no por periodo repetido.
		subj, emp, _po, _pc = self._p4_scenario()
		_data, chart, _summary = self._run_full(subj, from_date="2026-01-05", to_date="2026-01-06")
		self.assertIn(emp, chart["data"]["labels"])
		self.assertEqual(len(chart["data"]["datasets"]), 2)  # Availability vs Planned total
