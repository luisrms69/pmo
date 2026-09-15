# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Change Control v2 B7 — enforcement server-side del orden de la Addenda (ADR-0015 D7).

El hook `enforce_change_control_order` solo permite o bloquea la transición de workflow de la Quotation;
no escribe nada. Se prueba como función pura con un doc STUB de Quotation (el site de tests no tiene el
esquema de proposals: `workflow_state`/`proposal_group` en Quotation) + Change Requests REALES en DB +
fingerprint mockeado (`change_control.get_addendum_delta_fingerprint`). Datos ficticios.
"""

import frappe
from frappe.exceptions import ValidationError
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo import change_control
from pmo import quotation_guard as guard
from pmo.pmo.doctype.pmo_change_request import pmo_change_request as crmod


class _Q:
	"""Stub mínimo de Quotation para el hook (name + proposal_group + transición de workflow_state)."""

	def __init__(self, name, group, old_state, new_state):
		self.name = name
		self._group = group
		self._old = old_state
		self._new = new_state

	def get(self, key):
		return {"proposal_group": self._group, "workflow_state": self._new}.get(key)

	def get_value_before_save(self, key):
		return self._old if key == "workflow_state" else None


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
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def _project(name, owner="Administrator"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Open"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner)
	return pid


def _baseline(project, revision="BL-001"):
	frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,
			"baseline_type": "Original",
			"effective_date": today(),
			"reason": "Motivo",
		}
	).insert(ignore_permissions=True).submit()


def _cr(project, group, **kw):
	return frappe.get_doc(
		{
			"doctype": "PMO Change Request",
			"project": project,
			"title": "Cambio",
			"reason": "Motivo",
			"proposal_group": group,
			**kw,
		}
	).insert(ignore_permissions=True)


class TestQuotationGuardB7(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Mocks del contrato (site de tests sin erpnext_proposals): captura al aprobar + fingerprint.
		self._orig_live = change_control.get_live_proposal_for_group
		self._orig_fp = change_control.get_addendum_delta_fingerprint
		self._orig_state = crmod._addendum_state
		# self._addn debe ser una Quotation REAL: la captura del CR al aprobar fija approved_addendum (Link
		# → Quotation). El hook en sí no lee la Quotation de la BD (solo usa doc.name para el fingerprint
		# mockeado), por eso las "otras versiones" del stub pueden ser nombres string.
		self._addn = self._quotation()
		change_control.get_live_proposal_for_group = lambda pg: self._addn
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-DEFAULT"
		crmod._addendum_state = lambda q: frappe._dict(docstatus=1, workflow_state="En Revision")

	def tearDown(self):
		change_control.get_live_proposal_for_group = self._orig_live
		change_control.get_addendum_delta_fingerprint = self._orig_fp
		crmod._addendum_state = self._orig_state
		frappe.set_user("Administrator")

	def _quotation(self):
		cust = frappe.db.exists("Customer", {"customer_name": "B7-Cust"})
		if not cust:
			c = frappe.get_doc({"doctype": "Customer", "customer_name": "B7-Cust"})
			c.flags.ignore_validate = True
			cust = c.insert(ignore_permissions=True, ignore_mandatory=True).name
		q = frappe.get_doc({"doctype": "Quotation", "quotation_to": "Customer", "party_name": cust})
		q.flags.ignore_validate = True
		return q.insert(ignore_permissions=True, ignore_mandatory=True).name

	def _approved_cr(self, name, group):
		owner = _user(name.lower().replace(" ", "-") + "@example.com")
		p = _project(name, owner=owner)
		_baseline(p)
		cr = _cr(p, group)
		prev = frappe.session.user
		frappe.set_user(owner)
		try:
			apply_workflow(cr, "Send for Review")
			apply_workflow(cr, "Approve")
		finally:
			frappe.set_user(prev)
		cr.reload()
		return cr

	# --- casos en que PMO NO interviene ------------------------------------------

	def test_quotation_without_group_ignored(self):
		guard.enforce_change_control_order(_Q("Q1", None, "En Revision", "Aprobada"))  # no lanza

	def test_quotation_without_cr_ignored(self):
		guard.enforce_change_control_order(
			_Q("Q1", "GRP-NOCR", "En Revision", "Aprobada")
		)  # no CR → no lanza

	def test_transition_not_from_review_ignored(self):
		# Aprobada→Enviada/Ganada u otras que no salen de En Revision no las gobierna PMO.
		self._approved_cr("B7 NR", "GRP-NR")
		guard.enforce_change_control_order(_Q(self._addn, "GRP-NR", "Aprobada", "Enviada al Cliente"))

	def test_no_transition_ignored(self):
		self._approved_cr("B7 NOOP", "GRP-NOOP")
		guard.enforce_change_control_order(_Q(self._addn, "GRP-NOOP", "En Revision", "En Revision"))

	# --- inconsistencia -----------------------------------------------------------

	def test_multiple_active_crs_fail_closed(self):
		p = _project("B7 DUP")
		_baseline(p)
		_cr(p, "GRP-DUP")
		_cr(p, "GRP-DUP")  # segundo CR activo con el mismo grupo
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(self._addn, "GRP-DUP", "En Revision", "Aprobada"))

	# --- reglas D7 ----------------------------------------------------------------

	def test_review_to_approved_blocked_when_cr_not_approved(self):
		p = _project("B7 DRAFT")
		_baseline(p)
		_cr(p, "GRP-DRAFT")  # CR en Draft (no Approved)
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(self._addn, "GRP-DRAFT", "En Revision", "Aprobada"))

	def test_review_to_rejected_allowed_when_cr_not_approved(self):
		p = _project("B7 REJ")
		_baseline(p)
		_cr(p, "GRP-REJ")  # CR en Draft
		# La salida limpia de rechazo siempre se permite.
		guard.enforce_change_control_order(_Q(self._addn, "GRP-REJ", "En Revision", "Rechazada"))

	def test_cr_rejected_blocks_advance_but_allows_rejection(self):
		owner = _user("b7rej2@example.com")
		p = _project("B7 CRREJ", owner=owner)
		_baseline(p)
		cr = _cr(p, "GRP-CRREJ", decision_notes="Rechazado")
		frappe.set_user(owner)
		try:
			apply_workflow(cr, "Send for Review")
			apply_workflow(cr, "Reject")
		finally:
			frappe.set_user("Administrator")
		# CR Rejected: PMO no auto-actúa; el avance a Aprobada queda bloqueado, el rechazo se permite.
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(self._addn, "GRP-CRREJ", "En Revision", "Aprobada"))
		guard.enforce_change_control_order(_Q(self._addn, "GRP-CRREJ", "En Revision", "Rechazada"))

	def test_approved_without_fingerprint_blocked(self):
		cr = self._approved_cr("B7 NOFP", "GRP-NOFP")
		frappe.db.set_value("PMO Change Request", cr.name, "approved_delta_fingerprint", "")
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(self._addn, "GRP-NOFP", "En Revision", "Aprobada"))

	def test_approved_fingerprint_mismatch_blocked(self):
		self._approved_cr("B7 MIS", "GRP-MIS")
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-OTHER"  # actual != aprobado
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(self._addn, "GRP-MIS", "En Revision", "Aprobada"))

	def test_approved_fingerprint_match_allowed(self):
		self._approved_cr("B7 OK", "GRP-OK")  # approved_delta_fingerprint = FP-DEFAULT
		guard.enforce_change_control_order(_Q(self._addn, "GRP-OK", "En Revision", "Aprobada"))  # no lanza

	def test_new_version_same_fingerprint_allowed(self):
		self._approved_cr("B7 SAMEFP", "GRP-SAMEFP")
		# Otra versión (otro name) con la MISMA huella → permitido (delta semántico, no ID técnico).
		other = "QTN-STUB-V2"
		guard.enforce_change_control_order(_Q(other, "GRP-SAMEFP", "En Revision", "Aprobada"))

	def test_new_version_different_fingerprint_blocked(self):
		self._approved_cr("B7 DIFFFP", "GRP-DIFFFP")
		other = "QTN-STUB-V2"
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-CHANGED"
		with self.assertRaises(ValidationError):
			guard.enforce_change_control_order(_Q(other, "GRP-DIFFFP", "En Revision", "Aprobada"))

	# --- el hook no modifica nada -------------------------------------------------

	def test_hook_does_not_modify_cr(self):
		cr = self._approved_cr("B7 NOMOD", "GRP-NOMOD")
		before = frappe.db.get_value("PMO Change Request", cr.name, "modified")
		guard.enforce_change_control_order(_Q(self._addn, "GRP-NOMOD", "En Revision", "Aprobada"))
		after = frappe.db.get_value("PMO Change Request", cr.name, "modified")
		self.assertEqual(before, after)  # el hook no escribió el CR
