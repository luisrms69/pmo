# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 — PMO Project Handoff. Datos ficticios.

Cubre: naturaleza submittable + un-Handoff-por-Project, congelado autoritativo en before_submit (snapshot +
hash + issued_by/at), obligatoriedad del resumen de handoff y de la fecha, guard de emisión (responsable
operativo interno y contacto principal del cliente deben existir en el Project), ausencia de economía en el
snapshot (política económica), toma/congelado de responsable/contacto desde el Project (cambios posteriores en
el Project no alteran el Handoff ya emitido), y P4 (read = visibilidad del Project; write/submit = solo owner;
Executive read-only)."""

import json

import frappe
from frappe.exceptions import MandatoryError, ValidationError
from frappe.tests import IntegrationTestCase

from pmo.baseline import snapshot_hash
from pmo.permissions import has_permission_handoff
from pmo.pmo.doctype.pmo_project_handoff.pmo_project_handoff import (
	HANDOFF_SNAPSHOT_SCHEMA_VERSION,
	build_handoff_snapshot,
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


def _employee(name):
	return frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "employee_name": name, "first_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _customer(name):
	return frappe.db.exists("Customer", {"customer_name": name}) or (
		frappe.get_doc({"doctype": "Customer", "customer_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _contact(name, customer=None):
	"""Contact opcionalmente RELACIONADO a un Customer vía la tabla nativa Contact.links (Dynamic Link)."""
	existing = frappe.db.exists("Contact", {"first_name": name})
	if existing:
		return existing
	doc = frappe.get_doc({"doctype": "Contact", "first_name": name})
	if customer:
		doc.append("links", {"link_doctype": "Customer", "link_name": customer})
	return doc.insert(ignore_permissions=True, ignore_mandatory=True).name


def _project(name, owner="Administrator", committed=None, customer=None):
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
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	if committed:
		frappe.db.set_value("Project", pid, "pmo_committed_end_date", committed, update_modified=False)
	if customer:
		frappe.db.set_value("Project", pid, "customer", customer, update_modified=False)
	return pid


def _ready_project(name, owner="Administrator", committed=None, project_manager="Administrator"):
	"""Project listo para emitir el Handoff: con PM canónico, Customer y un Contact relacionado + Employee.
	Las partes (responsable operativo, contacto) se CAPTURAN en el Acta; aquí solo se preparan las fuentes.
	El Project Manager es la fuente única (Project.pmo_project_manager); el Acta lo toma read-only."""
	cust = _customer(f"Cust {name}")
	emp = _employee(f"Op {name}")
	ct = _contact(f"Contact {name}", customer=cust)
	p = _project(name, owner=owner, committed=committed, customer=cust)
	if project_manager:
		frappe.db.set_value("Project", p, "pmo_project_manager", project_manager, update_modified=False)
	return p, emp, ct


def _handoff_data(project, **kw):
	"""Datos completos de un Acta emitible (Charter + Handoff mínimo). Responsable operativo y contacto se
	capturan en el Acta; por defecto se derivan de las fuentes preparadas para el `project` (Customer)."""
	cust = frappe.db.get_value("Project", project, "customer")
	default_ct = (
		frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": "Customer", "link_name": cust},
			"parent",
		)
		if cust
		else None
	)
	default_emp = frappe.db.get_value("Employee", {}, "name")
	return {
		"doctype": "PMO Project Handoff",
		"project": project,
		"operational_owner": kw.get("operational_owner", default_emp),
		"customer_contact": kw.get("customer_contact", default_ct),
		"handoff_summary": kw.get("handoff_summary", "Se transfiere a ejecución con kickoff acordado."),
		"project_objective": kw.get("project_objective", "Poner en operación el sistema X para el cliente."),
		"scope_high_level": kw.get(
			"scope_high_level", "Implementación base, migración inicial y capacitación."
		),
		"committed_end_date": kw.get("committed_end_date", "2026-03-31"),
		"authorized_by": kw.get("authorized_by", "Sponsor del cliente (Dirección de Operaciones)"),
		"pm_informed_coordinated": kw.get("pm_informed_coordinated", 1),
		"internal_team_informed": kw.get("internal_team_informed", 1),
		"startup_conditions_reviewed": kw.get("startup_conditions_reviewed", 1),
		"contractual_legal_ready": kw.get("contractual_legal_ready", 1),
		"start_authorization_confirmed": kw.get("start_authorization_confirmed", 1),
	}


def _handoff(project, **kw):
	doc = frappe.get_doc(_handoff_data(project, **kw))
	doc.insert(ignore_permissions=True)
	return doc


def _handoff_bypass(project, **kw):
	"""Inserta un borrador saltando `reqd` del formulario (ignore_mandatory) para poder ejercitar el gate
	SERVER-SIDE en Submit — demuestra que la obligatoriedad no depende solo de `reqd` (punto 7)."""
	doc = frappe.get_doc(_handoff_data(project, **kw))
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return doc


class TestProjectHandoff(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_is_submittable_and_freezes_snapshot(self):
		p, _emp, _ct = _ready_project("HOF Freeze")
		doc = _handoff(p, committed_end_date="2026-03-31")
		self.assertEqual(doc.docstatus, 0)
		self.assertFalse(doc.snapshot_hash)  # nada congelado antes del submit
		doc.submit()
		self.assertEqual(doc.docstatus, 1)  # sigue siendo submittable
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], HANDOFF_SNAPSHOT_SCHEMA_VERSION)
		self.assertEqual(snap["project"]["name"], p)
		self.assertEqual(str(doc.committed_end_date), "2026-03-31")

	def test_handoff_summary_is_mandatory(self):
		p = _project("HOF Summary")
		doc = frappe.get_doc({"doctype": "PMO Project Handoff", "project": p})
		with self.assertRaises(MandatoryError):
			doc.insert(ignore_permissions=True)

	def test_handoff_date_is_mandatory(self):
		# Tiene default Today, pero si el usuario la borra no debe poder guardar (acta de transferencia).
		p, _emp, _ct = _ready_project("HOF Date")
		doc = _handoff(p)  # borrador con fecha por default
		doc.handoff_date = None
		with self.assertRaises(MandatoryError):
			doc.save()

	def test_no_economics_in_snapshot(self):
		# Política económica: el snapshot del Handoff NO contiene economía autorizada (sujeta a
		# can_see_project_economics / permlevel 1). Un lector del Project/Handoff no debe verla aquí.
		p, _emp, _ct = _ready_project("HOF NoEcon")
		snap = build_handoff_snapshot(p)
		self.assertNotIn("economics", snap)
		self.assertNotIn("authorized_revenue", json.dumps(snap))
		self.assertNotIn("authorized_margin", json.dumps(snap))

	def test_requires_operational_owner_to_submit(self):
		# Sin responsable operativo interno CAPTURADO en el Acta no se puede emitir.
		p, _emp, _ct = _ready_project("HOF NoOwner")
		doc = _handoff_bypass(p, operational_owner="")
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_requires_customer_contact_to_submit(self):
		# Sin contacto principal del cliente CAPTURADO en el Acta no se puede emitir.
		p, _emp, _ct = _ready_project("HOF NoContact")
		doc = _handoff_bypass(p, customer_contact="")
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_requires_project_customer_to_submit(self):
		# El Acta exige Customer en el Project para validar el contacto (relación nativa Contact↔Customer).
		p = _project("HOF NoCustomer")  # sin customer
		emp = _employee("Op NoCustomer")
		ct = _contact("Contact NoCustomer")  # contacto sin relación (no hay Customer)
		doc = _handoff_bypass(p, operational_owner=emp, customer_contact=ct)
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_rejects_contact_not_linked_to_customer(self):
		# Contacto que NO está relacionado (Dynamic Link) con el Customer del Project → Submit bloqueado.
		p, emp, _ct = _ready_project("HOF WrongContact")
		unrelated = _contact("Contact Unrelated CC")  # sin link al Customer del project
		doc = _handoff_bypass(p, operational_owner=emp, customer_contact=unrelated)
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_parties_synced_to_project_on_submit(self):
		# Al emitir, el Acta sincroniza responsable operativo y contacto hacia el Project.
		p, emp, ct = _ready_project("HOF SyncParties")
		# El Project arranca SIN partes cargadas (se capturan en el Acta).
		self.assertIsNone(frappe.db.get_value("Project", p, "pmo_operational_owner"))
		self.assertIsNone(frappe.db.get_value("Project", p, "pmo_customer_contact"))
		doc = _handoff(p, operational_owner=emp, customer_contact=ct)
		doc.submit()
		self.assertEqual(frappe.db.get_value("Project", p, "pmo_operational_owner"), emp)
		self.assertEqual(frappe.db.get_value("Project", p, "pmo_customer_contact"), ct)

	def test_contractual_legal_ready_in_snapshot_and_hash(self):
		p, _emp, _ct = _ready_project("HOF ReadySnap")
		snap_true = build_handoff_snapshot(p, True)
		snap_false = build_handoff_snapshot(p, False)
		self.assertTrue(snap_true["contractual_legal_ready"])
		self.assertFalse(snap_false["contractual_legal_ready"])
		# El hash cubre la readiness: cambiar el valor cambia el snapshot/hash construido.
		self.assertNotEqual(snapshot_hash(snap_true), snapshot_hash(snap_false))

	def test_submitted_handoff_freezes_readiness_in_snapshot(self):
		p, _emp, _ct = _ready_project("HOF ReadyFreeze")
		doc = _handoff(p)  # contractual_legal_ready = 1
		doc.submit()
		self.assertTrue(json.loads(doc.snapshot)["contractual_legal_ready"])

	def test_human_evidence_in_snapshot_and_hash(self):
		p, _emp, _ct = _ready_project("HOF HumanSnap")
		doc = _handoff(p, handoff_summary="Acta de transferencia")
		doc.submit()
		cap = json.loads(doc.snapshot)["captured"]
		for k in ("handoff_date", "project_manager", "handoff_summary", "issued_by", "issued_at"):
			self.assertIn(k, cap)
		self.assertEqual(cap["handoff_summary"], "Acta de transferencia")
		self.assertEqual(cap["issued_by"], "Administrator")
		self.assertTrue(cap["issued_at"])
		# El hash cubre la evidencia humana capturada.
		cap1 = {
			"handoff_date": "2026-01-01",
			"project_manager": None,
			"handoff_summary": "A",
			"issued_by": "Administrator",
			"issued_at": "2026-01-01 10:00:00",
		}
		h1 = snapshot_hash(build_handoff_snapshot(p, True, cap1))
		h2 = snapshot_hash(build_handoff_snapshot(p, True, dict(cap1, handoff_summary="B")))
		self.assertNotEqual(h1, h2)

	def test_requires_contractual_legal_readiness_to_submit(self):
		# Readiness contractual/legal debe estar confirmada antes de emitir el Handoff.
		p, _emp, _ct = _ready_project("HOF Readiness")
		doc = _handoff(p, contractual_legal_ready=0)
		with self.assertRaises(ValidationError):
			doc.submit()
		# Confirmada -> emite normalmente.
		doc.reload()
		doc.contractual_legal_ready = 1
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_one_handoff_per_project(self):
		p, _emp, _ct = _ready_project("HOF Unique")
		doc = _handoff(p)
		doc.submit()
		with self.assertRaises(ValidationError):
			_handoff(p)  # un segundo Handoff (no enmienda) para el mismo Project se rechaza

	def test_operational_owner_captured_and_frozen(self):
		# El responsable operativo se captura en el Acta, se congela y no cambia por edición posterior del Project.
		p, emp, ct = _ready_project("HOF OpOwner")
		doc = _handoff(p, operational_owner=emp, customer_contact=ct)
		doc.submit()
		self.assertEqual(doc.operational_owner, emp)
		self.assertEqual(json.loads(doc.snapshot)["operational_owner"], emp)
		# Cambiar el Project DESPUÉS del submit NO altera el Handoff ya emitido.
		emp2 = _employee("Op Owner HOF 2")
		frappe.db.set_value("Project", p, "pmo_operational_owner", emp2, update_modified=False)
		doc.reload()
		self.assertEqual(doc.operational_owner, emp)
		self.assertEqual(json.loads(doc.snapshot)["operational_owner"], emp)

	def test_customer_contact_captured_and_frozen(self):
		# El contacto se captura en el Acta, se congela y no cambia por edición posterior del Project.
		p, emp, ct = _ready_project("HOF Contact")
		doc = _handoff(p, operational_owner=emp, customer_contact=ct)
		doc.submit()
		self.assertEqual(doc.customer_contact, ct)
		self.assertEqual(json.loads(doc.snapshot)["customer_contact"], ct)
		# Cambio posterior en el Project no altera el Handoff emitido.
		ct2 = _contact("Primary Contact HOF 2")
		frappe.db.set_value("Project", p, "pmo_customer_contact", ct2, update_modified=False)
		doc.reload()
		self.assertEqual(doc.customer_contact, ct)

	def test_snapshot_hash_matches_frozen_json_not_live(self):
		import hashlib

		p, _emp, _ct = _ready_project("HOF Hash")
		doc = _handoff(p, committed_end_date="2026-03-31")
		doc.submit()
		self.assertEqual(doc.snapshot_hash, hashlib.sha256(doc.snapshot.encode("utf-8")).hexdigest())
		frozen = doc.snapshot
		# Cambiar el Project no altera el snapshot congelado (evidencia histórica, no vivo). La fecha del
		# snapshot es la AUTORIZADA en el Acta (2026-03-31), no la vigente en el Project.
		frappe.db.set_value("Project", p, "pmo_committed_end_date", "2027-12-31", update_modified=False)
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(json.loads(doc.snapshot)["project"]["committed_end_date"], "2026-03-31")

	def test_team_derived_from_p4_sources(self):
		owner = _user("hof_team_owner@example.com")
		p = _project("HOF Team", owner=owner)
		snap = build_handoff_snapshot(p)
		self.assertIn(owner, {m["user"] for m in snap["team"]})

	def test_p4_read_write_submit_share(self):
		owner = _user("hof_owner@example.com")
		stranger = _user("hof_stranger@example.com")
		p = _project("HOF P4", owner=owner)
		doc = _handoff_bypass(p)  # borrador solo para probar permisos (no se emite)
		# READ: visible al owner, no al extraño (sin share ni global read)
		self.assertTrue(has_permission_handoff(doc, "read", owner))
		self.assertFalse(has_permission_handoff(doc, "read", stranger))
		# WRITE/SUBMIT: solo el owner del Project
		self.assertTrue(has_permission_handoff(doc, "write", owner))
		self.assertFalse(has_permission_handoff(doc, "write", stranger))
		self.assertTrue(has_permission_handoff(doc, "submit", owner))
		self.assertFalse(has_permission_handoff(doc, "submit", stranger))
		# SHARE denegado incluso al owner
		self.assertFalse(has_permission_handoff(doc, "share", owner))

	def test_draft_does_not_sync_to_project(self):
		# La sincronización hacia el Project ocurre SOLO al emitir; un borrador no escribe nada.
		p, emp, ct = _ready_project("HOF DraftNoSync")
		_handoff(p, operational_owner=emp, customer_contact=ct)  # borrador, sin submit
		self.assertIsNone(frappe.db.get_value("Project", p, "pmo_operational_owner"))
		self.assertIsNone(frappe.db.get_value("Project", p, "pmo_customer_contact"))

	def test_owner_contact_fields_are_editable_and_required(self):
		# Ahora se CAPTURAN en el Acta: editables (no read_only) y obligatorios.
		m = frappe.get_meta("PMO Project Handoff")
		self.assertFalse(m.get_field("operational_owner").read_only)
		self.assertFalse(m.get_field("customer_contact").read_only)
		self.assertTrue(m.get_field("operational_owner").reqd)
		self.assertTrue(m.get_field("customer_contact").reqd)

	# --- Project Manager: fuente única = Project.pmo_project_manager (read-only + congelado, no sincroniza) ---
	def test_project_manager_readonly_and_fetched_from_project(self):
		m = frappe.get_meta("PMO Project Handoff")
		f = m.get_field("project_manager")
		self.assertTrue(f.read_only)
		self.assertEqual(f.fetch_from, "project.pmo_project_manager")

	def test_project_manager_frozen_from_project_not_synced(self):
		pm = _user("cc_pm@example.com")
		p, emp, ct = _ready_project("HOF PMFreeze", project_manager=pm)
		doc = _handoff(p, operational_owner=emp, customer_contact=ct)
		doc.submit()
		# Se sella el PM canónico del Project y se congela en el snapshot como evidencia.
		self.assertEqual(doc.project_manager, pm)
		self.assertEqual(json.loads(doc.snapshot)["captured"]["project_manager"], pm)
		# NO se sincroniza de vuelta: el PM del Project sigue siendo el canónico (sin cambios por el Handoff).
		self.assertEqual(frappe.db.get_value("Project", p, "pmo_project_manager"), pm)

	def test_requires_project_manager_on_project_to_submit(self):
		# Sin PM canónico en el Project no puede emitirse (sin fallback).
		p, emp, ct = _ready_project("HOF NoPM", project_manager=None)
		frappe.db.set_value("Project", p, "pmo_project_manager", None, update_modified=False)
		doc = _handoff_bypass(p, operational_owner=emp, customer_contact=ct)
		with self.assertRaises(ValidationError):
			doc.submit()

	# --- Charter mínimo: obligatoriedades SERVER-SIDE al emitir (punto 7) ---------------------------------
	def test_project_objective_required_to_submit(self):
		p, _emp, _ct = _ready_project("HOF ReqObjective")
		doc = _handoff_bypass(p, project_objective="")
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_scope_required_to_submit(self):
		p, _emp, _ct = _ready_project("HOF ReqScope")
		doc = _handoff_bypass(p, scope_high_level="")
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_committed_end_date_required_to_submit(self):
		p, _emp, _ct = _ready_project("HOF ReqCommitted")
		doc = _handoff_bypass(p, committed_end_date=None)
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_authorized_by_required_to_submit(self):
		p, _emp, _ct = _ready_project("HOF ReqAuthBy")
		doc = _handoff_bypass(p, authorized_by="")
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_start_authorization_confirmed_required_to_submit(self):
		p, _emp, _ct = _ready_project("HOF ReqAuthConfirm")
		doc = _handoff(p, start_authorization_confirmed=0)
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_coordination_checks_required_to_submit(self):
		# Cada check de coordinación debe estar marcado para emitir (validación server-side).
		for i, field in enumerate(
			("pm_informed_coordinated", "internal_team_informed", "startup_conditions_reviewed")
		):
			p, _emp, _ct = _ready_project(f"HOF ReqCoord {i}")
			doc = _handoff(p, **{field: 0})
			with self.assertRaises(ValidationError):
				doc.submit()

	# --- Fuente formal del compromiso inicial: Handoff → Project ------------------------------------------
	def test_committed_end_date_propagates_to_project_on_submit(self):
		# Al emitir, la fecha autorizada del Acta se copia a Project.pmo_committed_end_date.
		p, _emp, _ct = _ready_project("HOF Propagate")
		doc = _handoff(p, committed_end_date="2026-06-30")
		doc.submit()
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-06-30")

	def test_committed_end_date_does_not_depend_on_project_having_value(self):
		# El Acta puede fijar el compromiso aunque el Project no tuviera ninguna fecha previa.
		p, _emp, _ct = _ready_project("HOF NoPriorCommit")
		self.assertIsNone(frappe.db.get_value("Project", p, "pmo_committed_end_date"))
		doc = _handoff(p, committed_end_date="2026-05-15")
		doc.submit()
		self.assertEqual(str(doc.committed_end_date), "2026-05-15")
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-05-15")

	def test_committed_end_date_overwrites_project_value(self):
		# La fecha autorizada del Acta prevalece: sobrescribe cualquier valor previo del Project.
		p, _emp, _ct = _ready_project("HOF Overwrite", committed="2026-01-01")
		doc = _handoff(p, committed_end_date="2026-09-30")
		doc.submit()
		self.assertEqual(str(frappe.db.get_value("Project", p, "pmo_committed_end_date")), "2026-09-30")

	# --- Autorización formal: evidencia inequívoca congelada ----------------------------------------------
	def test_authorization_evidence_frozen_in_snapshot(self):
		p, _emp, _ct = _ready_project("HOF AuthEvidence")
		doc = _handoff(p, authorized_by="Cliente — Director General")
		doc.submit()
		cap = json.loads(doc.snapshot)["captured"]
		# Quién autorizó + autorización explícita confirmada + cuándo se formalizó (issued_at).
		self.assertEqual(cap["authorized_by"], "Cliente — Director General")
		self.assertTrue(cap["start_authorization_confirmed"])
		self.assertTrue(cap["issued_at"])
		# El hash cubre la evidencia de autorización: cambiar quién autorizó cambia el snapshot/hash.
		h1 = snapshot_hash(
			build_handoff_snapshot(p, True, {"authorized_by": "A"}, committed_end_date="2026-03-31")
		)
		h2 = snapshot_hash(
			build_handoff_snapshot(p, True, {"authorized_by": "B"}, committed_end_date="2026-03-31")
		)
		self.assertNotEqual(h1, h2)
