# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D9 — señales de gobierno (governance_flags) + sección Project Governance del Dashboard.

Datos ficticios. Cubre: semántica canónica de needs_closure ({Completed, Cancelled} sin Closure),
has_handoff/needs_review/open_change_requests, y que el bloque del Dashboard consume esas señales (P4).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo.dashboard import _governance_actions, governance_block
from pmo.governance import governance_flags


def _project(name, status="Open", owner="Administrator"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": status})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "status", status, update_modified=False)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	return pid


def _baseline(project):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"baseline_type": "Original",
			"effective_date": today(),
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _open_cr(project, title="Cambio"):
	# docstatus 0 -> workflow_state Draft (estado abierto canónico).
	return frappe.get_doc(
		{"doctype": "PMO Change Request", "project": project, "title": title, "reason": "Motivo"}
	).insert(ignore_permissions=True)


def _actions(project):
	return _governance_actions(governance_flags(project))


def _block_item(project):
	frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
	return next((it for it in governance_block()["governance"]["items"] if it["project"] == project), None)


def _handoff(project):
	# El Handoff exige responsable operativo interno + contacto del cliente en el Project para emitirse.
	emp = frappe.db.exists("Employee", {"employee_name": "GD Op Owner"}) or (
		frappe.get_doc({"doctype": "Employee", "employee_name": "GD Op Owner", "first_name": "GD"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	ct = frappe.db.exists("Contact", {"first_name": "GD Contact"}) or (
		frappe.get_doc({"doctype": "Contact", "first_name": "GD Contact"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", project, "pmo_operational_owner", emp, update_modified=False)
	frappe.db.set_value("Project", project, "pmo_customer_contact", ct, update_modified=False)
	d = frappe.get_doc(
		{"doctype": "PMO Project Handoff", "project": project, "handoff_summary": "Transferencia X"}
	)
	d.insert(ignore_permissions=True)
	d.submit()
	return d


def _closure(project):
	d = frappe.get_doc(
		{
			"doctype": "PMO Project Closure",
			"project": project,
			"closure_date": "2026-03-31",
			"final_result": "ok",
		}
	)
	d.insert(ignore_permissions=True)
	d.submit()
	return d


class TestGovernanceDashboard(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_needs_closure_includes_cancelled(self):
		# Semántica canónica: terminal (Completed O Cancelled) sin Closure → needs_closure.
		pc = _project("GD Completed", status="Completed")
		self.assertTrue(governance_flags(pc)["needs_closure"])
		px = _project("GD Cancelled", status="Cancelled")
		self.assertTrue(governance_flags(px)["needs_closure"])
		po = _project("GD Open", status="Open")
		self.assertFalse(governance_flags(po)["needs_closure"])  # no terminal

	def test_needs_closure_false_after_closure(self):
		p = _project("GD Closed", status="Completed")
		_closure(p)
		f = governance_flags(p)
		self.assertFalse(f["needs_closure"])
		self.assertTrue(f["needs_review"])  # cerrado sin Review

	def test_has_handoff_signal(self):
		p = _project("GD Handoff")
		self.assertFalse(governance_flags(p)["has_handoff"])
		_handoff(p)
		self.assertTrue(governance_flags(p)["has_handoff"])

	def test_open_change_request_only_appears_in_items(self):
		from pmo.dashboard import governance_block

		p = _project("GD CROnly", status="Open")  # no terminal, con Handoff → único pendiente = CR abierto
		_handoff(p)
		cr = frappe.get_doc(
			{
				"doctype": "PMO Change Request",
				"project": p,
				"title": "Scope change",
				"reason": "Client request",
			}
		)
		cr.insert(ignore_permissions=True)  # docstatus 0 → workflow_state Draft (abierto)
		f = governance_flags(p)
		self.assertEqual(f["open_change_requests"], 1)
		self.assertFalse(f["needs_closure"])
		self.assertFalse(f["needs_review"])
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		items = governance_block()["governance"]["items"]
		self.assertTrue(any(it["project"] == p for it in items))  # aparece por CR abierto

	def test_portfolio_row_exposes_governance_flags(self):
		from pmo.pmo.report.pmo_portfolio.pmo_portfolio import execute

		_project("GD PortFlags", status="Open")
		_cols, rows, *_ = execute({})
		self.assertTrue(rows)
		for r in rows:
			self.assertIn("has_handoff", r)
			self.assertIn("needs_closure", r)
			self.assertIn("open_change_requests", r)

	def test_dashboard_governance_block_consumes_signals(self):
		from pmo.dashboard import governance_block

		p = _project("GD Dash", status="Completed")  # terminal sin Closure → aparece en la sección
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		gov = governance_block()["governance"]
		self.assertIn("counts", gov)
		self.assertIn("items", gov)
		self.assertGreaterEqual(gov["counts"]["needs_closure"], 1)
		self.assertTrue(any(it["project"] == p for it in gov["items"]))


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


class TestPendingGovernanceActions(IntegrationTestCase):
	"""Punto 2: Pending Governance Actions como lista de trabajo (acciones humanas, sin claves internas)."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_action_crear_handoff(self):
		p = _project("PGA Handoff")  # sin Handoff
		acts = _actions(p)
		self.assertIn("Crear Handoff", acts)
		self.assertNotIn("Crear línea base inicial", acts)  # no baseline si falta Handoff

	def test_action_crear_baseline_after_handoff(self):
		p = _project("PGA Baseline")
		_handoff(p)
		f = governance_flags(p)
		self.assertTrue(f["needs_baseline"])
		acts = _actions(p)
		self.assertIn("Crear línea base inicial", acts)
		self.assertNotIn("Crear Handoff", acts)

	def test_no_baseline_action_when_baseline_exists(self):
		p = _project("PGA HasBaseline")
		_handoff(p)
		_baseline(p)
		f = governance_flags(p)
		self.assertFalse(f["needs_baseline"])
		self.assertNotIn("Crear línea base inicial", _actions(p))

	def test_change_request_action_count_and_plural(self):
		p = _project("PGA CR")
		_handoff(p)
		_baseline(p)
		_open_cr(p, "CR1")
		self.assertIn("Atender 1 solicitud de cambio", _actions(p))
		_open_cr(p, "CR2")
		self.assertEqual(governance_flags(p)["open_change_requests"], 2)
		self.assertIn("Atender 2 solicitudes de cambio", _actions(p))

	def test_terminal_without_closure_action(self):
		p = _project("PGA Closure", status="Completed")
		_handoff(p)
		self.assertTrue(governance_flags(p)["needs_closure"])
		self.assertIn("Emitir cierre", _actions(p))

	def test_closure_without_review_action(self):
		p = _project("PGA Review", status="Completed")
		_handoff(p)
		_closure(p)
		f = governance_flags(p)
		self.assertFalse(f["needs_closure"])
		self.assertTrue(f["needs_review"])
		self.assertIn("Realizar revisión post-proyecto", _actions(p))

	def test_indicators_match_rows(self):
		# El indicador superior refleja la fila: un Project sin Handoff cuenta en without_handoff y su fila
		# muestra exactamente "Crear Handoff".
		p = _project("PGA Match")
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		gov = governance_block()["governance"]
		self.assertGreaterEqual(gov["counts"]["without_handoff"], 1)
		item = next((it for it in gov["items"] if it["project"] == p), None)
		self.assertIsNotNone(item)
		self.assertEqual(item["actions"], ["Crear Handoff"])

	def test_no_lifecycle_keys_exposed(self):
		p = _project("PGA NoLifecycle")
		_handoff(p)
		item = _block_item(p)
		self.assertIsNotNone(item)
		# La fila solo comunica acciones; sin claves internas de lifecycle ni señales crudas.
		for k in ("lifecycle", "status", "has_handoff", "needs_baseline", "needs_closure", "needs_review"):
			self.assertNotIn(k, item)
		import json

		blob = json.dumps(governance_block()["governance"])
		for internal in ("initiation", "planning", "execution_control", "lifecycle"):
			self.assertNotIn(internal, blob)

	def test_risk_is_only_ux_reserve(self):
		# Reserva de UX: sin señal, sin conteo, sin pendiente. governance_flags no expone nada de riesgo.
		p = _project("PGA Risk")
		f = governance_flags(p)
		self.assertNotIn("needs_risk", f)
		frappe.cache().delete_value(f"pmo:dashboard:{frappe.session.user}")
		counts = governance_block()["governance"]["counts"]
		self.assertNotIn("needs_risk", counts)
		self.assertFalse(any("risk" in k for k in counts))

	def test_p4_only_visible_projects(self):
		owner = _user("pga-owner@example.com")
		stranger = _user("pga-stranger@example.com")
		p = _project("PGA P4", owner=owner)
		_handoff(p)  # tiene acción pendiente
		frappe.set_user(stranger)
		try:
			item = _block_item(p)  # el extraño no ve el Project del owner
		finally:
			frappe.set_user("Administrator")
		self.assertIsNone(item)
