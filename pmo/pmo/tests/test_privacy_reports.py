# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""P0 Incremento 4 — cierre de vectores que se saltan `pqc` (ADR-0002). Datos ficticios.

1. Reports de ERPNext que ignoran `pqc` (get_all/db.sql) restringidos a `PMO Executive Access` /
   `Administrator` vía `Custom Role` (fixture): un `Projects User` no ejecutivo NO puede ejecutarlos.
2. `create_duplicate_project` (override) exige READ sobre el Project origen: un no-miembro que conozca
   el nombre NO puede duplicar (exfiltrar Tasks) → `PermissionError`.

Requiere que los fixtures (Custom Role) estén importados en el site de tests (`bench migrate`).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.overrides import create_duplicate_project

MARK = "PMO-PRIV-R"
BASE = ["Projects User"]  # capacidad nativa read/report sobre Project/Task
RESTRICTED_REPORTS = ("Project Summary", "Delayed Tasks Summary", "Project wise Stock Tracking")


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


class TestPrivacyReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.outsider = _user(f"{MARK}-outsider@example.com", BASE)
		cls.exec_user = _user(f"{MARK}-exec@example.com", [*BASE, "PMO Executive Access"])
		cls.owner = _user(f"{MARK}-owner@example.com", BASE)
		cls.p1 = _project(f"{MARK}-P1", cls.owner)

	def _is_permitted(self, report, user):
		frappe.set_user(user)
		try:
			return frappe.get_doc("Report", report).is_permitted()
		finally:
			frappe.set_user("Administrator")

	# --- Custom Role restringe los 3 reports a Executive ------------------

	def test_reports_have_custom_role_fixture(self):
		for report in RESTRICTED_REPORTS:
			cr = frappe.db.get_value("Custom Role", {"report": report}, "name")
			self.assertTrue(cr, f"Falta Custom Role (fixture) para el report {report!r}")
			roles = frappe.get_all("Has Role", filters={"parent": cr}, pluck="role")
			self.assertEqual(roles, ["PMO Executive Access"], f"Roles inesperados en {report!r}: {roles}")

	def test_reports_restricted_to_executive(self):
		for report in RESTRICTED_REPORTS:
			self.assertTrue(
				self._is_permitted(report, self.exec_user), f"Executive debería ejecutar {report!r}"
			)
			self.assertFalse(
				self._is_permitted(report, self.outsider),
				f"Projects User no ejecutivo NO debería ejecutar {report!r}",
			)

	# --- create_duplicate_project exige READ del origen -------------------

	def test_duplicate_project_blocked_for_outsider(self):
		frappe.set_user(self.outsider)
		try:
			with self.assertRaises(frappe.PermissionError):
				create_duplicate_project(
					frappe.as_json({"name": self.p1, "project_name": self.p1}),
					f"{MARK}-DUP",
				)
		finally:
			frappe.set_user("Administrator")

	def test_duplicate_project_guard_passes_for_owner(self):
		# El owner sí puede leer el origen: el guard de permiso NO lanza PermissionError.
		# (No ejecutamos la duplicación completa: en test-pmo sin Company fallaría por mandatory.)
		frappe.set_user(self.owner)
		try:
			self.assertTrue(frappe.has_permission("Project", ptype="read", doc=self.p1))
		finally:
			frappe.set_user("Administrator")
