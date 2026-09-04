# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 vistas / ADR-0002 P0-P4 — Reporte PMO Work by Resource. Datos ficticios.

Verifica la doble evaluación independiente Task vs Project, la semántica de rango de `planned_hours`,
las Tasks sin fechas, y el enmascarado P4 (Task no visible -> agregado confidencial sin identidad).
Incluye tests unitarios de `is_task_visible` (DocShare y System Manager).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.permissions import is_task_visible
from pmo.pmo.report.pmo_work_by_resource.pmo_work_by_resource import execute

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


def _project(name, owner, members=()):
	p = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", p, "owner", owner)
	if members:
		doc = frappe.get_doc("Project", p)
		existing = {m.member for m in doc.get("pmo_members", [])}
		for m in members:
			if m not in existing:
				doc.append("pmo_members", {"member": m})
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
	return p


def _task(subject, project, expected, start="2026-01-05", end="2026-01-05"):
	existing = frappe.db.exists("Task", {"subject": subject})
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


class TestWorkByResource(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.flags.mute_emails = True
		_hl()
		_capacity_global(8.0)
		cls.mgr_user = _user("wbr-mgr@example.com", ["PMO Manager", "Projects User"])

	def setUp(self):
		frappe.db.delete("ToDo", {"reference_type": "Task"})

	def _run(self, observer, **filters):
		frappe.set_user(observer)
		try:
			_cols, data = execute(filters)
		finally:
			frappe.set_user("Administrator")
		return data

	def _columns(self):
		return execute({"from_date": "2026-01-05", "to_date": "2026-01-05"})[0]

	# --- is_task_visible (canónico: DocShare, System Manager) ---------------

	def test_is_task_visible_via_docshare(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		_employee("WBR Subject", subj)
		p_conf = _project("WBR-P-CONF", owner="Administrator")
		task = _task("WBR-T-SHARE", p_conf, 4)
		_assign(task, subj)
		outsider = _user("wbr-outsider@example.com", ["Projects User"])
		self.assertFalse(is_task_visible(task, outsider))  # ni assignee ni member
		frappe.share.add("Task", task, outsider, read=1)  # DocShare explícito
		self.assertTrue(is_task_visible(task, outsider))  # ahora sí (canónico incluye share)

	def test_system_manager_no_extra_task_visibility(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		_employee("WBR Subject", subj)
		p_conf = _project("WBR-P-CONF", owner="Administrator")
		task = _task("WBR-T-SYS", p_conf, 4)
		_assign(task, subj)
		sysmgr = _user("wbr-sys@example.com", ["System Manager", "Projects User"])
		self.assertFalse(is_task_visible(task, sysmgr))  # rol no concede alcance

	# --- doble boundary Task vs Project -------------------------------------

	def test_task_visible_project_confidential(self):
		# subj ve su Task (assignee) aunque no sea miembro del Project confidencial
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		p_conf = _project("WBR-P-CONF", owner="Administrator")
		task = _task("WBR-T-CONFPROJ", p_conf, 4)
		_assign(task, subj)
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		row = next(r for r in data if r.get("task_id") == task)
		self.assertEqual(row["project"], "Confidencial")  # Project enmascarado
		self.assertNotIn("project_id", row)  # sin id del Project
		self.assertEqual(row["planned_hours"], 4.0)

	def test_task_visible_project_visible(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		p_open = _project("WBR-P-OPEN", owner=subj)
		task = _task("WBR-T-OPEN", p_open, 4)
		_assign(task, subj)
		row = next(
			r
			for r in self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
			if r.get("task_id") == task
		)
		self.assertEqual(row["project_id"], p_open)  # Project identificado

	def test_task_without_project(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		task = _task("WBR-T-NOPROJ", None, 4)
		_assign(task, subj)
		row = next(
			r
			for r in self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
			if r.get("task_id") == task
		)
		self.assertEqual(row["project"], "Sin proyecto")
		self.assertNotIn("project_id", row)

	# --- Task no visible -> agregado confidencial sin identidad --------------

	def test_invisible_task_consolidated_without_identity(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		p_conf = _project("WBR-P-CONF", owner="Administrator")
		task = _task("WBR-T-SECRET", p_conf, 4)
		_assign(task, subj)
		# manager: ni assignee ni member -> la Task no es visible para él
		data = self._run(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		blob = frappe.as_json(data)
		self.assertNotIn(task, blob)  # identidad de la Task nunca llega
		self.assertNotIn("WBR-T-SECRET", blob)  # ni el subject
		conf = [r for r in data if r["task"] == "Comprometido (confidencial)"]
		self.assertEqual(len(conf), 1)
		self.assertEqual(conf[0]["planned_hours"], 4.0)  # las horas se conservan
		self.assertNotIn("task_id", conf[0])
		self.assertNotIn("project_id", conf[0])

	# --- rango parcial + sin fechas -----------------------------------------

	def test_partial_range_planned_hours(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		p_open = _project("WBR-P-OPEN", owner=subj)
		# 8h sobre 05..09 (06 festivo) -> 4 días laborables -> 2h/día
		task = _task("WBR-T-RANGE", p_open, 8, start="2026-01-05", end="2026-01-09")
		_assign(task, subj)
		row = next(
			r
			for r in self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
			if r.get("task_id") == task
		)
		self.assertEqual(row["expected_time"], 8.0)  # esfuerzo total de la Task
		self.assertEqual(row["planned_hours"], 2.0)  # solo el día consultado

	def test_visible_task_without_dates(self):
		subj = _user("wbr-subj@example.com", ["Projects User"])
		emp = _employee("WBR Subject", subj)
		p_open = _project("WBR-P-OPEN", owner=subj)
		task = _task("WBR-T-NODATE", p_open, 6, start=None, end=None)
		_assign(task, subj)
		row = next(
			r
			for r in self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
			if r.get("task_id") == task
		)
		self.assertIsNone(row["exp_start_date"])  # sin fechas
		self.assertIsNone(row["exp_end_date"])
		self.assertEqual(row["planned_hours"], 6.0)  # horas conocidas, no ubicables

	# --- estructura ---------------------------------------------------------

	def test_no_actual_column(self):
		fieldnames = [c["fieldname"] for c in self._columns()]
		self.assertNotIn("actual", fieldnames)
		self.assertNotIn("actual_hours", fieldnames)
