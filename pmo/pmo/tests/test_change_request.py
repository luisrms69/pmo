# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0005 — PMO Change Request. Datos ficticios.

Bloque 2: invariantes base (defaults, `impact_summary`, moneda, integridad de baselines, aprobacion en
`before_submit`, guard de `before_cancel`) y P4.
Bloque 3: Workflow (gate de baseline al formalizar + congelado de `baseline_before`; owner-only para
aprobar/rechazar/implementar/cerrar; gates de `Implementado`/`Cerrado`; cancelacion terminal) y la accion
"Aplicar Quotation al Project" (delegacion al contrato de erpnext_proposals; ruta no-disponible real +
ruta exito mockeada).
"""

import frappe
from frappe.exceptions import ValidationError
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo import change_control
from pmo.permissions import has_permission_change_request
from pmo.pmo.doctype.pmo_change_request.pmo_change_request import (
	aplicar_quotation_al_project,
	crear_addenda,
)


def _employee(name):
	return frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "employee_name": name, "first_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


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


def _project(name, owner="Administrator", members=(), company=None):
	pid = frappe.db.exists("Project", {"project_name": name})
	if not pid:
		pid = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": name,
					"expected_start_date": "2026-01-01",
					"expected_end_date": "2026-03-31",
					"status": "Open",
					"company": company,
				}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
	frappe.db.set_value("Project", pid, "owner", owner)
	# Membresía derivada: un "member" = DocShare(read+write) del Project (ADR-0002 revisado).
	for m in members:
		frappe.share.add("Project", pid, m, read=1, write=1, notify=0)
	return pid


def _baseline(
	project, revision, btype="Original", supersedes=None, effective=None, reason="Motivo", change_request=None
):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,
			"baseline_type": btype,
			"supersedes_baseline": supersedes,
			"effective_date": effective or today(),
			"reason": reason,
			"change_request": change_request,
		}
	).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _cr(project, title="Cambio", reason="Motivo", **kw):
	return frappe.get_doc(
		{
			"doctype": "PMO Change Request",
			"project": project,
			"title": title,
			"reason": reason,
			**kw,
		}
	).insert(ignore_permissions=True)


def _company():
	return frappe.db.get_value("Company", {}, "name")


class TestChangeRequest(IntegrationTestCase):
	def _run(self, doc, action, user):
		prev = frappe.session.user
		frappe.set_user(user)
		try:
			apply_workflow(doc, action)
		finally:
			frappe.set_user(prev)
		doc.reload()

	# --- comportamiento base (Bloque 2) ------------------------------------------

	def test_defaults_and_impact_summary(self):
		p = _project("CR-P1")
		cr = _cr(p, impacts_scope=1, impacts_commercial=1)
		self.assertTrue(cr.raised_by)
		self.assertEqual(str(cr.request_date), today())
		self.assertEqual(cr.priority, "Medium")
		self.assertEqual(cr.impact_summary, "Scope, Commercial")
		self.assertEqual(cr.workflow_state, "Draft")  # estado inicial del Workflow

	def test_currency_default_from_company(self):
		company = _company()
		expected = frappe.db.get_value("Company", company, "default_currency")
		p = _project("CR-P2", company=company)
		cr = _cr(p)
		self.assertEqual(cr.currency, expected)

	def test_baseline_before_must_match_project(self):
		p1 = _project("CR-P3")
		p2 = _project("CR-P3B")
		other_bl = _baseline(p2, "BL-001")
		with self.assertRaises(ValidationError):
			_cr(p1, baseline_before=other_bl.name)

	def test_baseline_after_effective_order(self):
		p = _project("CR-P4")
		b1 = _baseline(p, "BL-001", effective="2026-01-01")
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-02-01")
		with self.assertRaises(ValidationError):
			_cr(p, baseline_before=b2.name, baseline_after=b1.name)

	def test_before_submit_sets_approval(self):
		p = _project("CR-P5")
		_baseline(p, "BL-001")  # sin baseline vigente no se puede aprobar
		cr = _cr(p)
		cr.submit()  # ruta directa: aterriza en 'Aprobado' (primer doc_status=1)
		cr.reload()
		self.assertEqual(cr.docstatus, 1)
		self.assertTrue(cr.approved_by and cr.approved_at)
		self.assertTrue(cr.baseline_before)  # red de seguridad del gate

	def test_submit_blocked_without_baseline(self):
		p = _project("CR-P5B")  # sin baseline vigente
		cr = _cr(p)
		with self.assertRaises(ValidationError):
			cr.submit()

	def test_before_cancel_blocked_when_applied(self):
		p = _project("CR-P6")
		_baseline(p, "BL-001")
		cr = _cr(p)
		cr.submit()
		frappe.db.set_value("PMO Change Request", cr.name, "applied_to_project", 1)
		cr.reload()
		with self.assertRaises(ValidationError):
			cr.cancel()

	# --- P4 (Bloque 2) -----------------------------------------------------------

	def test_permissions_read_write_submit(self):
		owner = _user("cr-owner@example.com")
		member = _user("cr-member@example.com")
		other = _user("cr-other@example.com")
		execu = _user("cr-exec@example.com", ["PMO Executive Access"])
		p = _project("CR-P7", owner=owner, members=[member])
		cr = _cr(p)

		self.assertTrue(has_permission_change_request(cr, "read", owner))
		self.assertTrue(has_permission_change_request(cr, "read", member))
		self.assertTrue(has_permission_change_request(cr, "read", execu))
		self.assertFalse(has_permission_change_request(cr, "read", other))

		self.assertTrue(has_permission_change_request(cr, "write", owner))
		self.assertTrue(has_permission_change_request(cr, "write", member))
		self.assertFalse(has_permission_change_request(cr, "write", other))
		self.assertFalse(has_permission_change_request(cr, "write", execu))

		self.assertTrue(has_permission_change_request(cr, "submit", owner))
		self.assertFalse(has_permission_change_request(cr, "submit", member))
		self.assertFalse(has_permission_change_request(cr, "submit", execu))
		self.assertFalse(has_permission_change_request(cr, "cancel", member))
		self.assertFalse(has_permission_change_request(cr, "share", owner))

	def test_change_register_list_p4(self):
		"""El Change Register es un Report Builder sobre la lista del CR → depende de
		`permission_query_conditions`. Se valida que el listado filtra por visibilidad del Project."""
		owner_a = _user("cr-reg-a@example.com", ["Projects User"])
		owner_b = _user("cr-reg-b@example.com", ["Projects User"])
		execu = _user("cr-reg-exec@example.com", ["PMO Executive Access"])
		pa = _project("CR-REG-A", owner=owner_a)
		pb = _project("CR-REG-B", owner=owner_b)
		cra = _cr(pa, title="A change")
		crb = _cr(pb, title="B change")
		scope = {"project": ["in", [pa, pb]]}

		frappe.set_user(owner_a)
		try:
			names = frappe.get_list("PMO Change Request", filters=scope, pluck="name")
		finally:
			frappe.set_user("Administrator")
		self.assertIn(cra.name, names)
		self.assertNotIn(crb.name, names)  # no ve el CR de otro Project

		frappe.set_user(execu)
		try:
			names_e = frappe.get_list("PMO Change Request", filters=scope, pluck="name")
		finally:
			frappe.set_user("Administrator")
		self.assertIn(cra.name, names_e)
		self.assertIn(crb.name, names_e)  # lector global ve ambos

	def test_member_write_denied_after_submit(self):
		owner = _user("cr-owner2@example.com")
		member = _user("cr-member2@example.com")
		p = _project("CR-P8", owner=owner, members=[member])
		_baseline(p, "BL-001")
		cr = _cr(p)
		cr.submit()
		cr.reload()
		self.assertFalse(has_permission_change_request(cr, "write", member))
		self.assertTrue(has_permission_change_request(cr, "write", owner))

	# --- Workflow (Bloque 3) -----------------------------------------------------

	def test_workflow_happy_path_owner(self):
		owner = _user("cr-wf1@example.com", ["Projects User"])
		p = _project("CR-WF1", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p)
		self._run(cr, "Send for Review", owner)
		self.assertEqual(cr.workflow_state, "In Review")
		self.assertTrue(cr.baseline_before)  # congelada al formalizar
		self._run(cr, "Approve", owner)
		self.assertEqual(cr.workflow_state, "Approved")
		self.assertEqual(cr.docstatus, 1)
		self.assertTrue(cr.approved_by)

	def test_review_gate_requires_baseline(self):
		owner = _user("cr-wf2@example.com", ["Projects User"])
		p = _project("CR-WF2", owner=owner)  # sin baseline
		cr = _cr(p)
		with self.assertRaises(ValidationError):
			self._run(cr, "Send for Review", owner)

	def test_member_cannot_approve(self):
		owner = _user("cr-wf3-o@example.com", ["Projects User"])
		member = _user("cr-wf3-m@example.com", ["Projects User"])
		p = _project("CR-WF3", owner=owner, members=[member])
		_baseline(p, "BL-001")
		cr = _cr(p)
		self._run(cr, "Send for Review", member)  # member SI puede formalizar
		self.assertEqual(cr.workflow_state, "In Review")
		frappe.set_user(member)
		try:
			with self.assertRaises(Exception):
				apply_workflow(cr, "Approve")  # condicion owner-only -> no es accion valida para member
		finally:
			frappe.set_user("Administrator")

	def _assert_action_raises(self, doc, action, user):
		"""apply_workflow que debe lanzar; recarga el doc después para limpiar el estado en memoria que
		apply_workflow dejó seteado antes del throw (evita TimestampMismatch en pasos siguientes)."""
		prev = frappe.session.user
		frappe.set_user(user)
		try:
			with self.assertRaises(ValidationError):
				apply_workflow(doc, action)
		finally:
			frappe.set_user(prev)
		doc.reload()

	def test_implemented_gate_and_close_gate(self):
		owner = _user("cr-wf4@example.com", ["Projects User"])
		emp = _employee("Impl Owner WF4")
		p = _project("CR-WF4", owner=owner)
		_baseline(p, "BL-001", effective="2026-01-01")
		# comercial + responsable de implementación definido
		cr = _cr(p, proposal_group="GRP-1", implementation_owner=emp)
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		# Marcar implementado sin aplicar la Quotation -> bloqueado (impacto comercial)
		self._assert_action_raises(cr, "Mark Implemented", owner)
		frappe.db.set_value("PMO Change Request", cr.name, "applied_to_project", 1)
		cr.reload()
		self._run(cr, "Mark Implemented", owner)
		self.assertEqual(cr.workflow_state, "Implemented")
		# Cerrar sin baseline_after -> bloqueado
		self._assert_action_raises(cr, "Close", owner)
		# baseline_after se fija automáticamente por una Baseline Approved Change que referencia este CR
		b2 = _baseline(p, "BL-002", btype="Approved Change", change_request=cr.name, effective="2026-02-01")
		cr.reload()
		self.assertEqual(cr.baseline_after, b2.name)  # fijada por el sistema, no manual
		# Cerrar sin stakeholder_communication -> bloqueado
		self._assert_action_raises(cr, "Close", owner)
		frappe.set_user(owner)
		try:
			cr.stakeholder_communication = "Correo enviado a interesados"
			cr.save()
			apply_workflow(cr, "Close")
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertEqual(cr.workflow_state, "Closed")

	def test_implemented_ok_without_proposal(self):
		owner = _user("cr-wf5@example.com", ["Projects User"])
		emp = _employee("Impl Owner WF5")
		p = _project("CR-WF5", owner=owner)
		_baseline(p, "BL-001")
		# sin proposal_group -> solo-cronograma; exige responsable + aceptación del cliente documentada
		cr = _cr(
			p,
			implementation_owner=emp,
			customer_approval_status="Not Required",
			customer_approval_notes="Cambio interno sin impacto al cliente",
		)
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		self._run(cr, "Mark Implemented", owner)
		self.assertEqual(cr.workflow_state, "Implemented")

	def test_rejected_requires_decision_notes(self):
		owner = _user("cr-rej@example.com", ["Projects User"])
		p = _project("CR-REJ", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p)
		self._run(cr, "Send for Review", owner)
		self._assert_action_raises(cr, "Reject", owner)  # sin decision_notes -> bloqueado
		frappe.set_user(owner)
		try:
			cr.decision_notes = "Rechazado por costo/beneficio"
			cr.save()
			apply_workflow(cr, "Reject")
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertEqual(cr.workflow_state, "Rejected")

	def test_implementation_owner_required_before_implemented(self):
		owner = _user("cr-io@example.com", ["Projects User"])
		p = _project("CR-IO", owner=owner)  # sin pmo_operational_owner -> impl owner vacío
		_baseline(p, "BL-001")
		cr = _cr(
			p,
			customer_approval_status="Not Required",
			customer_approval_notes="n/a",
		)
		self.assertFalse(cr.implementation_owner)
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		self._assert_action_raises(cr, "Mark Implemented", owner)  # falta implementation_owner

	def test_noncommercial_pending_blocks_implemented(self):
		owner = _user("cr-pend@example.com", ["Projects User"])
		emp = _employee("Impl Owner PEND")
		p = _project("CR-PEND", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, implementation_owner=emp)  # customer_approval_status default = Pending
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		self._assert_action_raises(cr, "Mark Implemented", owner)  # Pending bloquea

	def test_customer_approval_approved_requires_contact_and_date(self):
		p = _project("CR-CAA")
		with self.assertRaises(ValidationError):  # validación server-side de aceptación del cliente
			_cr(p, customer_approval_status="Approved")  # sin Contact ni fecha

	def test_not_required_requires_justification(self):
		p = _project("CR-CANR")
		with self.assertRaises(ValidationError):
			_cr(p, customer_approval_status="Not Required")  # sin notas de justificación

	def test_baseline_after_is_read_only(self):
		# El usuario no relaciona manualmente CR y Baseline: baseline_after es read-only (lo fija la Baseline).
		self.assertTrue(frappe.get_meta("PMO Change Request").get_field("baseline_after").read_only)

	def test_cancel_blocked_on_terminal_state(self):
		owner = _user("cr-wf6@example.com", ["Projects User"])
		p = _project("CR-WF6", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, decision_notes="Rechazado")  # Reject exige decision_notes
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Reject", owner)
		self.assertEqual(cr.workflow_state, "Rejected")
		frappe.set_user(owner)
		try:
			with self.assertRaises(ValidationError):
				cr.cancel()  # estado terminal
		finally:
			frappe.set_user("Administrator")

	# --- Crear addenda comercial (delegación a erpnext_proposals) ----------------

	def test_create_addendum_delegator_unavailable(self):
		# erpnext_proposals no instalado en test-pmo.localhost -> el contrato no resuelve -> error claro
		with self.assertRaises(ValidationError):
			change_control.create_addendum_quotation("QTN-INEXISTENTE")

	def test_crear_addenda_requires_editable(self):
		p = _project("CR-ADD-E")
		_baseline(p, "BL-001")
		cr = _cr(p)
		cr.submit()  # docstatus 1 -> ya no editable
		with self.assertRaises(ValidationError):
			crear_addenda(cr.name)

	def test_crear_addenda_blocks_if_group_set(self):
		p = _project("CR-ADD-G")
		cr = _cr(p, proposal_group="GRP-YA")  # ya tiene addenda
		with self.assertRaises(ValidationError):
			crear_addenda(cr.name)

	# --- Accion "Aplicar Quotation al Project" (Bloque 3) ------------------------

	def _approved_cr(self, name, owner_email):
		owner = _user(owner_email, ["Projects User"])
		p = _project(name, owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-X")
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		return owner, p, cr

	def test_apply_action_integration_unavailable(self):
		owner, _p, cr = self._approved_cr("CR-APP1", "cr-app1@example.com")
		# erpnext_proposals no instalado en test-pmo.localhost -> el contrato no resuelve -> throw claro
		frappe.set_user(owner)
		try:
			with self.assertRaises(ValidationError):
				aplicar_quotation_al_project(cr.name, "QTN-FAKE")
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertFalse(cr.applied_to_project)  # no se marca aplicado si el contrato falla

	def test_apply_action_success_mocked(self):
		owner, _p, cr = self._approved_cr("CR-APP2", "cr-app2@example.com")
		q = self._quotation()
		orig = change_control.apply_addendum_to_project
		change_control.apply_addendum_to_project = lambda quotation, project: {
			"project": project,
			"tasks_created": 3,
		}
		try:
			frappe.set_user(owner)
			try:
				res = aplicar_quotation_al_project(cr.name, q)
			finally:
				frappe.set_user("Administrator")
		finally:
			change_control.apply_addendum_to_project = orig
		cr.reload()
		self.assertTrue(cr.applied_to_project)
		self.assertEqual(cr.applied_quotation, q)
		self.assertEqual(cr.workflow_state, "Approved")  # la accion NO mueve el Workflow
		self.assertEqual(res["tasks_created"], 3)

	def _quotation(self):
		"""Quotation mínima solo para satisfacer el link `applied_quotation`. El site de tests no tiene
		Company ni Fiscal Year, así que se salta la validación de ERPNext (`ignore_validate`): el registro
		solo necesita existir."""
		cust_name = "CR-Test-Cust"
		cust = frappe.db.exists("Customer", {"customer_name": cust_name})
		if not cust:
			c = frappe.get_doc({"doctype": "Customer", "customer_name": cust_name})
			c.flags.ignore_validate = True
			cust = c.insert(ignore_permissions=True, ignore_mandatory=True).name
		q = frappe.get_doc({"doctype": "Quotation", "quotation_to": "Customer", "party_name": cust})
		q.flags.ignore_validate = True
		return q.insert(ignore_permissions=True, ignore_mandatory=True).name
