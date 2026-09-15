# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D5 — PMO Post-Project Review. Datos ficticios.

Cubre: guard de secuencia (requiere Closure emitido), congelado al submit (snapshot + hash + issued),
integridad del hash contra el JSON congelado, lessons learned en el snapshot, un-Review-por-Project,
lifecycle -> post_project_reviewed, y P4 owner-only.
"""

import hashlib
import json

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.governance import LIFECYCLE_REVIEWED, derive_lifecycle_state
from pmo.permissions import has_permission_review


def _user(email):
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


def _review(project, with_lessons=True):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Post-Project Review",
			"project": project,
			"objectives_achieved": "Most objectives met",
			"what_worked": "Planning",
			"what_didnt": "Late deliveries",
			"causes": "Under-estimation",
			"recommendations": "Buffer estimates",
		}
	)
	if with_lessons:
		doc.append(
			"lessons",
			{
				"area": "Planning",
				"lesson": "Estimate better",
				"recommended_action": "Use ranges",
				"action_owner": "Administrator",
				"target_date": "2026-06-30",
			},
		)
	doc.insert(ignore_permissions=True)
	return doc


class TestPostProjectReview(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_requires_issued_closure(self):
		p = _project("PPR NoClosure")
		doc = _review(p)
		# Sin Closure emitido, el submit de la Review se rechaza (secuencia closed -> reviewed).
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_terminal_without_closure_still_rejected(self):
		# El Review es posterior al CIERRE documental, no solo al estado terminal del Project.
		for i, status in enumerate(("Completed", "Cancelled")):
			p = _project(f"PPR Terminal {i}")
			frappe.db.set_value("Project", p, "status", status, update_modified=False)
			doc = _review(p, with_lessons=False)
			with self.assertRaises(ValidationError):
				doc.submit()  # sin Closure emitido, aunque el Project sea terminal

	def test_immutable_after_submit(self):
		p = _project("PPR Immutable")
		_closure(p)
		doc = _review(p)
		doc.submit()
		frozen, frozen_hash = doc.snapshot, doc.snapshot_hash
		# Cambiar campos capturados vía DB después del submit no altera la evidencia congelada.
		frappe.db.set_value(
			"PMO Post-Project Review", doc.name, "recommendations", "changed", update_modified=False
		)
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(doc.snapshot_hash, frozen_hash)

	def test_submit_freezes_snapshot_and_lessons(self):
		p = _project("PPR Freeze")
		_closure(p)
		doc = _review(p)
		self.assertFalse(doc.snapshot_hash)
		doc.submit()
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], 2)
		self.assertEqual(len(snap["lessons"]), 1)
		self.assertEqual(snap["lessons"][0]["area"], "Planning")
		# La lesson congela también action_owner + target_date (ciclo accionable).
		self.assertEqual(snap["lessons"][0]["action_owner"], "Administrator")
		self.assertEqual(snap["lessons"][0]["target_date"], "2026-06-30")
		# Integridad contra la evidencia congelada.
		self.assertEqual(doc.snapshot_hash, hashlib.sha256(doc.snapshot.encode("utf-8")).hexdigest())

	def test_freezes_closure_traceability(self):
		p = _project("PPR Trace")
		cls = _closure(p)
		doc = _review(p)
		doc.submit()
		snap = json.loads(doc.snapshot)
		# Congela reviewed_by + referencia y hash del Closure base.
		self.assertIn("reviewed_by", snap)
		self.assertEqual(snap["based_on_closure"]["reference"], cls.name)
		self.assertEqual(snap["based_on_closure"]["snapshot_hash"], cls.snapshot_hash)
		frozen = doc.snapshot
		# Enmienda/cancelación posterior del Closure NO altera la trazabilidad congelada en la Review.
		cls.reload()
		cls.cancel()
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(json.loads(doc.snapshot)["based_on_closure"]["reference"], cls.name)

	def test_lifecycle_reviewed(self):
		p = _project("PPR Lifecycle")
		_closure(p)
		_review(p).submit()
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_REVIEWED)

	def test_one_review_per_project(self):
		p = _project("PPR Unique")
		_closure(p)
		_review(p).submit()
		with self.assertRaises(ValidationError):
			_review(p)

	def test_p4_read_and_write(self):
		owner = _user("ppr_owner@example.com")
		stranger = _user("ppr_stranger@example.com")
		p = _project("PPR P4", owner=owner)
		doc = _review(p)
		self.assertTrue(has_permission_review(doc, "read", owner))
		self.assertFalse(has_permission_review(doc, "read", stranger))
		self.assertTrue(has_permission_review(doc, "submit", owner))
		self.assertFalse(has_permission_review(doc, "submit", stranger))
		self.assertFalse(has_permission_review(doc, "share", owner))

	# ── Ciclo accionable (ToDo nativo) ────────────────────────────────────────────────

	def test_action_owner_and_date_mandatory_when_action_set(self):
		"""Si `recommended_action` tiene valor, action_owner y target_date son obligatorios
		(enforcement server-side en validate). Falta owner/date → falla el guardado."""
		p = _project("PPR MandAction")
		doc = frappe.get_doc(
			{
				"doctype": "PMO Post-Project Review",
				"project": p,
				"objectives_achieved": "ok",
			}
		)
		doc.append("lessons", {"area": "Cost", "lesson": "Track scope", "recommended_action": "Add gate"})
		with self.assertRaises(ValidationError):
			doc.insert(ignore_permissions=True)

	def test_lesson_without_action_needs_no_owner(self):
		"""Una lesson SIN recommended_action puede existir sin owner/date y sin generar ToDo."""
		p = _project("PPR NoAction")
		_closure(p)
		doc = frappe.get_doc(
			{"doctype": "PMO Post-Project Review", "project": p, "objectives_achieved": "ok"}
		)
		doc.append("lessons", {"area": "Cost", "lesson": "Only observation"})
		doc.insert(ignore_permissions=True)
		doc.submit()
		todos = frappe.get_all("ToDo", filters={"reference_type": doc.doctype, "reference_name": doc.name})
		self.assertEqual(len(todos), 0)

	def test_submit_creates_native_todo_per_action(self):
		"""Al submit, cada lesson con recommended_action produce un ToDo NATIVO con los campos esperados."""
		p = _project("PPR ToDo")
		_closure(p)
		doc = _review(p)
		doc.submit()
		todos = frappe.get_all(
			"ToDo",
			filters={"reference_type": doc.doctype, "reference_name": doc.name},
			fields=["allocated_to", "date", "description", "reference_type", "reference_name", "status"],
		)
		self.assertEqual(len(todos), 1)
		t = todos[0]
		self.assertEqual(t["allocated_to"], "Administrator")
		self.assertEqual(str(t["date"]), "2026-06-30")
		self.assertIn("Use ranges", t["description"])
		self.assertEqual(t["reference_type"], "PMO Post-Project Review")
		self.assertEqual(t["reference_name"], doc.name)
		self.assertEqual(t["status"], "Open")

	def test_continuous_improvement_data_contract(self):
		"""Contrato de datos de Mejora continua (capacidad separada de Governance): la acción es el ToDo y el
		Project de origen es alcanzable vía reference_name → Post-Project Review → project, sin denormalizar."""
		p = _project("PPR CIData")
		_closure(p)
		doc = _review(p)
		doc.submit()
		todo = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "PMO Post-Project Review",
				"reference_name": doc.name,
				"status": "Open",
			},
			fields=["name", "reference_name"],
		)[0]
		# Project de origen derivado por join nativo (no se guarda en el ToDo).
		source_project = frappe.db.get_value("PMO Post-Project Review", todo["reference_name"], "project")
		self.assertEqual(source_project, p)

	# ── UX nativa ─────────────────────────────────────────────────────────────────────

	def test_project_link_filter_terminal_only(self):
		"""Filtro nativo link_filters en `project`: solo Completed/Cancelled."""
		meta = frappe.get_meta("PMO Post-Project Review")
		lf = meta.get_field("project").link_filters
		self.assertIn("Completed", lf)
		self.assertIn("Cancelled", lf)
		self.assertIn("status", lf)

	def test_title_removed_from_doctype(self):
		"""`title` eliminado: ni campo ni title_field."""
		meta = frappe.get_meta("PMO Post-Project Review")
		self.assertIsNone(meta.get_field("title"))
		self.assertFalse(meta.title_field)
