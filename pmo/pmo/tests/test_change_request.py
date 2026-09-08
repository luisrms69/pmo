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
	baseline_after_query,
	crear_addenda,
	get_current_baseline,
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


def _baseline(project, revision, btype="Original", supersedes=None, effective=None):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,
			"baseline_type": btype,
			"supersedes_baseline": supersedes,
			"effective_date": effective or today(),
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
		self.assertEqual(cr.priority, "Media")
		self.assertEqual(cr.impact_summary, "Alcance, Comercial")
		self.assertEqual(cr.workflow_state, "Borrador")  # estado inicial del Workflow

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
		self._run(cr, "Enviar a Revision", owner)
		self.assertEqual(cr.workflow_state, "En Revision")
		self.assertTrue(cr.baseline_before)  # congelada al formalizar
		self._run(cr, "Aprobar", owner)
		self.assertEqual(cr.workflow_state, "Aprobado")
		self.assertEqual(cr.docstatus, 1)
		self.assertTrue(cr.approved_by)

	def test_review_gate_requires_baseline(self):
		owner = _user("cr-wf2@example.com", ["Projects User"])
		p = _project("CR-WF2", owner=owner)  # sin baseline
		cr = _cr(p)
		with self.assertRaises(ValidationError):
			self._run(cr, "Enviar a Revision", owner)

	def test_member_cannot_approve(self):
		owner = _user("cr-wf3-o@example.com", ["Projects User"])
		member = _user("cr-wf3-m@example.com", ["Projects User"])
		p = _project("CR-WF3", owner=owner, members=[member])
		_baseline(p, "BL-001")
		cr = _cr(p)
		self._run(cr, "Enviar a Revision", member)  # member SI puede formalizar
		self.assertEqual(cr.workflow_state, "En Revision")
		frappe.set_user(member)
		try:
			with self.assertRaises(Exception):
				apply_workflow(cr, "Aprobar")  # condicion owner-only -> no es accion valida para member
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
		p = _project("CR-WF4", owner=owner)
		b1 = _baseline(p, "BL-001", effective="2026-01-01")
		cr = _cr(p, proposal_group="GRP-1")  # con proposal -> exige aplicar antes de implementar
		self._run(cr, "Enviar a Revision", owner)
		self._run(cr, "Aprobar", owner)
		# Marcar implementado sin aplicar la Quotation -> bloqueado
		self._assert_action_raises(cr, "Marcar Implementado", owner)
		# simular aplicacion (la accion real se prueba aparte) y avanzar
		frappe.db.set_value("PMO Change Request", cr.name, "applied_to_project", 1)
		cr.reload()
		self._run(cr, "Marcar Implementado", owner)
		self.assertEqual(cr.workflow_state, "Implementado")
		# Cerrar sin baseline_after -> bloqueado
		self._assert_action_raises(cr, "Cerrar", owner)
		# ligar baseline_after (owner) y cerrar
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-02-01")
		cr.reload()
		frappe.set_user(owner)
		try:
			cr.baseline_after = b2.name
			cr.save()
			apply_workflow(cr, "Cerrar")
		finally:
			frappe.set_user("Administrator")
		cr.reload()
		self.assertEqual(cr.workflow_state, "Cerrado")

	def test_implemented_ok_without_proposal(self):
		owner = _user("cr-wf5@example.com", ["Projects User"])
		p = _project("CR-WF5", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p)  # sin proposal_group -> solo-cronograma
		self._run(cr, "Enviar a Revision", owner)
		self._run(cr, "Aprobar", owner)
		self._run(cr, "Marcar Implementado", owner)  # OK sin aplicar Quotation
		self.assertEqual(cr.workflow_state, "Implementado")

	def test_cancel_blocked_on_terminal_state(self):
		owner = _user("cr-wf6@example.com", ["Projects User"])
		p = _project("CR-WF6", owner=owner)
		_baseline(p, "BL-001")
		cr = _cr(p)
		self._run(cr, "Enviar a Revision", owner)
		self._run(cr, "Rechazar", owner)
		self.assertEqual(cr.workflow_state, "Rechazado")
		frappe.set_user(owner)
		try:
			with self.assertRaises(ValidationError):
				cr.cancel()  # estado terminal
		finally:
			frappe.set_user("Administrator")

	# --- UX baseline_after: query filtrada + conveniencia vigente (5.1) ----------

	def test_baseline_after_query_filters(self):
		p = _project("CR-BAQ")
		other = _project("CR-BAQ-OTHER")
		b1 = _baseline(p, "BL-001", effective="2026-02-01")
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-03-01")
		bother = _baseline(other, "BL-001", effective="2026-03-01")
		rows = baseline_after_query(
			"PMO Project Baseline", "", "name", 0, 20, {"project": p, "baseline_before": b1.name}
		)
		names = [r[0] for r in rows]
		self.assertIn(b2.name, names)  # posterior, mismo Project
		self.assertNotIn(b1.name, names)  # excluye la propia baseline_before
		self.assertNotIn(bother.name, names)  # excluye otro Project

	def test_get_current_baseline_p4(self):
		owner = _user("cr-gcb-owner@example.com")
		outsider = _user("cr-gcb-out@example.com")
		p = _project("CR-GCB", owner=owner)
		b1 = _baseline(p, "BL-001")
		frappe.set_user(owner)
		try:
			self.assertEqual(get_current_baseline(p), b1.name)
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(outsider)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_current_baseline(p)
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
		self._run(cr, "Enviar a Revision", owner)
		self._run(cr, "Aprobar", owner)
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
		self.assertEqual(cr.workflow_state, "Aprobado")  # la accion NO mueve el Workflow
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
