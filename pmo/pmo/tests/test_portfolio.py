# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Portfolio (salud multi-proyecto, ronda product-readiness).

Puros: `_health` (semáforo) y `_summary` (conteos). Integración: P4 (normal ve solo sus proyectos;
executive ve todos), filtro de completados, y forma de fila (esfuerzo Planned/Actual, salud, sin baseline).
Reutiliza `build_status_report`; no duplica motor."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.pmo.report.pmo_portfolio.pmo_portfolio import (
	HEALTH_AT_RISK,
	HEALTH_OFF_TRACK,
	HEALTH_ON_TRACK,
	_health,
	_summary,
	execute,
)


class TestPortfolioPure(unittest.TestCase):
	def test_health_off_track(self):
		self.assertEqual(_health(None, 3, 0, 0), HEALTH_OFF_TRACK)  # slip vs compromiso
		self.assertEqual(_health(None, None, 1, 0), HEALTH_OFF_TRACK)  # vencidas
		self.assertEqual(_health(None, None, 0, 2), HEALTH_OFF_TRACK)  # forecast excede compromiso

	def test_health_at_risk_and_on_track(self):
		self.assertEqual(_health(5, None, 0, 0), HEALTH_AT_RISK)  # solo slip vs baseline
		self.assertEqual(_health(None, None, 0, 0), HEALTH_ON_TRACK)
		self.assertEqual(_health(-3, -2, 0, 0), HEALTH_ON_TRACK)  # adelantos no penalizan

	def test_summary_counts(self):
		data = [
			{"health": HEALTH_OFF_TRACK, "has_baseline": True},
			{"health": HEALTH_AT_RISK, "has_baseline": False},
			{"health": HEALTH_ON_TRACK, "has_baseline": False},
		]
		cards = {c["label"]: c for c in _summary(data)}
		self.assertEqual(cards["Proyectos"]["value"], 3)
		self.assertEqual(cards["Desviados"]["value"], 1)
		self.assertEqual(cards["En riesgo"]["value"], 1)
		self.assertEqual(cards["Sin línea base"]["value"], 2)


def _user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)
	return email


def _project(name, owner, status="Open"):
	p = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", p, {"owner": owner, "status": status})
	return p


def _task(subject, project, expected=0, actual=0):
	t = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": project,
			"expected_time": expected,
			"status": "Open",
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	if actual:
		frappe.db.set_value("Task", t.name, "actual_time", actual)
	return t.name


class TestPortfolioP4(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def _run(self, observer, **filters):
		frappe.set_user(observer)
		try:
			return execute(filters)[1]
		finally:
			frappe.set_user("Administrator")

	def test_normal_sees_only_own_projects(self):
		obs = _user("pf-obs@example.com", ["Projects User"])
		vis = _project("PF-VIS", owner=obs)
		hid = _project("PF-HID", owner="Administrator")
		names = {r["project"] for r in self._run(obs)}
		self.assertIn(vis, names)
		self.assertNotIn(hid, names)

	def test_executive_sees_hidden_too(self):
		obs = _user("pf-obs@example.com", ["Projects User"])
		# ejecutivo real = acceso ejecutivo PMO + rol base de lectura de Project
		exec_user = _user("pf-exec@example.com", ["PMO Executive Access", "Projects User"])
		vis = _project("PF-VIS", owner=obs)
		hid = _project("PF-HID", owner="Administrator")
		names = {r["project"] for r in self._run(exec_user)}
		self.assertIn(vis, names)
		self.assertIn(hid, names)

	def test_completed_excluded_unless_flag(self):
		obs = _user("pf-obs@example.com", ["Projects User"])
		done = _project("PF-DONE", owner=obs, status="Completed")
		self.assertNotIn(done, {r["project"] for r in self._run(obs)})
		self.assertIn(done, {r["project"] for r in self._run(obs, include_completed=1)})

	def test_row_shape_effort_and_health(self):
		obs = _user("pf-obs@example.com", ["Projects User"])
		p = _project("PF-EFFORT", owner=obs)
		_task("PF-T1", p, expected=10, actual=4)
		row = next(r for r in self._run(obs) if r["project"] == p)
		self.assertEqual(row["planned_hours"], 10.0)
		self.assertEqual(row["actual_hours"], 4.0)
		self.assertEqual(row["pct_consumed"], 40.0)
		self.assertEqual(row["health"], HEALTH_ON_TRACK)  # sin baseline/vencidas/compromiso
		self.assertFalse(row["has_baseline"])
