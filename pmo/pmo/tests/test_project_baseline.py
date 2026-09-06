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

from pmo.baseline import build_snapshot, get_effective_baseline, run_preflight, snapshot_hash
from pmo.permissions import has_permission_baseline


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


def _baseline(project, revision, btype="Original", supersedes=None, effective=None, submit=False):
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
	if submit:
		doc.submit()
	return doc


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

	def test_nonoriginal_requires_supersedes(self):
		p = _project("BL-P4")
		_baseline(p, "BL-001", submit=True)
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-002", btype="Approved Change")

	def test_supersedes_must_be_submitted(self):
		p = _project("BL-P5")
		draft = _baseline(p, "BL-001")  # NO submitted
		with self.assertRaises(ValidationError):
			_baseline(p, "BL-002", btype="Replan", supersedes=draft.name)

	def test_no_fork(self):
		p = _project("BL-P6")
		orig = _baseline(p, "BL-001", submit=True)
		_baseline(p, "BL-002", btype="Approved Change", supersedes=orig.name, submit=True)
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
		b2 = _baseline(p, "BL-002", btype="Approved Change", supersedes=b1.name, submit=True)
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
