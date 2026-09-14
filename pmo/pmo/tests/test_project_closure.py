# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0014 D4 — PMO Project Closure. Datos ficticios.

Cubre: congelado al submit (snapshot no economico compuesto desde build_project_control + hash), aislamiento
economico por permlevel (economia NO legible con solo READ del Project), guard de estado terminal
(Completed/Cancelled), integridad del hash contra el JSON congelado, un-Closure-por-Project, P4 owner-only,
lifecycle terminal -> closed, y Print Format inmutable (renderiza solo desde la evidencia congelada).
"""

import hashlib
import json

import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.baseline import snapshot_hash
from pmo.governance import LIFECYCLE_CLOSED, derive_lifecycle_state
from pmo.permissions import has_permission_closure
from pmo.pmo.doctype.pmo_project_closure.pmo_project_closure import (
	CLOSURE_CHECKLIST_FIELDS,
	build_closure_snapshot,
)


def _open_cr(project, state, docstatus=0):
	cr = frappe.get_doc(
		{"doctype": "PMO Change Request", "project": project, "title": "C", "reason": "R"}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		"PMO Change Request",
		cr.name,
		{"workflow_state": state, "docstatus": docstatus},
		update_modified=False,
	)
	return cr


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


def _project(name, owner="Administrator", status="Completed"):
	pid = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": name,
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": status,
			}
		)
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", pid, "owner", owner, update_modified=False)
	frappe.db.set_value("Project", pid, "status", status, update_modified=False)
	return pid


def _closure(project, **kw):
	# Por defecto: aceptación formal + checklist completo (para emitir). Cualquiera se puede sobreescribir.
	data = {
		"doctype": "PMO Project Closure",
		"project": project,
		"closure_date": kw.get("closure_date", "2026-03-31"),
		"final_result": kw.get("final_result", "Delivered"),
		"accepted_by": kw.get("accepted_by", "Cliente"),
		"accepted_on": kw.get("accepted_on", "2026-03-31"),
	}
	for fn in CLOSURE_CHECKLIST_FIELDS:
		data[fn] = kw.get(fn, 1)
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	return doc


class TestProjectClosure(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_submit_freezes_snapshot_non_economic(self):
		p = _project("CLS Freeze")
		doc = _closure(p)
		self.assertFalse(doc.snapshot_hash)
		doc.submit()
		self.assertTrue(doc.snapshot_hash)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertTrue(doc.issued_at)
		snap = json.loads(doc.snapshot)
		self.assertEqual(snap["snapshot_schema_version"], 1)
		self.assertIn("schedule", snap)
		self.assertIn("effort", snap)
		self.assertIn("changes", snap)
		# La economía NO está en el snapshot no-económico (aislada en economics_snapshot).
		self.assertNotIn("economics", snap)
		self.assertNotIn("authorized_revenue", doc.snapshot)
		# La evidencia económica sí se congela, en su campo restringido.
		self.assertTrue(doc.economics_snapshot)
		eco = json.loads(doc.economics_snapshot)
		self.assertEqual(eco["as_of"], "current_at_issuance")

	def test_economics_snapshot_hash_matches_frozen_json(self):
		# Integridad del snapshot ECONÓMICO contra su JSON congelado (leído como Administrator = con gate).
		p = _project("CLS EcoHash")
		doc = _closure(p)
		doc.submit()
		self.assertTrue(doc.economics_snapshot)
		self.assertEqual(
			doc.economics_snapshot_hash,
			hashlib.sha256(doc.economics_snapshot.encode("utf-8")).hexdigest(),
		)

	def test_economics_isolated_by_permlevel(self):
		pu = _user("cls_pu@example.com", roles=["Projects User"])
		eu = _user("cls_eco@example.com", roles=["PMO Executive Access"])  # rol económico + lectura global
		p = _project("CLS Iso", owner=pu)
		doc = _closure(p)
		doc.submit()  # emitido por Administrator (con gate) → economía capturada

		# (a) permlevel: el Projects User no accede al nivel 1; el usuario económico sí.
		frappe.set_user(pu)
		self.assertNotIn(1, doc.get_permlevel_access("read"))
		frappe.set_user(eu)
		self.assertIn(1, doc.get_permlevel_access("read"))

		# (b) vía normal de lectura/serialización: apply_fieldlevel_read_permissions elimina los campos
		# económicos para el usuario sin gate y los conserva para el usuario con gate.
		frappe.set_user(pu)
		d_pu = frappe.get_doc("PMO Project Closure", doc.name)
		d_pu.apply_fieldlevel_read_permissions()
		self.assertIsNone(d_pu.get("economics_snapshot"))
		self.assertIsNone(d_pu.get("economics_snapshot_hash"))
		frappe.set_user(eu)
		d_eu = frappe.get_doc("PMO Project Closure", doc.name)
		d_eu.apply_fieldlevel_read_permissions()
		self.assertTrue(d_eu.get("economics_snapshot"))

		# (c) Print Format: el usuario sin gate NO ve economía en el printable, ni la sección ni cifras.
		# (El acceso económico de los usuarios con gate es por el campo `economics_snapshot`, prueba (b);
		# el printable no expone economía — defensa por permlevel + gate en la plantilla.)
		frappe.set_user(pu)
		html_pu = frappe.get_print("PMO Project Closure", doc.name, print_format="PMO Project Closure")
		self.assertNotIn("Economic evidence", html_pu)
		self.assertNotIn("Authorized revenue", html_pu)
		frappe.set_user("Administrator")

	def test_reject_closure_on_non_terminal_project(self):
		p = _project("CLS Open", status="Open")
		doc = _closure(p)
		# Un Project no terminal (Open) debe rechazar el submit del Closure.
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_hash_matches_frozen_json_not_live(self):
		p = _project("CLS Hash")
		doc = _closure(p)
		doc.submit()
		self.assertEqual(doc.snapshot_hash, hashlib.sha256(doc.snapshot.encode("utf-8")).hexdigest())
		frozen, frozen_hash = doc.snapshot, doc.snapshot_hash
		frappe.db.set_value("Project", p, "expected_end_date", "2027-12-31", update_modified=False)
		doc.reload()
		self.assertEqual(doc.snapshot, frozen)
		self.assertEqual(doc.snapshot_hash, frozen_hash)

	def test_completed_with_closure_is_closed(self):
		p = _project("CLS Completed", status="Completed")
		_closure(p).submit()
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSED)

	def test_cancelled_with_closure_is_closed(self):
		p = _project("CLS Cancelled", status="Cancelled")
		_closure(p).submit()
		self.assertEqual(derive_lifecycle_state(p), LIFECYCLE_CLOSED)

	def test_one_closure_per_project(self):
		p = _project("CLS Unique")
		_closure(p).submit()
		with self.assertRaises(ValidationError):
			_closure(p)

	def test_p4_read_and_write(self):
		owner = _user("cls_owner@example.com")
		stranger = _user("cls_stranger@example.com")
		p = _project("CLS P4", owner=owner)
		doc = _closure(p)
		self.assertTrue(has_permission_closure(doc, "read", owner))
		self.assertFalse(has_permission_closure(doc, "read", stranger))
		self.assertTrue(has_permission_closure(doc, "submit", owner))
		self.assertFalse(has_permission_closure(doc, "submit", stranger))
		self.assertFalse(has_permission_closure(doc, "share", owner))

	def test_print_format_immutable(self):
		p = _project("CLS Print")
		doc = _closure(p)
		doc.submit()
		html1 = frappe.get_print("PMO Project Closure", doc.name, print_format="PMO Project Closure")
		# El forecast/final congelado aparece en la salida.
		frozen_end = json.loads(doc.snapshot)["schedule"]["forecast_end"]
		if frozen_end:
			self.assertIn(str(frozen_end), html1)
		# Cambiar el Project despues del submit NO cambia la salida histórica del Closure.
		frappe.db.set_value("Project", p, "expected_end_date", "2099-12-31", update_modified=False)
		html2 = frappe.get_print("PMO Project Closure", doc.name, print_format="PMO Project Closure")
		self.assertEqual(html1, html2)
		self.assertNotIn("2099-12-31", html2)

	# --- estructura / gates de Submit (bloque Closure checklist) ------------------

	def test_title_removed_from_doctype(self):
		self.assertIsNone(frappe.get_meta("PMO Project Closure").get_field("title"))

	def test_closure_date_mandatory(self):
		p = _project("CLS DateReq")
		doc = _closure(p)  # tiene fecha por default
		doc.closure_date = None
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.save()

	def test_completed_requires_accepted_by(self):
		p = _project("CLS AccBy", status="Completed")
		doc = _closure(p, accepted_by="")  # Completed sin aceptante
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_completed_requires_accepted_on(self):
		p = _project("CLS AccOn", status="Completed")
		doc = _closure(p, accepted_on="")  # Completed sin fecha de aceptación
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_checklist_incomplete_blocks_submit(self):
		p = _project("CLS Chk")
		doc = _closure(p, chk_documentation=0)  # un check pendiente
		with self.assertRaises(ValidationError):
			doc.submit()

	def test_open_change_request_states_block_closure(self):
		for st in ("Draft", "In Review", "Approved", "Implemented"):
			p = _project(f"CLS CR {st}")
			_open_cr(p, st)
			doc = _closure(p)
			with self.assertRaises(ValidationError):
				doc.submit()  # CR abierto bloquea el cierre

	def test_terminal_change_request_states_do_not_block_closure(self):
		for st in ("Rejected", "Closed"):
			p = _project(f"CLS CRT {st}")
			_open_cr(p, st)
			doc = _closure(p)
			doc.submit()  # Rejected/Closed no bloquean
			self.assertEqual(doc.docstatus, 1)

	def test_cancelled_open_state_cr_does_not_block_closure(self):
		# CR con workflow_state abierto pero cancelado (docstatus=2) NO bloquea el cierre.
		p = _project("CLS CRCancel")
		_open_cr(p, "In Review", docstatus=2)
		doc = _closure(p)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_checklist_included_in_snapshot_and_hash(self):
		p = _project("CLS ChkSnap")
		doc = _closure(p)
		doc.submit()
		snap = json.loads(doc.snapshot)
		self.assertIn("closure_checklist", snap)
		expected = {
			"pending_items_resolved_or_transferred",
			"operations_support_handover_completed",
			"contractual_legal_obligations_reviewed",
			"administrative_financial_close_reviewed",
			"project_documentation_completed",
			"closure_communicated_to_stakeholders",
			"resources_released_reassigned",
		}
		self.assertEqual(set(snap["closure_checklist"]), expected)
		self.assertTrue(all(snap["closure_checklist"].values()))  # todos confirmados al emitir
		# El hash cubre el checklist: cambiar cualquier confirmación cambia el snapshot/hash construido.
		all_true = {k: True for k in expected}
		one_false = dict(all_true, project_documentation_completed=False)
		h_all = snapshot_hash(build_closure_snapshot(p, "2026-03-31", all_true))
		h_one = snapshot_hash(build_closure_snapshot(p, "2026-03-31", one_false))
		self.assertNotEqual(h_all, h_one)

	def test_print_format_economic_as_of_placeholder(self):
		# El as_of económico se renderiza (Administrator pasa el gate); no queda "restricted; 0" ni "{0}".
		p = _project("CLS PFEco")
		doc = _closure(p)
		doc.submit()
		html = frappe.get_print("PMO Project Closure", doc.name, print_format="PMO Project Closure")
		self.assertIn("current_at_issuance", html)
		self.assertNotIn("restricted; 0)", html)
		self.assertNotIn("{0}", html)

	def test_human_evidence_in_snapshot_and_hash(self):
		p = _project("CLS HumanSnap")
		doc = _closure(p, final_result="Delivered on time", accepted_by="ACME", closure_observations="Notas")
		doc.submit()
		cap = json.loads(doc.snapshot)["captured"]
		for k in (
			"accepted_by",
			"accepted_on",
			"final_result",
			"pending_items_transferred",
			"closure_observations",
			"issued_by",
			"issued_at",
		):
			self.assertIn(k, cap)
		self.assertEqual(cap["final_result"], "Delivered on time")
		self.assertEqual(cap["accepted_by"], "ACME")
		self.assertEqual(cap["issued_by"], "Administrator")
		self.assertTrue(cap["issued_at"])  # emitido dentro del snapshot
		# El hash cubre la evidencia humana: cambiar cualquiera cambia el snapshot/hash construido.
		chk = {"pending_items_resolved_or_transferred": True}
		base = {
			"accepted_by": "A",
			"accepted_on": "2026-03-31",
			"final_result": "X",
			"pending_items_transferred": None,
			"closure_observations": None,
			"issued_by": "Administrator",
			"issued_at": "2026-03-31 10:00:00",
		}
		h1 = snapshot_hash(build_closure_snapshot(p, "2026-03-31", chk, base))
		h2 = snapshot_hash(build_closure_snapshot(p, "2026-03-31", chk, dict(base, final_result="Y")))
		self.assertNotEqual(h1, h2)

	def test_closure_date_not_future(self):
		p = _project("CLS Future")
		with self.assertRaises(ValidationError):
			_closure(p, closure_date="2999-01-01")

	def test_accepted_on_not_after_closure_date(self):
		p = _project("CLS AccAfter")
		with self.assertRaises(ValidationError):
			_closure(p, closure_date="2026-03-31", accepted_on="2026-06-30")

	def test_print_format_reads_from_frozen_snapshot(self):
		p = _project("CLS PFSnap")
		doc = _closure(p, final_result="Cerrado OK")
		doc.submit()
		html = frappe.get_print("PMO Project Closure", doc.name, print_format="PMO Project Closure")
		self.assertIn("Cerrado OK", html)  # el resultado final viene del snapshot congelado
