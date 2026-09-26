# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Mejora continua (Continuous Improvement) — capacidad SEPARADA de Governance.

Cubre: ToDo nativo creado desde Lessons Learned al submit del Review; el Script Report
`PMO Continuous Improvement` (filtros, overdue, Project vía Review); aislamiento P4 (un usuario sin READ
al Review/Project no ve la acción); Governance no considera estos ToDo; Workspace con la Quick List.
Datos ficticios.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from pmo.governance import governance_flags
from pmo.pmo.report.pmo_continuous_improvement.pmo_continuous_improvement import execute


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
	user = frappe.get_doc("User", email)
	existing = {r.role for r in user.roles}
	for role in roles:
		if role not in existing:
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


def _project(name, owner="Administrator"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Completed"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	frappe.db.set_value("Project", pid, "status", "Completed", update_modified=False)
	return pid


def _closure(project):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Closure",
			"project": project,
			"closure_date": "2026-03-31",
			"final_result": "ok",
			"accepted_by": "Cliente",
			"accepted_on": "2026-03-31",
			"chk_pending_items": 1,
			"chk_ops_handover": 1,
			"chk_contractual_legal": 1,
			"chk_admin_financial": 1,
			"chk_documentation": 1,
			"chk_communicated": 1,
			"chk_resources_released": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _review(project, action="Use ranges", owner="Administrator", target_date="2026-06-30"):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Post-Project Review",
			"project": project,
			"objectives_achieved": "ok",
		}
	)
	doc.append(
		"lessons",
		{
			"area": "Planning",
			"lesson": "Estimate better",
			"recommended_action": action,
			"action_owner": owner,
			"target_date": target_date,
		},
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _rows(filters):
	return execute(filters)[1]


class TestContinuousImprovement(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_submit_creates_open_todo(self):
		p = _project("CI Create")
		_closure(p)
		rev = _review(p)
		todos = frappe.get_all(
			"ToDo",
			filters={"reference_type": "PMO Post-Project Review", "reference_name": rev.name},
			fields=["status", "reference_name"],
		)
		self.assertEqual(len(todos), 1)
		self.assertEqual(todos[0]["status"], "Open")
		self.assertEqual(todos[0]["reference_name"], rev.name)

	def test_report_includes_open_todo_of_visible_review(self):
		p = _project("CI Report")
		_closure(p)
		rev = _review(p)
		rows = _rows({"status": "Open"})
		mine = [r for r in rows if r["review"] == rev.name]
		self.assertEqual(len(mine), 1)
		self.assertEqual(mine[0]["project"], p)  # Project derivado vía Review
		self.assertIn("Use ranges", mine[0]["action"])
		self.assertEqual(mine[0]["responsible"], "Administrator")

	def test_closed_todo_hidden_with_default_open(self):
		p = _project("CI Closed")
		_closure(p)
		rev = _review(p)
		todo = frappe.get_all(
			"ToDo", filters={"reference_type": "PMO Post-Project Review", "reference_name": rev.name}
		)[0]["name"]
		frappe.db.set_value("ToDo", todo, "status", "Closed")
		rows = _rows({"status": "Open"})
		self.assertEqual([r for r in rows if r["review"] == rev.name], [])

	def test_overdue_derivation(self):
		p_over = _project("CI Overdue")
		_closure(p_over)
		rev_over = _review(p_over, target_date=add_days(nowdate(), -5))
		p_ok = _project("CI Future")
		_closure(p_ok)
		rev_ok = _review(p_ok, target_date=add_days(nowdate(), 30))
		rows = _rows({"status": "Open"})
		over = {r["review"]: r["overdue"] for r in rows}
		self.assertEqual(over.get(rev_over.name), 1)
		self.assertEqual(over.get(rev_ok.name), 0)
		# Filtro overdue deja solo las vencidas.
		only = _rows({"status": "Open", "overdue": 1})
		self.assertTrue(all(r["overdue"] == 1 for r in only))
		self.assertIn(rev_over.name, [r["review"] for r in only])
		self.assertNotIn(rev_ok.name, [r["review"] for r in only])

	def test_project_from_review(self):
		p = _project("CI ProjSource")
		_closure(p)
		rev = _review(p)
		row = next(r for r in _rows({"status": "Open"}) if r["review"] == rev.name)
		self.assertEqual(row["project"], p)
		self.assertEqual(row["project"], frappe.db.get_value("PMO Post-Project Review", rev.name, "project"))

	def test_p4_isolation_report(self):
		"""Un usuario sin READ al Review/Project NO ve esa acción en el reporte."""
		owner = _user("ci_owner@example.com")
		stranger = _user("ci_stranger@example.com")
		p = _project("CI P4", owner=owner)
		_closure(p)
		rev = _review(p)
		frappe.set_user(stranger)
		try:
			rows = _rows({"status": "Open"})
			self.assertEqual([r for r in rows if r["review"] == rev.name], [])
		finally:
			frappe.set_user("Administrator")
		# El owner del Project sí la ve.
		frappe.set_user(owner)
		try:
			rows = _rows({"status": "Open"})
			self.assertIn(rev.name, [r["review"] for r in rows])
		finally:
			frappe.set_user("Administrator")

	def test_governance_ignores_improvement_todo(self):
		"""Tras el Review emitido, Governance no marca el Project como pendiente por acciones de mejora."""
		p = _project("CI Gov")
		_closure(p)
		_review(p)
		flags = governance_flags(p)
		self.assertFalse(flags["needs_review"])
		self.assertFalse(flags["needs_closure"])
		# No existe ninguna señal de mejora/acciones en los flags de governance.
		self.assertNotIn("improvement", " ".join(flags.keys()).lower())

	def test_workspace_has_continuous_improvement_quick_list(self):
		ws = frappe.get_doc("Workspace", "PMO Governance")
		qls = [q for q in ws.quick_lists if q.document_type == "ToDo"]
		self.assertEqual(len(qls), 1)
		self.assertEqual(qls[0].label, "Continuous improvement actions")
		self.assertIn("PMO Post-Project Review", qls[0].quick_list_filter)
		self.assertIn("Open", qls[0].quick_list_filter)
