# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0005 D11 — Script Report PMO Baseline Comparison. Datos ficticios.

Valida el `execute(filters)`: reutiliza `compare_baselines` (P4 read en ambas + mismo Project), aplana a
filas de SOLO diferencias con Antes/Después/Variación, resumen superior, y el CR como contexto (no
atribución)."""

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.pmo.report.pmo_baseline_comparison.pmo_baseline_comparison import execute


def _user(email, roles=("Projects User",)):
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


def _project(name, owner):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": "Open",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner)
	return pid


def _leaf(subject, project, end):
	tid = frappe.db.exists("Task", {"subject": subject})
	if tid:
		return tid
	return (
		frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"expected_time": 8,
				"exp_start_date": "2026-01-05",
				"exp_end_date": end,
				"status": "Open",
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _baseline(project, revision, btype="Original", supersedes=None, effective=None):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,
			"baseline_type": btype,
			"supersedes_baseline": supersedes,
			"effective_date": effective or "2026-01-01",
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


class TestBaselineComparisonReport(IntegrationTestCase):
	def _pair(self, name, owner):
		p = _project(name, owner)
		task = _leaf(f"{name} task", p, end="2026-01-09")
		b1 = _baseline(p, "BL-001", effective="2026-01-01")
		frappe.db.set_value("Task", task, "exp_end_date", "2026-01-20")
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-02-01")
		return p, task, b1, b2

	def test_rows_only_differences_and_summary(self):
		owner = _user("rpt-owner@example.com")
		p, _task, b1, b2 = self._pair("RPT-P1", owner)
		frappe.set_user(owner)
		try:
			columns, data, _message, _chart, summary = execute(
				{"project": p, "baseline_before": b1.name, "baseline_after": b2.name}
			)
		finally:
			frappe.set_user("Administrator")

		self.assertEqual(len(columns), 6)
		# solo diferencias: la fila del cambio de Fin con variación en días
		fin = [r for r in data if r["field"] == "Fin"]
		self.assertEqual(len(fin), 1)
		self.assertEqual(fin[0]["change_type"], "Modificada")
		self.assertEqual(fin[0]["variance"], "+11 días")
		# resumen: 1 tarea modificada
		mod = next(s for s in summary if s["label"] == "Tareas modificadas")
		self.assertEqual(mod["value"], 1)

	def test_p4_read_on_both(self):
		owner = _user("rpt-owner2@example.com")
		outsider = _user("rpt-out@example.com")  # con rol pero sin visibilidad
		p, _t, b1, b2 = self._pair("RPT-P2", owner)
		frappe.set_user(outsider)
		try:
			with self.assertRaises(FrappePermissionError):
				execute({"project": p, "baseline_before": b1.name, "baseline_after": b2.name})
		finally:
			frappe.set_user("Administrator")

	def test_cross_project_rejected(self):
		owner = _user("rpt-owner3@example.com")
		_p1, _t1, b1, _b2 = self._pair("RPT-P3", owner)
		p2 = _project("RPT-P3-OTHER", owner)
		_leaf("RPT-P3-OTHER task", p2, end="2026-01-09")
		other = _baseline(p2, "BL-001")
		with self.assertRaises(ValidationError):
			execute({"project": _p1, "baseline_before": b1.name, "baseline_after": other.name})

	def test_missing_filters(self):
		with self.assertRaises(ValidationError):
			execute({"project": "X"})

	def test_cr_shown_as_context(self):
		owner = _user("rpt-owner4@example.com")
		p, _t, b1, b2 = self._pair("RPT-P4", owner)
		frappe.set_user(owner)
		try:
			_c, _d, message, _ch, _s = execute(
				{
					"project": p,
					"baseline_before": b1.name,
					"baseline_after": b2.name,
					"change_request": "PMO-CR-XYZ",
				}
			)
		finally:
			frappe.set_user("Administrator")
		self.assertIn("PMO-CR-XYZ", message)
		self.assertIn("no atribuye", message)  # contexto, no atribución
