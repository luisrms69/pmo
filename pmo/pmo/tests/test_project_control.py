# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.project_control (compositor canónico, ADR-0011).

Builder `build_project_control` + secciones + endpoint + template. Composición sobre motores existentes
(build_status_report, pmo.health), sin recalcular; P4 en el chokepoint; ausencia de dato → None."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from pmo.health import HEALTH_AT_RISK, HEALTH_DEVIATED, HEALTH_ON_TRACK, _health
from pmo.pmo.report.pmo_portfolio.pmo_portfolio import _health as portfolio_health
from pmo.project_control import (
	_executive_section,
	_scope_changes_section,
	build_project_control,
	get_executive_html,
)

KPI_KEYS = {
	"health",
	"health_label",
	"percent_complete",
	"tasks_due_by_cutoff_pct",
	"slip_baseline_days",
	"slip_committed_days",
	"compliance_pct",
	"overdue_tasks",
	"forecast_exceeds",
	"planned_hours",
	"actual_hours",
	"hours_consumed_pct",
}


def _sr(baseline=True, overdue=2, due=5, done=3, total=8, slip_bl=4, slip_cm=1, exceeds=0, actual=100):
	"""Forma canónica simulada de build_status_report (para mapeo determinista)."""
	tvb = [{"name": f"T{i}"} for i in range(total)]
	return {
		"status_date": "2026-09-11",
		"baseline": {"name": "BL", "expected_end_date": "2026-10-01"} if baseline else None,
		"current": {"expected_end_date": "2026-10-05"},
		"committed_end_date": "2026-09-30",
		"note": None,
		"indicators": {
			"final_date_slip_days": slip_bl,
			"slip_vs_committed_days": slip_cm,
			"tasks_overdue_at_cutoff": {"count": overdue},
			"forecast_exceeds_commitment": {"count": exceeds},
			"tasks_vs_baseline": tvb,
			"counts": {"baseline_due_by_cutoff": due, "completed_by_cutoff": done},
			"actual_hours_to_date": actual,
		},
	}


def _leaf_tasks(rows=None):
	"""Router de frappe.get_list para Task (planned hours). Delega el resto a la función real."""
	real_gl = frappe.get_list

	def gl(*args, **kwargs):
		dt = kwargs.get("doctype", args[0] if args else None)
		if dt == "Task":
			return rows if rows is not None else [{"expected_time": 30}, {"expected_time": 20}]
		return real_gl(*args, **kwargs)

	return gl


class TestHealthCanonical(IntegrationTestCase):
	def test_single_source_matches_portfolio(self):
		# Fuente única (pmo.health): el _health del builder y el re-exportado por pmo_portfolio coinciden.
		for sb in (None, -1, 0, 1, 3):
			for sc in (None, 0, 1):
				for od in (0, 1):
					for ex in (0, 1):
						self.assertEqual(_health(sb, sc, od, ex), portfolio_health(sb, sc, od, ex))

	def test_none_is_not_zero(self):
		self.assertEqual(_health(None, None, 0, 0), HEALTH_ON_TRACK)
		self.assertEqual(_health(None, 1, 0, 0), HEALTH_DEVIATED)
		self.assertEqual(_health(3, None, 0, 0), HEALTH_AT_RISK)


class TestExecutiveSection(IntegrationTestCase):
	"""_executive_section refleja exactamente build_status_report (mock) y corrige la fuente de horas."""

	def test_keys_and_mapping(self):
		sr = _sr(baseline=True, overdue=2, due=5, done=3, total=8, actual=100)
		with (
			patch("pmo.project_control.frappe.db.get_value", return_value=40),
			patch("pmo.project_control.frappe.get_list", side_effect=_leaf_tasks()),
		):
			kp = _executive_section("X", sr, sr["indicators"])["kpis"]
		self.assertEqual(set(kp.keys()), KPI_KEYS)
		self.assertEqual(kp["percent_complete"], 40)
		self.assertEqual(kp["overdue_tasks"], 2)  # == build_status_report
		self.assertEqual(kp["tasks_due_by_cutoff_pct"], round(5 / 8 * 100))
		self.assertEqual(kp["compliance_pct"], round(3 / 5 * 100))
		# Horas reales = actual_hours_to_date (NO Project.actual_time ni Σ Task.actual_time)
		self.assertEqual(kp["actual_hours"], 100)
		self.assertEqual(kp["planned_hours"], 50)
		self.assertEqual(kp["hours_consumed_pct"], round(100 / 50 * 100))

	def test_no_baseline_yields_none(self):
		sr = _sr(baseline=False, due=None, done=None, total=0, actual=5)
		with (
			patch("pmo.project_control.frappe.db.get_value", return_value=10),
			patch("pmo.project_control.frappe.get_list", side_effect=_leaf_tasks()),
		):
			kp = _executive_section("X", sr, sr["indicators"])["kpis"]
		for key in ("tasks_due_by_cutoff_pct", "compliance_pct", "overdue_tasks"):
			self.assertIsNone(kp[key], f"{key} debe ser None sin baseline")
		self.assertEqual(kp["percent_complete"], 10)

	def test_no_tasks_no_zero_division(self):
		sr = _sr(baseline=False, total=0, actual=0)
		with (
			patch("pmo.project_control.frappe.db.get_value", return_value=0),
			patch("pmo.project_control.frappe.get_list", side_effect=_leaf_tasks(rows=[])),
		):
			kp = _executive_section("X", sr, sr["indicators"])["kpis"]
		self.assertEqual(kp["planned_hours"], 0)
		self.assertIsNone(kp["hours_consumed_pct"])  # planned=0 → None, no ZeroDivision


class TestScopeChanges(IntegrationTestCase):
	"""scope_changes: audience=portal oculta Draft; internal los incluye (ADR-0011 D3)."""

	def _crs(self):
		return [
			frappe._dict(name="CR-1", title="A", workflow_state="Draft", request_date="2026-09-03"),
			frappe._dict(name="CR-2", title="B", workflow_state="Approved", request_date="2026-09-02"),
			frappe._dict(name="CR-3", title="C", workflow_state="Rejected", request_date="2026-09-01"),
		]

	def _router(self, crs):
		real_gl = frappe.get_list

		def gl(*args, **kwargs):
			dt = kwargs.get("doctype", args[0] if args else None)
			if dt == "PMO Change Request":
				return list(crs)
			return real_gl(*args, **kwargs)

		return gl

	def test_internal_includes_draft(self):
		with patch("pmo.project_control.frappe.get_list", side_effect=self._router(self._crs())):
			out = _scope_changes_section("X", "internal")
		self.assertEqual(len(out["change_requests"]), 3)

	def test_portal_excludes_draft(self):
		with patch("pmo.project_control.frappe.get_list", side_effect=self._router(self._crs())):
			out = _scope_changes_section("X", "portal")
		states = {c["workflow_state"] for c in out["change_requests"]}
		self.assertNotIn("Draft", states)
		self.assertEqual(len(out["change_requests"]), 2)  # Approved + Rejected (Rejected SÍ es historial)


class TestBuilderStructureAndP4(IntegrationTestCase):
	def _routers(self):
		real_gl, real_ga = frappe.get_list, frappe.get_all

		def gl(*a, **k):
			return (
				[]
				if k.get("doctype", a[0] if a else None) in ("Task", "PMO Change Request")
				else real_gl(*a, **k)
			)

		def ga(*a, **k):
			return [] if k.get("doctype", a[0] if a else None) == "Task" else real_ga(*a, **k)

		def gv(*a, **k):
			# project meta (as_dict) / percent_complete / pmo_status_date → valores neutros
			if k.get("as_dict"):
				return frappe._dict(
					{"project_name": "P", "status": "Open", "company": None, "customer": None}
				)
			return None

		return gl, ga, gv

	def test_structure_and_sections(self):
		gl, ga, gv = self._routers()
		with (
			patch("pmo.project_control.build_status_report", return_value=_sr(baseline=False, total=0)),
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			full = build_project_control("X", cutoff="2026-09-11")
			subset = build_project_control("X", cutoff="2026-09-11", sections=["project", "executive"])
		self.assertEqual(
			set(full.keys()),
			{"audience", "cutoff", "note", "project", "executive", "schedule", "scope_changes"},
		)
		self.assertEqual(set(subset.keys()), {"audience", "cutoff", "note", "project", "executive"})
		self.assertEqual(full["cutoff"], "2026-09-11")

	def test_p4_propagates(self):
		# build_status_report es el chokepoint P4: si lanza PermissionError, el builder y el endpoint la propagan.
		with patch("pmo.project_control.build_status_report", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				build_project_control("X")
		with patch("pmo.project_control.build_status_report", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				get_executive_html("X")

	def test_no_ignore_permissions_in_source(self):
		# Guard estructural: el compositor no debe saltarse permisos.
		import pmo.project_control as mod

		src = open(mod.__file__).read()
		# El patrón peligroso es el kwarg de bypass, no la mención en comentarios/docstring.
		self.assertNotIn("ignore_permissions=True", src)
		self.assertNotIn("ignore_permissions =", src)


class TestRenderer(IntegrationTestCase):
	"""El template canónico representa el contexto; None → ausencia (—), no cero."""

	def _pc(self, has_baseline=True):
		return {
			"audience": "internal",
			"cutoff": "2026-09-11",
			"note": None,
			"project": {
				"name": "PROJ-X",
				"project_name": "Proyecto X",
				"status": "Open",
				"company": None,
				"customer": None,
				"customer_name": None,
				"has_baseline": has_baseline,
				"forecast_end": "2026-10-05",
				"baseline_end": "2026-10-01" if has_baseline else None,
				"committed_end": "2026-09-30",
			},
			"executive": {
				"kpis": {
					"health": "on_track",
					"health_label": "On track",
					"percent_complete": 40,
					"tasks_due_by_cutoff_pct": 62 if has_baseline else None,
					"slip_baseline_days": 4 if has_baseline else None,
					"slip_committed_days": 1,
					"compliance_pct": 60 if has_baseline else None,
					"overdue_tasks": 2 if has_baseline else None,
					"forecast_exceeds": 0,
					"planned_hours": 50.0,
					"actual_hours": 100.0,
					"hours_consumed_pct": 200,
				}
			},
			"schedule": {
				"counts": {"total": 8, "completed": 3, "active": 4, "overdue_at_cutoff": 2},
				"milestones": [],
				"relevant_tasks": [],
				"omitted_tasks": 0,
				"total_baseline_tasks": 8 if has_baseline else 0,
				"gantt": {"tasks": [], "min_start": None, "max_end": None},
			},
			"scope_changes": {"change_requests": []},
		}

	def _render(self, pc):
		return frappe.render_template("pmo/templates/project_control/executive.html", {"pc": pc})

	def test_renders_with_baseline(self):
		html = self._render(self._pc(has_baseline=True))
		self.assertIn("Proyecto X", html)
		self.assertIn("2026-10-01", html)  # baseline_end
		self.assertIn("40%", html)  # progress

	def test_renders_without_baseline_none_as_dash(self):
		html = self._render(self._pc(has_baseline=False))
		self.assertIn("no baseline", html)
		# KPIs de baseline None → "—" (ausencia), NUNCA "0%"
		self.assertNotIn("0%", html.replace("100%", "").replace("40%", "").replace("200%", ""))
		self.assertIn("—", html)
