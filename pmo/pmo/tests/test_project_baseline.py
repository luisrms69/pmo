# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0004 — PMO Project Baseline. Datos ficticios.

Cubre: invariantes de lineage (configuration control lineal), congelado autoritativo en before_submit
(snapshot canonico + hash + aprobacion), preflight bloqueante ante reparto inconsistente, derivacion de
la baseline vigente as-of (Opcion B, sin future-effective), y P4 (read = visibilidad del Project;
write/submit = solo owner; Executive read-only).
"""

import json

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from pmo import change_control
from pmo.baseline import build_snapshot, get_effective_baseline, run_preflight, snapshot_hash
from pmo.permissions import has_permission_baseline
from pmo.pmo.doctype.pmo_change_request import pmo_change_request as crmod
from pmo.pmo.doctype.pmo_project_baseline.pmo_project_baseline import (
	establish_baseline,
	get_baseline_state,
	new_baseline,
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


def _employee(name, user_id):
	emp = frappe.db.exists("Employee", {"employee_name": name}) or (
		frappe.get_doc({"doctype": "Employee", "first_name": name, "status": "Active"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Employee", emp, "user_id", user_id)
	return emp


def _project(name, owner="Administrator"):
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


def _task(subject, project, is_group=0, expected_time=0, exp_start=None, exp_end=None, parent=None):
	tid = frappe.db.exists("Task", {"subject": subject})
	if tid:
		return tid
	doc = {
		"doctype": "Task",
		"subject": subject,
		"project": project,
		"is_group": is_group,
		"expected_time": expected_time,
		"status": "Open",
	}
	if parent:
		doc["parent_task"] = parent
	if exp_start:
		doc["exp_start_date"] = exp_start
	if exp_end:
		doc["exp_end_date"] = exp_end
	return frappe.get_doc(doc).insert(ignore_permissions=True, ignore_mandatory=True).name


def _assign(task, user, override=None):
	td = frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"reference_type": "Task",
			"reference_name": task,
			"status": "Open",
			"description": f"a {task}",
		}
	).insert(ignore_permissions=True)
	if override is not None:
		frappe.db.set_value("ToDo", td.name, "pmo_planned_hours", override)
	return td.name


def _baseline(
	project,
	revision=None,
	btype="Original",
	supersedes=None,
	effective=None,
	submit=False,
	reason="Motivo",
	change_request=None,
):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Project Baseline",
			"project": project,
			"revision": revision,  # None -> autogenerada por el controlador (BL-NNN)
			"baseline_type": btype,
			"supersedes_baseline": supersedes,
			"effective_date": effective or today(),
			"reason": reason,
			"change_request": change_request,
		}
	).insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _implemented_cr(project, owner):
	"""Crea un PMO Change Request y lo lleva por su Workflow real hasta `Implemented` (aprobado + aplicado,
	a la espera de su nueva baseline). Requiere una baseline vigente en el Project (gate de `In Review`).
	El gate de Implemented exige responsable de implementación y aceptación del cliente documentada."""
	from frappe.model.workflow import apply_workflow

	emp = _employee("CR Impl Owner", owner)
	# Flujo único (ADR-0015 B4/B5/B6): toda CR formal tiene su Addenda (`proposal_group`); la aprobación
	# captura approved_addendum + fingerprint (B5) y el apply real (B6) fija applied_to_project +
	# applied_quotation. El contrato de erpnext_proposals (ausente en el site de tests) se mockea.
	cr = frappe.get_doc(
		{
			"doctype": "PMO Change Request",
			"project": project,
			"title": "Cambio",
			"reason": "Motivo",
			"implementation_owner": emp,
			"proposal_group": "GRP-1",
		}
	).insert(ignore_permissions=True)
	# B5: la captura al aprobar consulta el contrato de erpnext_proposals (ausente en el site de tests).
	# Se mockean los seams para que la captura tenga éxito (versión viva En Revision + fingerprint).
	cust = frappe.db.exists("Customer", {"customer_name": "BL-B5-Cust"})
	if not cust:
		c = frappe.get_doc({"doctype": "Customer", "customer_name": "BL-B5-Cust"})
		c.flags.ignore_validate = True
		cust = c.insert(ignore_permissions=True, ignore_mandatory=True).name
	_q = frappe.get_doc({"doctype": "Quotation", "quotation_to": "Customer", "party_name": cust})
	_q.flags.ignore_validate = True
	addn = _q.insert(ignore_permissions=True, ignore_mandatory=True).name
	orig_live = change_control.get_live_proposal_for_group
	orig_fp = change_control.get_addendum_delta_fingerprint
	orig_state = crmod._addendum_state
	orig_apply = change_control.apply_addendum_to_project
	change_control.get_live_proposal_for_group = lambda pg: addn
	change_control.get_addendum_delta_fingerprint = lambda q: "FP-DEFAULT"
	crmod._addendum_state = lambda q: frappe._dict(docstatus=1, workflow_state="En Revision")
	change_control.apply_addendum_to_project = lambda quotation, project: {"tasks_created": 1}
	prev = frappe.session.user
	frappe.set_user(owner)
	try:
		apply_workflow(cr, "Send for Review")  # In Review: congela baseline_before = vigente
		apply_workflow(cr, "Approve")  # Approved (Submit) → captura Addenda gobernada (B5)
		# B6 real: pasa a Ganada y aplica → fija applied_to_project + applied_quotation (no atajo por DB).
		crmod._addendum_state = lambda q: frappe._dict(docstatus=1, workflow_state="Ganada")
		crmod.apply_addendum(cr.name)
		cr.reload()
		apply_workflow(cr, "Mark Implemented")  # Implemented (evidencia B5+B6 completa)
	finally:
		frappe.set_user(prev)
		change_control.get_live_proposal_for_group = orig_live
		change_control.get_addendum_delta_fingerprint = orig_fp
		crmod._addendum_state = orig_state
		change_control.apply_addendum_to_project = orig_apply
	cr.reload()
	return cr


class TestBaselineFromProject(IntegrationTestCase):
	"""Operación de línea base desde Project (endpoints native-first: establecer / nueva / estado).
	Reutiliza el controlador (snapshot + submit); baseline inmutable; sin overwrite; conserva la cadena;
	sin ampliar Change Control (usa `Implemented` + `baseline_after`)."""

	def setUp(self):
		frappe.set_user("Administrator")

	def _proj_with_tasks(self, name):
		p = _project(name)
		_task(f"{name}-T1", p, exp_start="2026-01-05", exp_end="2026-01-20")
		_task(f"{name}-T2", p, exp_start="2026-01-21", exp_end="2026-02-10")
		return p

	def test_state_no_baseline(self):
		p = self._proj_with_tasks("BLP-STATE0")
		st = get_baseline_state(p)
		self.assertFalse(st["has_baseline"])
		self.assertIsNone(st["revision"])
		# Sin línea base → sin historial: baseline_count == 0 (la UI no muestra «Historial de líneas base»).
		self.assertEqual(st["baseline_count"], 0)

	def test_establish_creates_submitted_original(self):
		p = self._proj_with_tasks("BLP-EST")
		r = establish_baseline(p, reason="Compromiso inicial")
		self.assertTrue(r["revision"])
		bl = frappe.get_doc("PMO Project Baseline", r["name"])
		self.assertEqual(bl.docstatus, 1)  # submitted (inmutable)
		self.assertEqual(bl.baseline_type, "Original")
		self.assertEqual(get_effective_baseline(p), r["name"])
		st = get_baseline_state(p)
		self.assertTrue(st["has_baseline"])
		self.assertEqual(st["revision"], bl.revision)
		# Con una línea base establecida → historial visible: baseline_count >= 1.
		self.assertGreaterEqual(st["baseline_count"], 1)

	def test_establish_requires_reason_server_side(self):
		# El motivo es OBLIGATORIO también server-side: el endpoint rechaza la PRIMERA baseline sin motivo,
		# no basta el `reqd` del diálogo. Con motivo, procede.
		p = self._proj_with_tasks("BLP-REASON")
		with self.assertRaises(ValidationError):
			establish_baseline(p, reason="   ")
		with self.assertRaises(ValidationError):
			establish_baseline(p)  # sin argumento de motivo
		self.assertIsNone(get_effective_baseline(p))  # nada se creó
		r = establish_baseline(p, reason="Compromiso formal inicial")
		self.assertEqual(get_effective_baseline(p), r["name"])

	def test_establish_rejected_if_baseline_exists(self):
		# No overwrite: con baseline vigente, «Establecer» se rechaza (usar «Nueva línea base»).
		p = self._proj_with_tasks("BLP-EST2")
		establish_baseline(p, reason="Compromiso inicial")
		with self.assertRaises(ValidationError):
			establish_baseline(p, reason="Segundo intento")

	def test_establish_rejected_without_tasks(self):
		p = _project("BLP-NOTASK")
		with self.assertRaises(ValidationError):
			establish_baseline(p, reason="Motivo")

	def test_new_baseline_replan_supersedes_and_preserves_chain(self):
		p = self._proj_with_tasks("BLP-REPLAN")
		first = establish_baseline(p, reason="Compromiso inicial")
		second = new_baseline(p, reason="Replaneación por desviaciones acumuladas")
		self.assertNotEqual(first["name"], second["name"])
		self.assertEqual(get_effective_baseline(p), second["name"])  # vigente = nueva
		self.assertEqual(
			frappe.db.get_value("PMO Project Baseline", first["name"], "docstatus"), 1
		)  # se conserva
		self.assertEqual(frappe.get_doc("PMO Project Baseline", second["name"]).baseline_type, "Replan")

	def test_new_baseline_requires_reason(self):
		p = self._proj_with_tasks("BLP-NOREASON")
		establish_baseline(p, reason="Compromiso inicial")
		with self.assertRaises(ValidationError):
			new_baseline(p, reason="   ")

	def test_new_baseline_requires_existing_baseline(self):
		p = self._proj_with_tasks("BLP-NOEXIST")
		with self.assertRaises(ValidationError):
			new_baseline(p, reason="motivo")

	def test_replan_rejected_for_normal_pm(self):
		# PM normal (owner, Projects User, sin rol PMO): puede establecer la primera baseline, pero NO
		# puede rebaselinar libremente (Replan sin CR). Debe ir por el mecanismo formal (Approved Change).
		pm = _user("bl-pm@example.com", ["Projects User"])
		p = self._proj_with_tasks("BLP-PM-REPLAN")
		frappe.db.set_value("Project", p, "owner", pm)
		frappe.set_user(pm)
		try:
			establish_baseline(p, reason="Compromiso inicial")  # Original permitido para el owner
			with self.assertRaises(frappe.PermissionError):
				new_baseline(p, reason="Rebaseline libre no autorizado")
		finally:
			frappe.set_user("Administrator")

	def test_replan_allowed_for_authorized_pmo(self):
		# Rol PMO autorizado (PMO Manager) + owner: Replan excepcional permitido, con motivo/trazabilidad.
		mgr = _user("bl-mgr@example.com", ["Projects User", "PMO Manager"])
		p = self._proj_with_tasks("BLP-MGR-REPLAN")
		frappe.db.set_value("Project", p, "owner", mgr)
		frappe.set_user(mgr)
		try:
			establish_baseline(p, reason="Compromiso inicial")
			r = new_baseline(p, reason="Replaneación autorizada por PMO")
			self.assertEqual(frappe.get_doc("PMO Project Baseline", r["name"]).baseline_type, "Replan")
		finally:
			frappe.set_user("Administrator")

	def test_state_exposes_can_replan(self):
		p = self._proj_with_tasks("BLP-CANREPLAN")
		self.assertTrue(get_baseline_state(p)["can_replan"])  # Administrator (System Manager)

	def test_new_baseline_approved_change_links_cr(self):
		# Integración real con Change Control (sin ampliarlo): CR Implemented + baseline_after.
		p = self._proj_with_tasks("BLP-APPR")
		establish_baseline(
			p, reason="Compromiso inicial"
		)  # el gate «In Review» del CR exige baseline vigente
		cr = _implemented_cr(p, "Administrator")
		st = get_baseline_state(p)
		self.assertIn(cr.name, [c["name"] for c in st["eligible_crs"]])
		second = new_baseline(p, reason="Cambio aprobado aplicado", change_request=cr.name)
		bl = frappe.get_doc("PMO Project Baseline", second["name"])
		self.assertEqual(bl.baseline_type, "Approved Change")
		self.assertEqual(frappe.db.get_value("PMO Change Request", cr.name, "baseline_after"), second["name"])


class TestProjectBaseline(IntegrationTestCase):
	# --- invariantes de lineage --------------------------------------------------

	def test_original_must_not_supersede(self):
		p = _project("BL-P1")
		base = _baseline(p, "BL-001", submit=True)
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-XX", btype="Original", supersedes=base.name)

	def test_only_one_valid_original_per_project(self):
		p = _project("BL-P2")
		_baseline(p, "BL-001", submit=True)
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-002", btype="Original")

	def test_revision_unique_per_project(self):
		p = _project("BL-P3")
		_baseline(p, "BL-001", submit=True)
		# otra revision distinta que sustituye la cabeza: ok; misma revision: bloquea
		with self.assertRaises(ValidationError):
			_baseline(
				p,
				"BL-001",
				btype="Replan",
				supersedes=frappe.db.get_value(
					"PMO Project Baseline", {"project": p, "revision": "BL-001"}, "name"
				),
			)

	def test_nonoriginal_without_effective_baseline_is_rejected(self):
		# Una baseline no-Original necesita una vigente que sustituir; sin Original previa, se rechaza
		# (supersedes se autodetermina y queda vacía → error claro).
		p = _project("BL-P4")
		with self.assertRaises(ValidationError):
			_baseline(p, btype="Replan")

	def test_supersedes_must_be_submitted(self):
		p = _project("BL-P5")
		draft = _baseline(p, "BL-001")  # NO submitted
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-002", btype="Replan", supersedes=draft.name)

	def test_no_fork(self):
		p = _project("BL-P6")
		orig = _baseline(p, "BL-001", submit=True)
		_baseline(p, "BL-002", btype="Replan", supersedes=orig.name, submit=True)
		# BL-003 intenta sustituir de nuevo BL-001 (cabeza ya sustituida) -> bifurcacion
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-003", btype="Replan", supersedes=orig.name)

	def test_effective_date_not_future(self):
		p = _project("BL-P7")
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-001", effective="2999-01-01")

	# --- congelado autoritativo (before_submit) ----------------------------------

	def _scenario(self, pname):
		# Frappe minusculiza el name/email del User; usar minusculas para comparar contra ToDo.allocated_to.
		subj = _user(f"{pname.lower()}-subj@example.com")
		emp = _employee(f"{pname} Emp", subj)
		p = _project(pname, owner=subj)
		g = _task(
			f"{pname} Fase", p, is_group=1, expected_time=0, exp_start="2026-01-05", exp_end="2026-01-09"
		)
		c = _task(
			f"{pname} Tarea",
			p,
			is_group=0,
			expected_time=8,
			exp_start="2026-01-05",
			exp_end="2026-01-09",
			parent=g,
		)
		_assign(c, subj)  # sin override -> reparto uniforme (8h a 1 asignado)
		return subj, emp, p, g, c

	def test_submit_builds_snapshot(self):
		subj, emp, p, g, c = self._scenario("BL-P8")
		base = _baseline(p, "BL-001", submit=True)
		base.reload()
		self.assertTrue(base.snapshot_hash)
		self.assertEqual(base.snapshot_schema_version, 1)
		self.assertTrue(base.snapshot_at and base.approved_at)
		self.assertEqual(base.approved_by, "Administrator")  # quien ejecuto el submit

		snap = json.loads(base.snapshot)
		self.assertEqual(snap["project"]["name"], p)
		task = next(t for t in snap["tasks"] if t["name"] == c)
		self.assertEqual(task["wbs_order"], 1)
		self.assertEqual(task["parent_task"], g)
		a = task["assignments"][0]
		self.assertEqual(a["user"], subj)
		self.assertEqual(a["employee"], emp)
		self.assertIsNone(a["override_hours"])
		self.assertEqual(a["effective_hours"], 8.0)

	def test_snapshot_hash_deterministic(self):
		_subj, _emp, p, _g, _c = self._scenario("BL-P9")
		self.assertEqual(snapshot_hash(build_snapshot(p)), snapshot_hash(build_snapshot(p)))

	def test_effective_baseline_asof(self):
		_subj, _emp, p, _g, _c = self._scenario("BL-P10")
		base = _baseline(p, "BL-001", submit=True)
		self.assertEqual(get_effective_baseline(p), base.name)

	# --- preflight bloqueante ----------------------------------------------------

	def test_preflight_blocks_inconsistent_distribution(self):
		p = _project("BL-P11")
		u1 = _user("bl-u1@example.com")
		u2 = _user("bl-u2@example.com")
		t = _task("BL-P11 T", p, expected_time=8, exp_start="2026-01-05", exp_end="2026-01-09")
		_assign(t, u1, override=6)
		_assign(t, u2, override=4)  # 6+4=10 != 8 -> inconsistente
		pf = run_preflight(p)
		self.assertTrue(any(b["code"] == "inconsistent_distribution" for b in pf["blocking"]))
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-001", submit=True)

	# --- P4 -----------------------------------------------------------------------

	def test_permissions_read_and_write(self):
		subj = _user("bl-owner@example.com")
		other = _user("bl-other@example.com")
		execu = _user("bl-exec@example.com", ["PMO Executive Access"])
		p = _project("BL-P12", owner=subj)
		base = _baseline(p, "BL-001")  # draft

		# READ = visibilidad del Project
		self.assertTrue(has_permission_baseline(base, "read", subj))  # owner
		self.assertFalse(has_permission_baseline(base, "read", other))  # ajeno
		self.assertTrue(has_permission_baseline(base, "read", execu))  # executive global

		# WRITE/SUBMIT = solo owner
		self.assertTrue(has_permission_baseline(base, "write", subj))
		self.assertTrue(has_permission_baseline(base, "submit", subj))
		self.assertFalse(has_permission_baseline(base, "submit", other))
		self.assertFalse(has_permission_baseline(base, "submit", execu))  # executive read-only
		self.assertFalse(has_permission_baseline(base, "share", subj))

	# --- cancelacion / monotonia de vigencia -------------------------------------

	def test_cannot_cancel_intermediate_with_successor(self):
		p = _project("BL-P13")
		b1 = _baseline(p, "BL-001", submit=True)
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, submit=True)
		# cancelar la intermedia (con sucesor no-cancelado) -> bloqueado
		with self.assertRaises(ValidationError):
			b1.cancel()
		# cancelar la cabeza -> permitido; la vigencia vuelve a la anterior
		b2.reload()
		b2.cancel()
		self.assertEqual(get_effective_baseline(p), b1.name)

	def test_effective_date_monotonic_in_chain(self):
		p = _project("BL-P14")
		b1 = _baseline(p, "BL-001", effective="2026-02-01", submit=True)
		# sucesora con effective ANTERIOR -> bloqueado
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-01-01")
		# igual fecha -> permitido
		b2 = _baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-02-01")
		self.assertTrue(b2.name)


class TestBaselineRevisionAndTypes(IntegrationTestCase):
	"""Autogeneración de revision, autodeterminación de la línea base sustituida, obligatoriedad del motivo,
	y reglas del tipo Cambio aprobado (Change Request válido + relación consistente con baseline_after)."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_revision_autogenerated_per_project(self):
		p = _project("BL-RV1")
		b1 = _baseline(p, submit=True)  # sin revision -> BL-001
		self.assertEqual(b1.revision, "BL-001")
		b2 = _baseline(p, btype="Replan", submit=True)  # -> BL-002 (supersedes autodeterminado)
		self.assertEqual(b2.revision, "BL-002")
		# otro Project reinicia el consecutivo
		p2 = _project("BL-RV2")
		self.assertEqual(_baseline(p2, submit=True).revision, "BL-001")

	def test_supersedes_autodetermined_from_effective(self):
		p = _project("BL-SD1")
		b1 = _baseline(p, submit=True)
		b2 = _baseline(p, btype="Replan", submit=True)  # sin supersedes explícito
		self.assertEqual(b2.supersedes_baseline, b1.name)

	def test_reason_mandatory_for_nonoriginal(self):
		p = _project("BL-RM1")
		_baseline(p, submit=True)
		with self.assertRaises(ValidationError):  # MandatoryError hereda de ValidationError
			_baseline(p, btype="Replan", reason=None)

	def test_original_reason_mandatory(self):
		# La línea base es un compromiso formal: el motivo es OBLIGATORIO también para la Original.
		p = _project("BL-RM2")
		with self.assertRaises(ValidationError):  # MandatoryError / ValidationError
			_baseline(p, reason=None, submit=True)
		# Con motivo, la Original procede con normalidad.
		b = _baseline(p, reason="Compromiso formal inicial", submit=True)
		self.assertEqual(b.baseline_type, "Original")

	def test_replan_does_not_require_change_request(self):
		p = _project("BL-RP1")
		_baseline(p, submit=True)
		b2 = _baseline(p, btype="Replan", submit=True)
		self.assertEqual(b2.baseline_type, "Replan")
		self.assertFalse(b2.change_request)

	def test_approved_change_requires_change_request(self):
		p = _project("BL-AC1")
		_baseline(p, submit=True)
		with self.assertRaises(ValidationError):
			_baseline(p, btype="Approved Change")  # sin Solicitud de cambio

	def test_approved_change_rejects_draft_cr(self):
		p = _project("BL-AC2")
		_baseline(p, submit=True)
		cr = frappe.get_doc(
			{"doctype": "PMO Change Request", "project": p, "title": "Cambio", "reason": "Motivo"}
		).insert(ignore_permissions=True)  # Draft: no válido
		with self.assertRaises(ValidationError):
			_baseline(p, btype="Approved Change", change_request=cr.name)

	def test_approved_change_rejects_cr_of_other_project(self):
		owner = _user("bl-ac3-owner@example.com", ["Projects User"])
		p1 = _project("BL-AC3a", owner=owner)
		_baseline(p1, submit=True)
		cr = _implemented_cr(p1, owner)
		p2 = _project("BL-AC3b", owner=owner)
		_baseline(p2, submit=True)
		with self.assertRaises(ValidationError):
			_baseline(p2, btype="Approved Change", change_request=cr.name)  # CR de otro Project

	def test_approved_change_links_and_blocks_reuse(self):
		owner = _user("bl-ac4-owner@example.com", ["Projects User"])
		p = _project("BL-AC4", owner=owner)
		b1 = _baseline(p, submit=True)
		cr = _implemented_cr(p, owner)
		self.assertFalse(cr.baseline_after)
		# Cambio aprobado: relación consistente con baseline_after y supersedes autodeterminado.
		b2 = _baseline(p, btype="Approved Change", change_request=cr.name, submit=True)
		cr.reload()
		self.assertEqual(cr.baseline_after, b2.name)
		self.assertEqual(b2.supersedes_baseline, b1.name)
		# reutilizar el mismo CR (ya con baseline_after) en otra baseline -> bloqueado
		with self.assertRaises(ValidationError):
			_baseline(p, btype="Approved Change", change_request=cr.name)
