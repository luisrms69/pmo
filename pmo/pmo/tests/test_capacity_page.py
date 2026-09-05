# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 / ADR-0002 P4 -- Endpoint del Resource Center de la Page Capacity Planning. Datos ficticios.

Verifica que `pmo.capacity_page.get_resources` respeta el MISMO alcance de observador que los reportes
(reutiliza `_scope_employees`): un Employee normal recibe unicamente su propio Employee; Manager y
Executive reciben el alcance cuantitativo completo. Ademas verifica que el payload solo contiene
metadata organizacional segura (sin Project/Task, sin identificadores ocultos).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.capacity_page import get_resources

FROM = "2026-09-07"
TO = "2026-09-11"

SAFE_KEYS = {"employee", "employee_name", "email", "department", "designation", "branch"}


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


HL = "CP-HL-TEST"


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


def _employee(name, user_id):
	emp = frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "first_name": name, "status": "Active", "holiday_list": _hl()})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Employee", emp, "user_id", user_id)
	# El rol `Employee` lo gestiona ERPNext: solo persiste si el User tiene un Employee vinculado
	# (User.validate lo retira si no). Se concede DESPUES de vincular para que quede efectivo (igual
	# que `Employee.update_user` en el alta real). Necesario para el gate real de la Page/reporte.
	frappe.get_doc("User", user_id).add_roles("Employee")
	return emp


def _capacity(emp, hours=8.0):
	if not frappe.get_all("PMO Capacity", filters={"employee": emp, "from_date": "2026-01-01"}, limit=1):
		frappe.get_doc(
			{
				"doctype": "PMO Capacity",
				"employee": emp,
				"from_date": "2026-01-01",
				"capacity_hours_per_day": hours,
			}
		).insert(ignore_permissions=True)


def _project(name, owner):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner)
	return pid


def _task(name, project, hours, from_date, to_date):
	tid = frappe.db.exists("Task", {"subject": name})
	if tid:
		return tid
	return (
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": name,
				"project": project,
				"expected_time": hours,
				"exp_start_date": from_date,
				"exp_end_date": to_date,
			}
		)
		.insert(ignore_permissions=True)
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
			"description": f"Asignacion {task}",
		}
	).insert(ignore_permissions=True)


class TestCapacityPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.exec_user = _user("cp-exec@example.com", ["PMO Executive Access"])
		cls.mgr_user = _user("cp-mgr@example.com", ["PMO Manager"])

		cls.ana_user = _user("cp-ana@example.com", ["Employee"])
		cls.bruno_user = _user("cp-bruno@example.com", ["Employee"])
		cls.ana = _employee("CP Ana", cls.ana_user)
		cls.bruno = _employee("CP Bruno", cls.bruno_user)
		_capacity(cls.ana, 8.0)
		_capacity(cls.bruno, 6.0)

	def _resources(self, observer):
		frappe.set_user(observer)
		try:
			return get_resources(FROM, TO)
		finally:
			frappe.set_user("Administrator")

	# --- alcance por observador -------------------------------------------------

	def test_normal_sees_only_own_employee(self):
		res = self._resources(self.ana_user)
		self.assertEqual([r["employee"] for r in res], [self.ana])

	def test_normal_does_not_see_other_employees(self):
		res = self._resources(self.bruno_user)
		ids = [r["employee"] for r in res]
		self.assertIn(self.bruno, ids)
		self.assertNotIn(self.ana, ids)

	def test_manager_sees_full_scope(self):
		ids = [r["employee"] for r in self._resources(self.mgr_user)]
		self.assertIn(self.ana, ids)
		self.assertIn(self.bruno, ids)

	def test_executive_sees_full_scope(self):
		ids = [r["employee"] for r in self._resources(self.exec_user)]
		self.assertIn(self.ana, ids)
		self.assertIn(self.bruno, ids)

	# --- payload seguro (sin Project/Task, sin identidad oculta) ----------------

	def test_payload_only_safe_metadata(self):
		res = self._resources(self.exec_user)
		self.assertTrue(res)
		for r in res:
			self.assertEqual(set(r.keys()), SAFE_KEYS, "get_resources debe devolver solo metadata segura")

	def test_no_project_or_task_identifier_in_payload(self):
		blob = frappe.as_json(self._resources(self.mgr_user)).lower()
		self.assertNotIn("project", blob)
		self.assertNotIn('"task"', blob)
		self.assertNotIn("reference_name", blob)

	def test_metadata_matches_employee(self):
		res = self._resources(self.ana_user)
		row = res[0]
		self.assertEqual(row["employee"], self.ana)
		self.assertEqual(row["email"], self.ana_user)
		self.assertEqual(row["employee_name"], "CP Ana")


class TestCapacityPageReportPath(IntegrationTestCase):
	"""Regresion del CAMINO REAL de la Page: `frappe.desk.query_report.run` (gate de permisos incluido),
	no `execute()` directo. Un Employee normal con rol `Employee` + Employee activo debe poder cargar su
	propia capacidad, manteniendo P4 (confidencial contado sin identidad) y sin ver a terceros.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# usuario normal real: rol Employee + Employee activo vinculado (contrato v0.4.0)
		cls.subj = _user("cpr-ana@example.com", ["Employee"])
		cls.emp = _employee("CPR Ana", cls.subj)
		_capacity(cls.emp, 8.0)
		# un tercero con actividad, para probar que el normal NO lo ve
		cls.other = _user("cpr-otro@example.com", ["Employee"])
		cls.other_emp = _employee("CPR Otro", cls.other)
		_capacity(cls.other_emp, 8.0)

		cls.p_open = _project("CPR-P-OPEN", owner=cls.subj)  # visible (owner = subj)
		cls.p_conf = _project("CPR-P-CONF", owner="Administrator")  # confidencial para subj
		_assign(_task("CPR-T-OPEN", cls.p_open, 4, FROM, FROM), cls.subj)
		_assign(_task("CPR-T-CONF", cls.p_conf, 4, FROM, FROM), cls.subj)
		# actividad del tercero (proyecto propio del tercero)
		p_other = _project("CPR-P-OTHER", owner=cls.other)
		_assign(_task("CPR-T-OTHER", p_other, 4, FROM, FROM), cls.other)

	def _run_as(self, user):
		from frappe.desk.query_report import run

		frappe.set_user(user)
		try:
			return run(
				report_name="PMO Capacity Planning",
				filters={"from_date": FROM, "to_date": FROM, "granularity": "Day"},
			)
		finally:
			frappe.set_user("Administrator")

	def test_normal_can_run_report_via_page_path(self):
		"""El gate real (query_report.run) NO debe bloquear a un Employee normal."""
		out = self._run_as(self.subj)
		self.assertTrue(out.get("result"), "el reporte debe devolver filas por el camino real")

	def test_normal_only_own_employee_and_p4_via_run(self):
		rows = self._run_as(self.subj)["result"]
		emps = {r["employee"] for r in rows}
		self.assertEqual(emps, {self.emp}, "el normal solo debe ver su propio Employee")
		self.assertNotIn(self.other_emp, emps)

		own = next(r for r in rows if r["employee"] == self.emp)
		# P4: visible (owner) + confidencial (no visible) sumados en el total
		self.assertEqual(own["planned_visible"], 4.0)
		self.assertEqual(own["confidential"], 4.0)
		self.assertEqual(own["planned_total"], 8.0)

	def test_no_confidential_identity_via_run(self):
		blob = frappe.as_json(self._run_as(self.subj)["result"])
		self.assertNotIn(self.p_conf, blob, "el nombre del proyecto confidencial no debe viajar al cliente")
		self.assertNotIn("CPR-T-CONF", blob, "el nombre de la tarea confidencial no debe viajar al cliente")
