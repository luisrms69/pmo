# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 (Opción E) — PMO Project Risk (registro vivo) + evolución nativa + P4 + Risk Register.

La historia del riesgo la conserva Frappe nativamente (`track_changes` → `Version`: qué cambió, old → new, quién,
cuándo; consultable en el Timeline). NO hay child de historia. Lo único custom es el MOTIVO obligatorio ante
cambio material (`update_note`), que tras un save exitoso se publica como **Comment nativo** y se limpia.

Cubre: exposición derivada, status default, descripción obligatoria, motivo obligatorio por cada campo material,
varios cambios en un Save → un solo Comment, cambio no material sin nota, contenido exacto del Comment,
`update_note` limpiado, `Version` nativo registra old → new, creación inicial sin nota, riesgo manual, P4 y el
Risk Register."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from pmo.permissions import has_permission_risk
from pmo.pmo.report.pmo_project_risk_register.pmo_project_risk_register import execute as register_execute


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
		frappe.get_doc({"doctype": "Project", "project_name": name, "status": "Open"})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	return pid


def _risk(project, **vals):
	doc = {
		"doctype": "PMO Project Risk",
		"project": project,
		"description": vals.pop("description", "Riesgo de prueba"),
		"probability": vals.pop("probability", "High likelihood"),
		"impact": vals.pop("impact", "High"),
	}
	doc.update(vals)
	return frappe.get_doc(doc).insert(ignore_permissions=True)


def _comments(risk_name):
	return frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "PMO Project Risk",
			"reference_name": risk_name,
			"comment_type": "Comment",
		},
		fields=["content"],
		order_by="creation asc",
	)


def _versions(risk_name):
	return frappe.get_all(
		"Version",
		filters={"ref_doctype": "PMO Project Risk", "docname": risk_name},
		fields=["data"],
		order_by="creation asc",
	)


class TestProjectRisk(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_exposure_derived_and_status_default(self):
		r = _risk(_project("PR Exposure"), probability="Low likelihood", impact="High")
		self.assertEqual(r.exposure, "Medium exposure")
		self.assertEqual(r.status, "Open")
		self.assertTrue(r.identified_on)

	def test_description_required(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.get_doc(
				{"doctype": "PMO Project Risk", "project": _project("PR NoDesc"), "description": "  "}
			).insert(ignore_permissions=True)

	def test_manual_direct_risk(self):
		r = _risk(_project("PR Manual"), description="Riesgo directo")
		self.assertEqual(int(r.is_manual or 0), 1)  # sin source_question_code → manual

	def test_project_selectable_on_create(self):
		p = _project("PR CreateProj")
		r = _risk(p, description="Riesgo")
		self.assertEqual(r.project, p)  # se pudo fijar al crear

	def test_project_is_immutable_on_existing(self):
		p1 = _project("PR Imm1")
		p2 = _project("PR Imm2")
		r = _risk(p1, description="Riesgo")
		r.project = p2
		with self.assertRaises(frappe.exceptions.ValidationError):
			r.save()  # enforcement server-side (cubre API/script/import/save)

	def test_initial_creation_requires_no_note_and_no_comment(self):
		r = _risk(_project("PR Init"), probability="High likelihood", impact="High")
		self.assertEqual(len(_comments(r.name)), 0)  # sin Comment artificial en la creación

	def test_material_change_requires_note(self):
		r = _risk(_project("PR NoteReq"), probability="High likelihood", impact="High")
		r.status = "Managing"  # cambio material sin nota → bloquea
		with self.assertRaises(frappe.exceptions.ValidationError):
			r.save()

	def _assert_field_is_trigger(self, name, field, value, note):
		r = _risk(_project(name), probability="High likelihood", impact="High")
		setattr(r, field, value)
		with self.assertRaises(frappe.exceptions.ValidationError):
			r.save()  # cambio material sin nota → bloquea
		r.reload()  # tras el save fallido, recargar (en UI el form recarga; evita TimestampMismatch)
		setattr(r, field, value)
		r.update_note = note
		r.save()
		r.reload()
		self.assertEqual(getattr(r, field), value)
		comments = _comments(r.name)
		self.assertEqual(len(comments), 1)
		self.assertEqual(comments[0].content, note)
		self.assertFalse(r.update_note)  # transitorio limpiado

	def test_description_is_material_trigger(self):
		self._assert_field_is_trigger(
			"PR Desc", "description", "Enunciado refinado", "Se aclara el enunciado."
		)

	def test_probability_is_material_trigger(self):
		self._assert_field_is_trigger("PR Prob", "probability", "Low likelihood", "Baja la probabilidad.")

	def test_impact_is_material_trigger(self):
		self._assert_field_is_trigger("PR Impact", "impact", "Low", "Menor impacto estimado.")

	def test_status_is_material_trigger(self):
		self._assert_field_is_trigger("PR Status", "status", "Managing", "Entra en gestión activa.")

	def test_owner_is_material_trigger(self):
		self._assert_field_is_trigger("PR Owner", "risk_owner", "Administrator", "Se reasigna responsable.")

	def test_response_is_material_trigger(self):
		self._assert_field_is_trigger("PR Resp", "response", "Proveedor alterno", "Se define tratamiento.")

	def test_may_affect_controlled_is_material_trigger(self):
		self._assert_field_is_trigger(
			"PR Signal", "may_affect_controlled", "Yes", "Podría afectar el alcance."
		)

	def test_multiple_material_changes_single_comment(self):
		r = _risk(
			_project("PR Multi"),
			description="Riesgo inicial",
			probability="High likelihood",
			impact="High",
		)
		# Un solo guardado cambia probability, owner, response y status simultáneamente.
		r.probability = "Medium likelihood"
		r.risk_owner = "Administrator"
		r.response = "Proveedor alterno confirmado"
		r.status = "Managing"
		r.update_note = "Reevaluación integral tras confirmación del proveedor."
		r.save()
		r.reload()
		comments = _comments(r.name)
		self.assertEqual(len(comments), 1)  # UN solo Comment, no cuatro
		self.assertEqual(comments[0].content, "Reevaluación integral tras confirmación del proveedor.")
		self.assertFalse(r.update_note)

	def test_no_note_and_no_comment_without_material_change(self):
		r = _risk(_project("PR NoChange"), probability="High likelihood", impact="High")
		r.save()  # re-guardar sin cambios → sin nota y sin Comment
		r.reload()
		self.assertEqual(len(_comments(r.name)), 0)

	def test_native_version_records_old_to_new(self):
		r = _risk(_project("PR Version"), probability="High likelihood", impact="High")
		r.status = "Managing"
		r.update_note = "Cambio de estado."
		# Frappe desactiva Version en modo test por defecto (document.py: ignore_version = frappe.in_test);
		# lo forzamos para verificar que track_changes registra old → new.
		r.save(ignore_version=False)
		versions = _versions(r.name)
		self.assertTrue(versions)  # track_changes creó al menos un Version
		# Alguna versión registra el cambio de status Open → Managing (old → new).
		found = False
		for v in versions:
			for field, old, new in json.loads(v.data).get("changed", []):
				if field == "status" and old == "Open" and new == "Managing":
					found = True
		self.assertTrue(found)

	def test_register_reads_risks(self):
		p = _project("PR Register")
		_risk(p, description="R1", probability="High likelihood", impact="High")
		_risk(p, description="R2", probability="Low likelihood", impact="Low")
		_columns, data = register_execute({"project": p})
		rows = [d for d in data if d["project"] == p]
		self.assertEqual(len(rows), 2)
		self.assertTrue(any(d["exposure"] == "High exposure" for d in rows))

	def test_register_status_filter(self):
		p = _project("PR RegFilter")
		r = _risk(p, description="R", probability="High likelihood", impact="High")
		r.status = "Closed"
		r.update_note = "Riesgo cerrado tras mitigación."
		r.save()
		_columns, data = register_execute({"project": p, "status": "Open"})
		self.assertEqual(len([d for d in data if d["project"] == p]), 0)

	def test_p4_read_and_write(self):
		owner = _user("pr_owner@example.com")
		stranger = _user("pr_stranger@example.com")
		p = _project("PR P4", owner=owner)
		doc = _risk(p, description="R")
		self.assertTrue(has_permission_risk(doc, "read", owner))
		self.assertFalse(has_permission_risk(doc, "read", stranger))
		self.assertTrue(has_permission_risk(doc, "write", owner))
		self.assertFalse(has_permission_risk(doc, "write", stranger))
		self.assertFalse(has_permission_risk(doc, "share", owner))
