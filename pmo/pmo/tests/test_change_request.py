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

import inspect

import frappe
from frappe.exceptions import ValidationError
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo import change_control
from pmo.permissions import has_permission_change_request
from pmo.pmo.doctype.pmo_change_request import pmo_change_request as crmod
from pmo.pmo.doctype.pmo_change_request.pmo_change_request import (
	apply_addendum,
	crear_addenda,
	reapprove_addendum_version,
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


def _addendum_quotation():
	"""Quotation mínima (registro real) para satisfacer el Link `approved_addendum`. El site de tests no
	tiene Company/Fiscal Year ni el esquema de proposals, así que se salta la validación (`ignore_validate`):
	solo necesita EXISTIR con un nombre real; su estado se controla mockeando `_addendum_state`."""
	cust = frappe.db.exists("Customer", {"customer_name": "CR-B5-Cust"})
	if not cust:
		c = frappe.get_doc({"doctype": "Customer", "customer_name": "CR-B5-Cust"})
		c.flags.ignore_validate = True
		cust = c.insert(ignore_permissions=True, ignore_mandatory=True).name
	q = frappe.get_doc({"doctype": "Quotation", "quotation_to": "Customer", "party_name": cust})
	q.flags.ignore_validate = True
	return q.insert(ignore_permissions=True, ignore_mandatory=True).name


class TestChangeRequest(IntegrationTestCase):
	def setUp(self):
		# B5: el site de tests no tiene erpnext_proposals ni el esquema de Quotation (workflow_state /
		# proposal_group). Se mockean los seams de contrato para que la CAPTURA al aprobar tenga éxito por
		# defecto (versión viva `En Revision` + fingerprint). Los tests de fallo sobreescriben estos mocks.
		frappe.set_user("Administrator")
		self._addn = _addendum_quotation()  # Quotation real para el Link approved_addendum
		self._orig_live = change_control.get_live_proposal_for_group
		self._orig_fp = change_control.get_addendum_delta_fingerprint
		self._orig_state = crmod._addendum_state
		self._orig_apply = change_control.apply_addendum_to_project
		change_control.get_live_proposal_for_group = lambda pg: self._addn
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-DEFAULT"
		crmod._addendum_state = lambda q: frappe._dict(docstatus=1, workflow_state="En Revision")

	def tearDown(self):
		change_control.get_live_proposal_for_group = self._orig_live
		change_control.get_addendum_delta_fingerprint = self._orig_fp
		crmod._addendum_state = self._orig_state
		change_control.apply_addendum_to_project = self._orig_apply
		frappe.set_user("Administrator")

	def _won(self):
		"""Cambia el estado mockeado de la Addenda a `Ganada` (para probar el apply de B6)."""
		crmod._addendum_state = lambda q: frappe._dict(docstatus=1, workflow_state="Ganada")

	def _spy_apply(self, result):
		"""Instala un espía sobre la primitive de apply; devuelve la lista de llamadas (q, project)."""
		calls = []

		def _fake(quotation, project):
			calls.append((quotation, project))
			return dict(result)

		change_control.apply_addendum_to_project = _fake
		return calls

	def _do_valid_apply(self, cr, tasks_created=1):
		"""Aplica realmente la Addenda (B6) sobre un CR Approved: fija applied_to_project + applied_quotation
		vía el flujo real (no un atajo por DB). Requiere el estado mockeado en `Ganada`."""
		self._won()
		self._spy_apply({"tasks_created": tasks_created})
		apply_addendum(cr.name)
		cr.reload()

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
		cr = _cr(p, proposal_group="GRP-1")  # flujo único: Addenda requerida también en submit directo
		cr.submit()  # ruta directa: aterriza en 'Aprobado' (primer doc_status=1)
		cr.reload()
		self.assertEqual(cr.docstatus, 1)
		self.assertTrue(cr.approved_by and cr.approved_at)
		self.assertTrue(cr.baseline_before)  # red de seguridad del gate

	def test_direct_submit_blocked_without_addendum(self):
		"""Flujo único (B4): un submit() directo (sin pasar por In Review) tampoco aprueba sin Addenda."""
		p = _project("CR-P5C")
		_baseline(p, "BL-001")  # baseline OK, pero sin proposal_group
		cr = _cr(p)
		with self.assertRaises(ValidationError):
			cr.submit()

	def test_direct_submit_allowed_with_addendum_and_baseline(self):
		"""Con Addenda + baseline, el submit directo sigue permitido (comportamiento actual)."""
		p = _project("CR-P5D")
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		cr.submit()
		cr.reload()
		self.assertEqual(cr.docstatus, 1)

	def test_submit_blocked_without_baseline(self):
		p = _project("CR-P5B")  # sin baseline vigente
		cr = _cr(p)
		with self.assertRaises(ValidationError):
			cr.submit()

	def test_before_cancel_blocked_when_applied(self):
		p = _project("CR-P6")
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
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
		cr = _cr(p, proposal_group="GRP-1")
		cr.submit()
		cr.reload()
		self.assertFalse(has_permission_change_request(cr, "write", member))
		self.assertTrue(has_permission_change_request(cr, "write", owner))

	# --- Workflow (Bloque 3) -----------------------------------------------------

	def test_workflow_happy_path_owner(self):
		owner = _user("cr-wf1@example.com", ["Projects User"])
		p = _project("CR-WF1", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")  # flujo único: la Addenda ya existe antes de formalizar
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
		cr = _cr(p, proposal_group="GRP-1")  # con Addenda: aísla el gate de baseline
		with self.assertRaises(ValidationError):
			self._run(cr, "Send for Review", owner)

	def test_review_gate_requires_addendum(self):
		"""Flujo único (B4): sin Addenda (`proposal_group`) no se puede pasar a In Review, aunque haya baseline."""
		owner = _user("cr-wf2b@example.com", ["Projects User"])
		p = _project("CR-WF2B", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p)  # sin proposal_group
		with self.assertRaises(ValidationError):
			self._run(cr, "Send for Review", owner)

	def test_member_cannot_approve(self):
		owner = _user("cr-wf3-o@example.com", ["Projects User"])
		member = _user("cr-wf3-m@example.com", ["Projects User"])
		p = _project("CR-WF3", owner=owner, members=[member])
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
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
		# Marcar implementado sin aplicar la Addenda -> bloqueado (flujo único, B4/B8)
		self._assert_action_raises(cr, "Mark Implemented", owner)
		# Apply válido de B6 (fija applied_to_project + applied_quotation por el flujo real, no por DB).
		self._do_valid_apply(cr)
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

	def test_rejected_requires_decision_notes(self):
		owner = _user("cr-rej@example.com", ["Projects User"])
		p = _project("CR-REJ", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
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
		cr = _cr(p, proposal_group="GRP-1")  # con Addenda, pero sin implementation_owner
		self.assertFalse(cr.implementation_owner)
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		self._assert_action_raises(cr, "Mark Implemented", owner)  # falta implementation_owner

	def test_proposal_group_is_read_only(self):
		# Flujo único (B4): el usuario no fija proposal_group manualmente; lo pone el sistema al crear la Addenda.
		self.assertTrue(frappe.get_meta("PMO Change Request").get_field("proposal_group").read_only)

	def test_customer_approval_fields_removed(self):
		# B4: el modelo heredado de aceptación del cliente ya no existe.
		meta = frappe.get_meta("PMO Change Request")
		for fn in (
			"customer_approval_status",
			"customer_approved_by",
			"customer_approved_on",
			"customer_approval_notes",
		):
			self.assertIsNone(meta.get_field(fn))

	def test_baseline_after_is_read_only(self):
		# El usuario no relaciona manualmente CR y Baseline: baseline_after es read-only (lo fija la Baseline).
		self.assertTrue(frappe.get_meta("PMO Change Request").get_field("baseline_after").read_only)

	def test_cancel_blocked_on_terminal_state(self):
		owner = _user("cr-wf6@example.com", ["Projects User"])
		p = _project("CR-WF6", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1", decision_notes="Rechazado")  # Reject exige decision_notes
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
		cr = _cr(p, proposal_group="GRP-1")  # Addenda requerida para poder someter
		cr.submit()  # docstatus 1 -> ya no editable
		with self.assertRaises(ValidationError):
			crear_addenda(cr.name)

	def test_crear_addenda_blocks_if_group_set(self):
		p = _project("CR-ADD-G")
		cr = _cr(p, proposal_group="GRP-YA")  # ya tiene addenda
		with self.assertRaises(ValidationError):
			crear_addenda(cr.name)

	# NOTA (B4): los tests de la acción "Aplicar Quotation al Project" (con Quotation manual) se eliminaron
	# junto con esa acción. El apply automático y gobernado se prueba en B6.

	# --- B5: aprobación gobernada + fingerprint + re-aprobación -------------------

	def _approved(self, name, implementation_owner=None):
		owner = _user(name.lower() + "@example.com", ["Projects User"])
		p = _project(name, owner=owner)
		_baseline(p, "BL-001")
		kw = {"proposal_group": "GRP-1"}
		if implementation_owner:
			kw["implementation_owner"] = implementation_owner
		cr = _cr(p, **kw)
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		return owner, cr

	def test_approve_captures_addendum_and_fingerprint(self):
		_owner, cr = self._approved("CR-B5A")
		self.assertEqual(cr.workflow_state, "Approved")
		self.assertEqual(cr.approved_addendum, self._addn)
		self.assertEqual(cr.approved_delta_fingerprint, "FP-DEFAULT")

	def test_reject_does_not_capture(self):
		owner = _user("cr-b5rej@example.com", ["Projects User"])
		p = _project("CR-B5REJ", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1", decision_notes="Rechazado por costo")
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Reject", owner)
		self.assertEqual(cr.workflow_state, "Rejected")
		self.assertFalse(cr.approved_addendum)
		self.assertFalse(cr.approved_delta_fingerprint)
		self.assertFalse(cr.approved_by)  # rechazar no es aprobar
		self.assertFalse(cr.approved_at)

	def test_approve_blocked_without_live_addendum(self):
		owner = _user("cr-b5nolive@example.com", ["Projects User"])
		p = _project("CR-B5NOLIVE", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		self._run(cr, "Send for Review", owner)
		change_control.get_live_proposal_for_group = lambda pg: None  # no hay versión viva
		self._assert_action_raises(cr, "Approve", owner)
		self.assertEqual(cr.docstatus, 0)  # aprobación fail-closed: no quedó submitted

	def test_approve_blocked_with_draft_addendum(self):
		owner = _user("cr-b5draft@example.com", ["Projects User"])
		p = _project("CR-B5DRAFT", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		self._run(cr, "Send for Review", owner)
		crmod._addendum_state = lambda q: frappe._dict(docstatus=0, workflow_state="Borrador")
		self._assert_action_raises(cr, "Approve", owner)
		self.assertEqual(cr.docstatus, 0)

	def test_approve_blocked_on_fingerprint_error(self):
		owner = _user("cr-b5fp@example.com", ["Projects User"])
		p = _project("CR-B5FP", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		self._run(cr, "Send for Review", owner)

		def _boom(q):
			frappe.throw(frappe._("fingerprint failed"))

		change_control.get_addendum_delta_fingerprint = _boom
		self._assert_action_raises(cr, "Approve", owner)
		self.assertEqual(cr.docstatus, 0)

	def test_reapprove_only_when_approved(self):
		owner = _user("cr-b5ra1@example.com", ["Projects User"])
		p = _project("CR-B5RA1", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		self._run(cr, "Send for Review", owner)  # In Review (docstatus 0)
		frappe.set_user(owner)
		try:
			with self.assertRaises(ValidationError):
				reapprove_addendum_version(cr.name)
		finally:
			frappe.set_user("Administrator")

	def test_reapprove_owner_only(self):
		stranger = _user("cr-b5ra2-s@example.com", ["Projects User"])
		_owner, cr = self._approved("CR-B5RA2")  # el owner del project lo crea _approved
		frappe.set_user(stranger)
		try:
			with self.assertRaises(frappe.PermissionError):
				reapprove_addendum_version(cr.name)
		finally:
			frappe.set_user("Administrator")

	def test_reapprove_updates_fingerprint_without_side_effects(self):
		owner = _user("cr-b5ra3@example.com", ["Projects User"])
		p = _project("CR-B5RA3", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p, proposal_group="GRP-1")
		self._run(cr, "Send for Review", owner)
		self._run(cr, "Approve", owner)
		self.assertEqual(cr.approved_delta_fingerprint, "FP-DEFAULT")
		approved_by, approved_at = cr.approved_by, cr.approved_at
		# nueva versión divergente En Revisión (otra Quotation real)
		addn_v2 = _addendum_quotation()
		change_control.get_live_proposal_for_group = lambda pg: addn_v2
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-V2"
		frappe.set_user(owner)
		try:
			reapprove_addendum_version(cr.name)
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertEqual(cr.approved_addendum, addn_v2)
		self.assertEqual(cr.approved_delta_fingerprint, "FP-V2")
		self.assertEqual(cr.workflow_state, "Approved")  # no cambia el workflow
		self.assertEqual(cr.approved_by, approved_by)  # no cambia la aprobación original
		self.assertEqual(cr.approved_at, approved_at)
		self.assertFalse(cr.applied_to_project)  # no toca applied_*

	# --- B6: apply gobernado (Addenda Ganada + guard de fingerprint + atomicidad) ---

	def test_apply_signature_has_no_user_quotation(self):
		# El método de apply NO acepta una Quotation elegida por el usuario.
		params = list(inspect.signature(apply_addendum).parameters)
		self.assertEqual(params, ["change_request"])

	def test_apply_blocked_without_approved_fingerprint(self):
		_owner, cr = self._approved("CR-B6NOFP")
		frappe.db.set_value("PMO Change Request", cr.name, "approved_delta_fingerprint", "")
		self._won()
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)  # como Administrator (owner-only OK); falla por falta de fingerprint
		cr.reload()
		self.assertFalse(cr.applied_to_project)

	def test_apply_blocked_without_live_version(self):
		_owner, cr = self._approved("CR-B6NOLIVE")
		self._won()
		change_control.get_live_proposal_for_group = lambda pg: None
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)
		cr.reload()
		self.assertFalse(cr.applied_to_project)

	def test_apply_blocked_when_not_won(self):
		_owner, cr = self._approved("CR-B6NOTWON")
		# _addendum_state sigue en "En Revision" (no Ganada) → bloqueado
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)
		cr.reload()
		self.assertFalse(cr.applied_to_project)

	def test_apply_blocked_on_fingerprint_mismatch_and_primitive_not_called(self):
		_owner, cr = self._approved("CR-B6MIS")
		self._won()
		change_control.get_addendum_delta_fingerprint = lambda q: "FP-OTHER"  # != FP-DEFAULT aprobado
		calls = self._spy_apply({"tasks_created": 1})
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)
		self.assertEqual(calls, [])  # la primitive NO se llamó
		cr.reload()
		self.assertFalse(cr.applied_to_project)

	def test_apply_calls_primitive_with_derived_quotation_and_project(self):
		_owner, cr = self._approved("CR-B6CALL")
		self._won()
		calls = self._spy_apply({"tasks_created": 2})
		apply_addendum(cr.name)
		self.assertEqual(calls, [(self._addn, cr.project)])

	def test_apply_success_sets_applied_fields(self):
		_owner, cr = self._approved("CR-B6OK")
		self._won()
		self._spy_apply({"tasks_created": 2})
		apply_addendum(cr.name)
		cr.reload()
		self.assertTrue(cr.applied_to_project)
		self.assertTrue(cr.applied_at)
		self.assertEqual(cr.applied_quotation, self._addn)
		self.assertEqual(cr.workflow_state, "Approved")  # apply NO mueve el workflow

	def test_apply_tasks_created_zero_is_valid(self):
		_owner, cr = self._approved("CR-B6ZERO")
		self._won()
		self._spy_apply({"tasks_created": 0})  # addenda economic-only / $0 / sin scope
		apply_addendum(cr.name)
		cr.reload()
		self.assertTrue(cr.applied_to_project)

	def test_apply_primitive_failure_keeps_unapplied(self):
		_owner, cr = self._approved("CR-B6FAIL")
		self._won()

		def _boom(quotation, project):
			frappe.throw(frappe._("external apply failed"))

		change_control.apply_addendum_to_project = _boom
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)
		cr.reload()
		self.assertFalse(cr.applied_to_project)
		self.assertFalse(cr.applied_quotation)

	def test_apply_second_time_blocked(self):
		_owner, cr = self._approved("CR-B6TWICE")
		self._won()
		calls = self._spy_apply({"tasks_created": 1})
		apply_addendum(cr.name)
		with self.assertRaises(ValidationError):
			apply_addendum(cr.name)  # ya aplicado → bloqueado
		self.assertEqual(len(calls), 1)  # la primitive se llamó una sola vez

	def test_apply_owner_only(self):
		stranger = _user("cr-b6-stranger@example.com", ["Projects User"])
		_owner, cr = self._approved("CR-B6P4")
		self._won()
		self._spy_apply({"tasks_created": 1})
		frappe.set_user(stranger)
		try:
			with self.assertRaises(frappe.PermissionError):
				apply_addendum(cr.name)
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertFalse(cr.applied_to_project)

	# --- B8: gate de Implemented exige evidencia completa B5+B6 -------------------

	def test_implemented_blocked_without_apply(self):
		owner, cr = self._approved("CR-B8NOAPPLY")
		# Aprobado (evidencia B5) pero SIN apply (B6) → no puede implementarse.
		self._assert_action_raises(cr, "Mark Implemented", owner)

	def test_implemented_blocked_with_flag_but_no_applied_quotation(self):
		owner, cr = self._approved("CR-B8FLAG")
		# Atajo inválido: solo el flag applied_to_project, sin applied_quotation → NO basta (B8).
		frappe.db.set_value("PMO Change Request", cr.name, "applied_to_project", 1)
		cr.reload()
		self._assert_action_raises(cr, "Mark Implemented", owner)

	def test_implemented_blocked_without_governed_approval(self):
		owner, cr = self._approved("CR-B8NOAPPROVAL")
		# Simula un apply presente pero sin evidencia de aprobación gobernada (B5) → bloqueado.
		frappe.db.set_value(
			"PMO Change Request",
			cr.name,
			{"applied_to_project": 1, "applied_quotation": self._addn, "approved_delta_fingerprint": ""},
		)
		cr.reload()
		self._assert_action_raises(cr, "Mark Implemented", owner)

	def test_implemented_allowed_with_full_evidence(self):
		emp = _employee("Impl Owner B8OK")
		owner, cr = self._approved("CR-B8OK", implementation_owner=emp)
		self._do_valid_apply(cr)  # B6 real: applied_to_project + applied_quotation
		self._run(cr, "Mark Implemented", owner)
		self.assertEqual(cr.workflow_state, "Implemented")

	def test_replan_does_not_close_change_request(self):
		# D8: solo una Baseline `Approved Change` que referencia el CR fija baseline_after. Un Replan NO lo
		# hace → el CR Implemented sigue sin poder cerrarse.
		emp = _employee("Impl Owner B8REPLAN")
		owner, cr = self._approved("CR-B8REPLAN", implementation_owner=emp)
		p = cr.project
		self._do_valid_apply(cr)
		self._run(cr, "Mark Implemented", owner)
		# Replan del Project (no referencia al CR): no fija baseline_after.
		_baseline(p, "BL-RPL", btype="Replan", effective=today())
		cr.reload()
		self.assertFalse(cr.baseline_after)
		self._assert_action_raises(cr, "Close", owner)  # sin baseline_after → cierre bloqueado
