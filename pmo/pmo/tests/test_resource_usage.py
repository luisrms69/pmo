# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 vistas / ADR-0002 P4 — Reporte PMO Resource Usage by Project. Datos ficticios.

Verifica el árbol Employee -> Project con enmascarado P4: proyectos visibles identificados (con
project_id auxiliar), no visibles consolidados en UNA fila "Comprometido (confidencial)" sin ningún
identificador, bucket separado "Sin proyecto", y la igualdad exacta
Total Employee = Σ visibles + Sin proyecto + Comprometido (confidencial) para Planned y Actual.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.pmo.report.pmo_resource_usage_by_project.pmo_resource_usage_by_project import execute

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
	frappe.db.set_value("Timesheet", ts.name, "docstatus", 1)


class TestResourceUsage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_hl()
		_activity_type()
		_capacity_global(8.0)
		cls.mgr_user = _user("ru-mgr@example.com", ["PMO Manager"])

	def setUp(self):
		frappe.db.delete("ToDo", {"reference_type": "Task"})
		frappe.db.delete("Timesheet Detail")
		frappe.db.delete("Timesheet")

	def _run(self, observer, **filters):
		frappe.set_user(observer)
		try:
			_cols, data = execute(filters)
		finally:
			frappe.set_user("Administrator")
		return data

	def _scenario(self):
		subj = _user("ru-subj@example.com")
		emp = _employee("RU Subject", subj)
		p_open = _project("RU-P-OPEN", owner=subj)  # visible (owner)
		p_conf = _project("RU-P-CONF", owner="Administrator")  # confidencial
		_assign(_task("RU-T-OPEN", p_open, 4), subj)  # 4h visible
		_assign(_task("RU-T-CONF", p_conf, 4), subj)  # 4h confidencial
		_assign(_task("RU-T-NOPROJ", None, 6), subj)  # 6h sin proyecto
		_timesheet(emp, p_open, 5)  # 5h Actual en proyecto visible
		return subj, emp, p_open, p_conf

	def _children(self, data, emp):
		return [r for r in data if r.get("employee") is None]

	def _parent(self, data, emp):
		rows = [r for r in data if r.get("employee") == emp]
		self.assertEqual(len(rows), 1)
		return rows[0]

	# --- estructura ---------------------------------------------------------

	def test_tree_structure(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		parent = self._parent(data, emp)
		self.assertEqual(parent["indent"], 0)
		children = self._children(data, emp)
		self.assertTrue(all(c["indent"] == 1 for c in children))
		self.assertEqual(len(children), 3)  # visible + sin proyecto + confidencial

	def test_total_equals_children(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		parent = self._parent(data, emp)
		children = self._children(data, emp)
		self.assertEqual(parent["planned"], round(sum(c["planned"] for c in children), 2))
		self.assertEqual(parent["actual"], round(sum(c["actual"] for c in children), 2))
		self.assertEqual(parent["planned"], 14.0)  # 4 + 6 + 4
		self.assertEqual(parent["actual"], 5.0)  # solo p_open

	# --- P4 -----------------------------------------------------------------

	def test_confidential_single_row_without_identifier(self):
		subj, emp, _po, p_conf = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		conf = [r for r in data if r["project"] == "Comprometido (confidencial)"]
		self.assertEqual(len(conf), 1)  # una sola fila
		self.assertEqual(conf[0]["planned"], 4.0)  # confidencial cuenta en el total
		self.assertNotIn("project_id", conf[0])  # sin identificador auxiliar
		self.assertNotIn(p_conf, frappe.as_json(data))  # nombre real nunca serializado

	def test_visible_project_has_identifier(self):
		subj, emp, p_open, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		vis = [r for r in data if r.get("project_id") == p_open]
		self.assertEqual(len(vis), 1)
		self.assertEqual(vis[0]["planned"], 4.0)

	def test_sin_proyecto_bucket_separate(self):
		subj, emp, _po, _pc = self._scenario()
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		np = [r for r in data if r["project"] == "Sin proyecto"]
		self.assertEqual(len(np), 1)
		self.assertEqual(np[0]["planned"], 6.0)
		self.assertNotIn("project_id", np[0])  # no revela identidad (no existe)

	def test_manager_no_confidential_identity_leak(self):
		# manager no es owner/member → p_open y p_conf ambos confidenciales para él
		_subj, emp, p_open, p_conf = self._scenario()
		data = self._run(self.mgr_user, from_date="2026-01-05", to_date="2026-01-05", employee=emp)
		blob = frappe.as_json(data)
		self.assertNotIn(p_open, blob)
		self.assertNotIn(p_conf, blob)
		conf = [r for r in data if r["project"] == "Comprometido (confidencial)"]
		self.assertEqual(conf[0]["planned"], 8.0)  # 4 + 4 consolidados, cuentan en el total

	def test_normal_sees_only_own_subtree(self):
		subj, emp, _po, _pc = self._scenario()
		other = _user("ru-other@example.com")
		other_emp = _employee("RU Other", other)
		_assign(_task("RU-T-OTHER", _project("RU-P-OTHER", owner=other), 3), other)
		data = self._run(subj, from_date="2026-01-05", to_date="2026-01-05")
		parents = [r["employee"] for r in data if r.get("employee")]
		self.assertIn(emp, parents)
		self.assertNotIn(other_emp, parents)
