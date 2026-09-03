# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 Incremento 1 — Aislamiento READ de Project/Task (ADR-0002). Datos ficticios.

Cubre: List (pqc) y documento único (has_permission) para owner/member/no-miembro/
task-only assignee/executive. Task hereda la frontera del Project; asignación ≠ membresía.
"""

import frappe
from frappe.desk.form import assign_to
from frappe.tests import IntegrationTestCase

MARK = "PMO-PRIV"


def _user(email, roles):
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
	u = frappe.get_doc("User", email)
	u.add_roles(*roles)
	return email


def _project(name, owner):
	p = frappe.get_doc({"doctype": "Project", "project_name": name})
	p.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value("Project", p.name, "owner", owner)
	return p.name


def _task(subject, project):
	t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": project})
	t.insert(ignore_permissions=True, ignore_mandatory=True)
	return t.name


class TestPrivacyRead(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.flags.mute_emails = True
		cls.owner = _user(f"{MARK}-owner@example.com", ["Projects User"])
		cls.member = _user(f"{MARK}-member@example.com", ["Projects User"])
		cls.outsider = _user(f"{MARK}-outsider@example.com", ["Projects User"])
		cls.assignee = _user(f"{MARK}-assignee@example.com", ["Projects User"])
		cls.exec_user = _user(f"{MARK}-exec@example.com", ["Projects User", "PMO Executive Access"])

		cls.p1 = _project(f"{MARK}-P1", cls.owner)
		cls.p2 = _project(f"{MARK}-P2", cls.owner)
		cls.t1 = _task(f"{MARK}-T1", cls.p1)
		cls.t2 = _task(f"{MARK}-T2", cls.p1)
		cls.t3 = _task(f"{MARK}-T3", cls.p2)
		cls.orphan = _task(f"{MARK}-ORPHAN", None)

		# member de P1
		proj = frappe.get_doc("Project", cls.p1)
		proj.append("pmo_members", {"member": cls.member})
		proj.flags.ignore_mandatory = True
		proj.save(ignore_permissions=True)

		# assignee: solo asignado a T1 (de P1), NO miembro
		assign_to.add({"doctype": "Task", "name": cls.t1, "assign_to": frappe.as_json([cls.assignee])})

	def _projects(self, user):
		frappe.set_user(user)
		try:
			r = set(frappe.get_list("Project", pluck="name", limit=0))
		finally:
			frappe.set_user("Administrator")
		return r

	def _tasks(self, user):
		frappe.set_user(user)
		try:
			r = set(frappe.get_list("Task", pluck="name", limit=0))
		finally:
			frappe.set_user("Administrator")
		return r

	def _can_read(self, dt, dn, user):
		frappe.set_user(user)
		try:
			r = frappe.has_permission(dt, doc=dn, user=user, ptype="read")
		finally:
			frappe.set_user("Administrator")
		return r

	# --- Project (list + doc) ---------------------------------------------

	def test_project_list_isolation(self):
		self.assertEqual(self._projects(self.outsider) & {self.p1, self.p2}, set())
		mp = self._projects(self.member)
		self.assertIn(self.p1, mp)
		self.assertNotIn(self.p2, mp)
		self.assertIn(self.p1, self._projects(self.owner))
		ep = self._projects(self.exec_user)
		self.assertIn(self.p1, ep)
		self.assertIn(self.p2, ep)

	def test_project_has_permission(self):
		self.assertTrue(self._can_read("Project", self.p1, self.member))
		self.assertFalse(self._can_read("Project", self.p1, self.outsider))
		self.assertFalse(self._can_read("Project", self.p2, self.member))
		self.assertTrue(self._can_read("Project", self.p2, self.exec_user))
		self.assertTrue(self._can_read("Project", self.p1, self.owner))

	# --- Task (hereda del Project) ----------------------------------------

	def test_task_list_isolation(self):
		mt = self._tasks(self.member)
		self.assertTrue({self.t1, self.t2} <= mt)
		self.assertNotIn(self.t3, mt)
		self.assertEqual(self._tasks(self.outsider) & {self.t1, self.t2, self.t3}, set())
		self.assertTrue({self.t1, self.t2, self.t3} <= self._tasks(self.exec_user))

	def test_task_assignee_sees_only_that_task(self):
		at = self._tasks(self.assignee)
		self.assertIn(self.t1, at)  # asignada
		self.assertNotIn(self.t2, at)  # otra Task de P1 → no
		self.assertNotIn(self.t3, at)
		# y NO ve el Project completo (asignación ≠ membresía)
		self.assertNotIn(self.p1, self._projects(self.assignee))
		self.assertFalse(self._can_read("Project", self.p1, self.assignee))
		self.assertTrue(self._can_read("Task", self.t1, self.assignee))
		self.assertFalse(self._can_read("Task", self.t2, self.assignee))

	def test_projectless_task_is_standard(self):
		# Task sin Project → fuera del boundary → visible por rol nativo (Projects User)
		self.assertIn(self.orphan, self._tasks(self.outsider))
