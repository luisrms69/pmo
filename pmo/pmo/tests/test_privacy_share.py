# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 Incremento 3 — SHARE de Project/Task (ADR-0002 D7). Datos ficticios.

Política: SHARE manual solo `PMO Executive Access` / `Administrator`; owner/member/assignee/otros NO.
Implementado por el permiso nativo vía `has_permission(ptype="share")` (sin Custom DocPerm).
Además: `assign_to` NO crea auto-share (la visibilidad del asignado viene del ToDo).
"""

import frappe
from frappe.desk.form import assign_to
from frappe.tests import IntegrationTestCase

MARK = "PMO-PRIV-S"
BASE = ["Projects User"]  # incluye capacidad nativa share=1 sobre Project/Task


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


class TestPrivacyShare(IntegrationTestCase):
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
		cls.t1 = _task(f"{MARK}-T1", cls.p1)

		proj = frappe.get_doc("Project", cls.p1)
		proj.append("pmo_members", {"member": cls.member})
		proj.flags.ignore_mandatory = True
		proj.save(ignore_permissions=True)

		assign_to.add({"doctype": "Task", "name": cls.t1, "assign_to": frappe.as_json([cls.assignee])})

	def _can_share(self, dt, dn, user):
		frappe.set_user(user)
		try:
			r = frappe.has_permission(dt, doc=dn, user=user, ptype="share")
		finally:
			frappe.set_user("Administrator")
		return r

	# --- has_permission(ptype="share") ------------------------------------

	def test_share_permission_restricted_to_executive(self):
		self.assertTrue(self._can_share("Project", self.p1, self.exec_user))
		self.assertTrue(self._can_share("Task", self.t1, self.exec_user))
		self.assertFalse(self._can_share("Project", self.p1, self.owner))
		self.assertFalse(self._can_share("Project", self.p1, self.member))
		self.assertFalse(self._can_share("Task", self.t1, self.assignee))
		self.assertFalse(self._can_share("Project", self.p1, self.outsider))

	# --- Share manual real ------------------------------------------------

	def test_manual_share_blocked_for_non_executive(self):
		frappe.set_user(self.member)
		try:
			with self.assertRaises(frappe.PermissionError):
				frappe.share.add("Project", self.p1, self.outsider)
		finally:
			frappe.set_user("Administrator")

	def test_manual_share_allowed_for_executive(self):
		frappe.set_user(self.exec_user)
		try:
			frappe.share.add("Project", self.p1, self.outsider)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(
			frappe.db.exists(
				"DocShare", {"share_doctype": "Project", "share_name": self.p1, "user": self.outsider}
			)
		)

	# --- assign_to NO crea auto-share -------------------------------------

	def test_assignment_creates_no_docshare(self):
		# assignee ya asignado a t1 en setUpClass; su visibilidad viene del ToDo, no de un share
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Task",
					"reference_name": self.t1,
					"allocated_to": self.assignee,
					"status": "Open",
				},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"DocShare", {"share_doctype": "Task", "share_name": self.t1, "user": self.assignee}
			)
		)
