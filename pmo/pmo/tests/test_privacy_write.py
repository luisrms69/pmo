# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 Incremento 2 — Aislamiento WRITE de Project/Task (ADR-0002 D6). Datos ficticios.

Política:
- Project: owner escribe; PMO Project Member y PMO Executive Access NO escriben el Project.
- Task: owner/member del Project y assignee (ToDo) escriben; PMO Executive Access solo lectura.
- Capacidad (rol) x alcance (hooks): todos los usuarios tienen rol con write; el hook aplica el alcance.
"""

import frappe
from frappe.desk.form import assign_to
from frappe.tests import IntegrationTestCase

MARK = "PMO-PRIV-W"
BASE = ["Projects User"]  # write+create nativo en Project y Task


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
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def _project(name, owner):
	p = frappe.get_doc({"doctype": "Project", "project_name": name})
	p.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value("Project", p.name, "owner", owner)
	return p.name


def _task(subject, project):
	return (
		frappe.get_doc({"doctype": "Task", "subject": subject, "project": project})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


class TestPrivacyWrite(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.flags.mute_emails = True
		cls.owner = _user(f"{MARK}-owner@example.com", BASE)
		cls.member = _user(f"{MARK}-member@example.com", BASE)
		cls.assignee = _user(f"{MARK}-assignee@example.com", BASE)
		cls.outsider = _user(f"{MARK}-outsider@example.com", BASE)
		cls.exec_user = _user(f"{MARK}-exec@example.com", [*BASE, "PMO Executive Access"])

		cls.p1 = _project(f"{MARK}-P1", cls.owner)
		cls.p2 = _project(f"{MARK}-P2", cls.owner)
		cls.t1 = _task(f"{MARK}-T1", cls.p1)
		cls.t2 = _task(f"{MARK}-T2", cls.p1)
		cls.t3 = _task(f"{MARK}-T3", cls.p2)

		proj = frappe.get_doc("Project", cls.p1)
		proj.append("pmo_members", {"member": cls.member})
		proj.flags.ignore_mandatory = True
		proj.save(ignore_permissions=True)

		assign_to.add({"doctype": "Task", "name": cls.t1, "assign_to": frappe.as_json([cls.assignee])})

	def _can(self, dt, dn, user, ptype):
		frappe.set_user(user)
		try:
			r = frappe.has_permission(dt, doc=dn, user=user, ptype=ptype)
		finally:
			frappe.set_user("Administrator")
		return r

	# --- Project WRITE ----------------------------------------------------

	def test_project_write(self):
		self.assertTrue(self._can("Project", self.p1, self.owner, "write"))
		self.assertFalse(self._can("Project", self.p1, self.member, "write"))  # member NO escribe Project
		self.assertFalse(self._can("Project", self.p1, self.exec_user, "write"))  # executive read-only
		self.assertFalse(self._can("Project", self.p1, self.outsider, "write"))
		# read del executive sí
		self.assertTrue(self._can("Project", self.p1, self.exec_user, "read"))

	# --- Task WRITE -------------------------------------------------------

	def test_task_write(self):
		# owner y member del Project → escriben Tasks del Project
		self.assertTrue(self._can("Task", self.t1, self.owner, "write"))
		self.assertTrue(self._can("Task", self.t1, self.member, "write"))
		self.assertFalse(self._can("Task", self.t3, self.member, "write"))  # Task de P2 → no
		# assignee escribe solo su Task
		self.assertTrue(self._can("Task", self.t1, self.assignee, "write"))
		self.assertFalse(self._can("Task", self.t2, self.assignee, "write"))
		# executive: solo lectura
		self.assertFalse(self._can("Task", self.t1, self.exec_user, "write"))
		self.assertTrue(self._can("Task", self.t1, self.exec_user, "read"))
		# outsider: nada
		self.assertFalse(self._can("Task", self.t1, self.outsider, "write"))
