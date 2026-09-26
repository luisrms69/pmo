# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 — helper get_risk_history (solo lectura) + Print Format PMO Project Risk. Datos ficticios.

Cubre: P4 (autorizado obtiene historia; no autorizado → PermissionError), Version old→new, Comment/Nota,
múltiples cambios de un mismo save, Risk sin historia, y el Print Format instalado/asociado como default."""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.risk_history import get_risk_history


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


def _project(name, owner="Administrator"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Open"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	return pid


def _risk(project, **vals):
	doc = {
		"doctype": "PMO Project Risk",
		"project": project,
		"description": vals.pop("description", "Riesgo de prueba"),
		"probability": vals.pop("probability", "High likelihood"),
		"impact": vals.pop("impact", "High"),
	}
	doc.update(vals)
	return frappe.get_doc(doc).insert(ignore_permissions=True)


class TestRiskHistory(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_no_history_returns_empty(self):
		r = _risk(_project("RH Empty"))
		self.assertEqual(get_risk_history(r.name), [])  # recién creado: sin Version ni Comment

	def test_same_save_merged_into_single_event(self):
		# Version (old→new) + Comment (nota) del MISMO save → UN solo evento fusionado (no dos renglones).
		r = _risk(_project("RH Basic"), probability="High likelihood", impact="High")
		r.status = "Managing"
		r.update_note = "El proveedor confirmó una nueva fecha."
		r.save(ignore_version=False)  # Frappe desactiva Version en test por defecto; lo forzamos
		history = get_risk_history(r.name)
		self.assertEqual(len(history), 1)  # una sola fila, no Version + Comment separados
		ev = history[0]
		self.assertEqual(ev["kind"], "change")
		status_change = next((c for c in ev["changes"] if c["new"] == "Managing"), None)
		self.assertIsNotNone(status_change)  # Version old → new presente
		self.assertEqual(status_change["old"], "Open")
		self.assertEqual(ev["note"], "El proveedor confirmó una nueva fecha.")  # nota fusionada
		self.assertTrue(ev["who"] and ev["when_display"])

	def test_multiple_changes_single_version_event(self):
		r = _risk(_project("RH Multi"), probability="High likelihood", impact="High")
		r.probability = "Medium likelihood"
		r.status = "Managing"
		r.update_note = "Reevaluación integral."
		r.save(ignore_version=False)
		history = get_risk_history(r.name)
		change = next(e for e in history if e["kind"] == "change")
		# Un solo evento Version agrupa los campos cambiados en ese save (probability + status [+ exposure]).
		self.assertGreaterEqual(len(change["changes"]), 2)
		self.assertTrue(any(c["new"] == "Managing" for c in change["changes"]))

	def test_chronological_order(self):
		r = _risk(_project("RH Order"), probability="High likelihood", impact="High")
		r.status = "Managing"
		r.update_note = "Primero."
		r.save(ignore_version=False)
		history = get_risk_history(r.name)
		times = [e["when"] for e in history]
		self.assertEqual(times, sorted(times))

	def test_p4_authorized_user_gets_history(self):
		owner = _user("rh_owner@example.com", roles=("Projects User",))
		p = _project("RH P4ok", owner=owner)
		r = _risk(p, probability="High likelihood", impact="High")
		frappe.set_user(owner)
		try:
			# No debe lanzar; devuelve lista (posiblemente vacía) para un riesgo visible.
			self.assertIsInstance(get_risk_history(r.name), list)
		finally:
			frappe.set_user("Administrator")

	def test_p4_unauthorized_user_blocked(self):
		owner = _user("rh_owner2@example.com", roles=("Projects User",))
		stranger = _user("rh_stranger@example.com", roles=("Projects User",))
		p = _project("RH P4no", owner=owner)
		r = _risk(p, probability="High likelihood", impact="High")
		frappe.set_user(stranger)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_risk_history(r.name)
		finally:
			frappe.set_user("Administrator")

	def test_print_format_installed_and_default(self):
		self.assertTrue(frappe.db.exists("Print Format", "PMO Project Risk"))
		pf = frappe.get_doc("Print Format", "PMO Project Risk")
		self.assertEqual(pf.doc_type, "PMO Project Risk")
		self.assertEqual(pf.standard, "Yes")
		self.assertEqual(frappe.get_meta("PMO Project Risk").default_print_format, "PMO Project Risk")
