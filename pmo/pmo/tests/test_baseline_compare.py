# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0005 D11 — Comparator Baseline ↔ Baseline. Datos ficticios.

Cubre el engine puro `compare_snapshots` (sobre snapshots v1 fabricados) y el endpoint
`compare_baselines` (P4: lectura en ambas + mismo Project; sobre snapshots ya almacenados).
"""

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from pmo.compare import compare_baselines, compare_snapshots


def _task(
	name, parent=None, wbs=1, start="2026-01-05", end="2026-01-09", hours=8.0, status="Open", assignments=None
):
	return {
		"name": name,
		"subject": f"T {name}",
		"description": "",
		"parent_task": parent,
		"wbs_order": wbs,
		"is_group": 0,
		"is_milestone": 0,
		"exp_start_date": start,
		"exp_end_date": end,
		"expected_time": hours,
		"duration": 0,
		"status": status,
		"depends_on": [],
		"assignments": assignments or [],
	}


def _snap(tasks, project=None):
	return {
		"snapshot_schema_version": 1,
		"project": project
		or {
			"name": "P",
			"expected_start_date": "2026-01-01",
			"expected_end_date": "2026-03-31",
			"status": "Open",
		},
		"tasks": tasks,
	}


def _assign(user, override=None, effective=8.0, employee=None):
	return {"user": user, "employee": employee, "override_hours": override, "effective_hours": effective}


class TestCompareSnapshots(IntegrationTestCase):
	def test_equal_snapshots_empty(self):
		snap = _snap([_task("T1")])
		diff = compare_snapshots(snap, snap)
		self.assertFalse(diff["has_changes"])
		self.assertEqual(diff["tasks_added"], [])
		self.assertEqual(diff["tasks_removed"], [])
		self.assertEqual(diff["tasks_changed"], [])
		self.assertEqual(diff["project_changes"], {})

	def test_task_added_and_removed(self):
		before = _snap([_task("T1")])
		after = _snap([_task("T1"), _task("T2")])
		d = compare_snapshots(before, after)
		self.assertEqual([t["name"] for t in d["tasks_added"]], ["T2"])
		self.assertEqual(d["tasks_removed"], [])
		# inverso
		d2 = compare_snapshots(after, before)
		self.assertEqual([t["name"] for t in d2["tasks_removed"]], ["T2"])

	def test_date_change(self):
		before = _snap([_task("T1", start="2026-01-05", end="2026-01-09")])
		after = _snap([_task("T1", start="2026-01-06", end="2026-01-12")])
		d = compare_snapshots(before, after)
		ch = d["tasks_changed"][0]["fields"]
		self.assertEqual(ch["exp_start_date"], {"from": "2026-01-05", "to": "2026-01-06"})
		self.assertEqual(ch["exp_end_date"], {"from": "2026-01-09", "to": "2026-01-12"})

	def test_hours_change(self):
		d = compare_snapshots(_snap([_task("T1", hours=8.0)]), _snap([_task("T1", hours=12.0)]))
		self.assertEqual(d["tasks_changed"][0]["fields"]["expected_time"], {"from": 8.0, "to": 12.0})

	def test_structure_change(self):
		before = _snap([_task("T1", parent=None, wbs=1)])
		after = _snap([_task("T1", parent="G1", wbs=3)])
		ch = compare_snapshots(before, after)["tasks_changed"][0]["fields"]
		self.assertEqual(ch["parent_task"], {"from": None, "to": "G1"})
		self.assertEqual(ch["wbs_order"], {"from": 1, "to": 3})

	def test_status_change(self):
		d = compare_snapshots(_snap([_task("T1", status="Open")]), _snap([_task("T1", status="Completed")]))
		self.assertEqual(d["tasks_changed"][0]["fields"]["status"], {"from": "Open", "to": "Completed"})

	def test_assignment_changes(self):
		before = _snap([_task("T1", assignments=[_assign("a@x.com", override=None, effective=8.0)])])
		after = _snap(
			[
				_task(
					"T1",
					assignments=[
						_assign("a@x.com", override=6.0, effective=6.0),  # cambia override + effective
						_assign("b@x.com", effective=4.0),  # añadido
					],
				)
			]
		)
		a = compare_snapshots(before, after)["tasks_changed"][0]["assignments"]
		self.assertEqual([x["user"] for x in a["added"]], ["b@x.com"])
		self.assertEqual(a["removed"], [])
		self.assertEqual(a["changed"][0]["user"], "a@x.com")
		self.assertIn("override_hours", a["changed"][0]["changes"])
		self.assertIn("effective_hours", a["changed"][0]["changes"])
		# eliminacion de asignado
		d2 = compare_snapshots(after, before)["tasks_changed"][0]["assignments"]
		self.assertEqual([x["user"] for x in d2["removed"]], ["b@x.com"])

	def test_project_date_change(self):
		before = _snap(
			[_task("T1")],
			project={
				"name": "P",
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-03-31",
				"status": "Open",
			},
		)
		after = _snap(
			[_task("T1")],
			project={
				"name": "P",
				"expected_start_date": "2026-01-01",
				"expected_end_date": "2026-04-30",
				"status": "Open",
			},
		)
		pc = compare_snapshots(before, after)["project_changes"]
		self.assertEqual(pc["expected_end_date"], {"from": "2026-03-31", "to": "2026-04-30"})

	def test_deterministic_order(self):
		before = _snap([_task("A"), _task("B")])
		after = _snap([_task("D"), _task("C"), _task("A"), _task("B", hours=99.0)])
		d = compare_snapshots(before, after)
		self.assertEqual([t["name"] for t in d["tasks_added"]], ["C", "D"])  # ordenado
		self.assertEqual([t["name"] for t in d["tasks_changed"]], ["B"])


class TestCompareBaselinesP4(IntegrationTestCase):
	def _user(self, email, roles=("Projects User",)):
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

	def _project(self, name, owner):
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

	def _leaf(self, subject, project, end="2026-01-09"):
		tid = frappe.db.exists("Task", {"subject": subject})
		if tid:
			return tid
		return (
			frappe.get_doc(
				{
					"doctype": "Task",
					"subject": subject,
					"project": project,
					"expected_time": 8,
					"exp_start_date": "2026-01-05",
					"exp_end_date": end,
					"status": "Open",
				}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)

	def _baseline(self, project, revision, btype="Original", supersedes=None, effective=None):
		doc = frappe.get_doc(
			{
				"doctype": "PMO Project Baseline",
				"project": project,
				"revision": revision,
				"baseline_type": btype,
				"supersedes_baseline": supersedes,
				"effective_date": effective or "2026-01-01",
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_compare_baselines_detects_change_and_p4(self):
		owner = self._user("cmp-owner@example.com")
		outsider = self._user("cmp-out@example.com")  # con rol pero sin visibilidad del Project
		p = self._project("CMP-P1", owner)
		task = self._leaf("CMP task", p, end="2026-01-09")
		b1 = self._baseline(p, "BL-001", effective="2026-01-01")
		# cambiar el plan y crear una segunda baseline (snapshot distinto)
		frappe.db.set_value("Task", task, "exp_end_date", "2026-01-20")
		b2 = self._baseline(p, "BL-002", btype="Replan", supersedes=b1.name, effective="2026-02-01")

		# owner: comparación válida y detecta el cambio de fecha
		frappe.set_user(owner)
		try:
			d = compare_baselines(b1.name, b2.name)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(d["has_changes"])
		changed = {t["name"]: t for t in d["tasks_changed"]}
		self.assertIn("exp_end_date", changed[task]["fields"])
		self.assertEqual(d["meta"]["before"]["name"], b1.name)

		# outsider: lectura P4 denegada sobre las baselines
		frappe.set_user(outsider)
		try:
			with self.assertRaises(FrappePermissionError):
				compare_baselines(b1.name, b2.name)
		finally:
			frappe.set_user("Administrator")

	def test_compare_baselines_rejects_cross_project(self):
		owner = self._user("cmp-owner2@example.com")
		p1 = self._project("CMP-P2", owner)
		p2 = self._project("CMP-P3", owner)
		self._leaf("CMP p2 task", p1)
		self._leaf("CMP p3 task", p2)
		b1 = self._baseline(p1, "BL-001")
		b2 = self._baseline(p2, "BL-001")
		with self.assertRaises(ValidationError):
			compare_baselines(b1.name, b2.name)
