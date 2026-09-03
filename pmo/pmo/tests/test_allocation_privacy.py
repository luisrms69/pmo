# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 Incremento 2 / ADR-0002 P4 — privacidad de PMO Resource Allocation. Datos ficticios.

El plan hereda el boundary del Project: se ve/edita según la visibilidad del Project (owner/member/
executive). Un outsider no ve el plan en listas ni por documento. Executive ve (global) pero es solo
lectura. El child PMO Allocation Day hereda del padre (sin hooks propios).
"""

import frappe
from frappe.tests import IntegrationTestCase

MARK = "PMO-ALLOC-PRIV"
BASE = ["Projects User"]
HL = "PMO-HL-TEST"


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


def _holiday_list():
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


def _employee():
	existing = frappe.db.exists("Employee", {"employee_name": "PMO Priv Emp"})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "PMO Priv Emp",
				"holiday_list": _holiday_list(),
				"status": "Active",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


class TestAllocationPrivacy(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.owner = _user(f"{MARK}-owner@example.com", BASE)
		cls.member = _user(f"{MARK}-member@example.com", BASE)
		cls.outsider = _user(f"{MARK}-outsider@example.com", BASE)
		cls.exec_user = _user(f"{MARK}-exec@example.com", [*BASE, "PMO Executive Access"])

		emp = _employee()
		existing = frappe.db.exists("Project", {"project_name": f"{MARK}-P1"})
		if existing:
			p = frappe.get_doc("Project", existing)
		else:
			p = frappe.get_doc({"doctype": "Project", "project_name": f"{MARK}-P1"})
			p.insert(ignore_permissions=True, ignore_mandatory=True)
		if not any(m.member == cls.member for m in p.get("pmo_members", [])):
			p.append("pmo_members", {"member": cls.member})
			p.flags.ignore_mandatory = True
			p.save(ignore_permissions=True)
		# owner al final vía set_value (sin save posterior) para no chocar con el timestamp del doc.
		frappe.db.set_value("Project", p.name, "owner", cls.owner)
		cls.p1 = p.name

		cls.alloc = (
			frappe.get_doc(
				{
					"doctype": "PMO Resource Allocation",
					"employee": emp,
					"project": cls.p1,
					"from_date": "2026-01-05",
					"to_date": "2026-01-09",
					"planned_hours": 20.0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _list_as(self, user):
		frappe.set_user(user)
		try:
			return frappe.get_list("PMO Resource Allocation", pluck="name", limit=0)
		finally:
			frappe.set_user("Administrator")

	def _can(self, user, ptype):
		frappe.set_user(user)
		try:
			return frappe.has_permission("PMO Resource Allocation", doc=self.alloc, user=user, ptype=ptype)
		finally:
			frappe.set_user("Administrator")

	# --- listas (pqc) -------------------------------------------------------

	def test_list_isolation(self):
		self.assertIn(self.alloc, self._list_as(self.owner))
		self.assertIn(self.alloc, self._list_as(self.member))
		self.assertIn(self.alloc, self._list_as(self.exec_user))  # global reader
		self.assertNotIn(self.alloc, self._list_as(self.outsider))

	# --- documento único (has_permission) -----------------------------------

	def test_read_permission(self):
		self.assertTrue(self._can(self.owner, "read"))
		self.assertTrue(self._can(self.member, "read"))
		self.assertTrue(self._can(self.exec_user, "read"))
		self.assertFalse(self._can(self.outsider, "read"))

	def test_write_permission(self):
		self.assertTrue(self._can(self.owner, "write"))
		self.assertTrue(self._can(self.member, "write"))
		self.assertFalse(self._can(self.exec_user, "write"))  # executive solo lectura
		self.assertFalse(self._can(self.outsider, "write"))

	def test_submit_permission_follows_write(self):
		self.assertTrue(self._can(self.member, "submit"))
		self.assertFalse(self._can(self.exec_user, "submit"))
		self.assertFalse(self._can(self.outsider, "submit"))
