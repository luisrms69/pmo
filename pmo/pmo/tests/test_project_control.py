# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.project_control (compositor canónico, ADR-0011).

Builder `build_project_control` + secciones + endpoint + template. Composición sobre motores existentes
(build_status_report, pmo.health), sin recalcular; P4 en el chokepoint; ausencia de dato → None."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from pmo.health import HEALTH_AT_RISK, HEALTH_DEVIATED, HEALTH_ON_TRACK, _health
from pmo.pmo.report.pmo_portfolio.pmo_portfolio import _health as portfolio_health
from pmo.project_control import (
	DEFAULT_SECTIONS,
	SECTION_COSTS,
	_assigned_task_names,
	_comparative_gantt,
	_costs_section,
	_exc_deviation,
	_exc_type,
	_execution_state,
	_executive_section,
	_planning_section,
	_schedule_deviations,
	_scope_changes_section,
	build_project_control,
	get_executive_html,
	get_financial_html,
	get_schedule_html,
	get_summary_html,
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


class TestPlanningSection(IntegrationTestCase):
	"""Planning Maturity (5 componentes, promedio de evaluables) + tareas activas sin responsable."""

	def _leaves(self):
		# T1/T2 con responsable; T3 activa sin responsable; T4 Completed sin responsable (no es alerta).
		return [
			frappe._dict(
				name="T1",
				subject="T1",
				status="Open",
				exp_start_date="2026-09-01",
				exp_end_date="2026-09-05",
				expected_time=5,
			),
			frappe._dict(
				name="T2",
				subject="T2",
				status="Working",
				exp_start_date="2026-09-02",
				exp_end_date="2026-09-06",
				expected_time=0,
			),
			frappe._dict(
				name="T3",
				subject="T3",
				status="Open",
				exp_start_date="2026-09-03",
				exp_end_date=None,
				expected_time=0,
			),
			frappe._dict(
				name="T4",
				subject="T4",
				status="Completed",
				exp_start_date=None,
				exp_end_date=None,
				expected_time=0,
			),
		]

	def _mocks(self, leaves, assigned, baseline_names=None):
		real_gl, real_ga, real_gv = frappe.get_list, frappe.get_all, frappe.db.get_value

		def gl(*a, **k):
			return leaves if k.get("doctype", a[0] if a else None) == "Task" else real_gl(*a, **k)

		def ga(*a, **k):
			if k.get("doctype", a[0] if a else None) == "ToDo":
				return [frappe._dict(reference_name=n) for n in assigned]
			return real_ga(*a, **k)

		def gv(*a, **k):
			if baseline_names is not None:
				return json.dumps({"tasks": [{"name": n} for n in baseline_names]})
			return real_gv(*a, **k)

		return gl, ga, gv

	def test_components_and_maturity(self):
		gl, ga, gv = self._mocks(self._leaves(), assigned=["T1", "T2"], baseline_names=["T1", "T2", "T3"])
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": {"name": "BL"}})
		c = pl["components"]
		self.assertEqual(c["with_responsible_pct"], 50)  # T1,T2 / 4
		self.assertEqual(c["with_start_pct"], 75)  # T1,T2,T3 / 4
		self.assertEqual(c["with_end_pct"], 50)  # T1,T2 / 4
		self.assertEqual(c["with_estimate_pct"], 25)  # T1 / 4
		self.assertEqual(c["in_baseline_pct"], 75)  # T1,T2,T3 / 4 (T4 nueva, no en baseline)
		self.assertEqual(pl["maturity_pct"], round((50 + 75 + 50 + 25 + 75) / 5))  # 55

	def test_unassigned_excludes_completed(self):
		gl, ga, gv = self._mocks(self._leaves(), assigned=["T1", "T2"], baseline_names=["T1"])
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": {"name": "BL"}})
		# T3 (Open, sin responsable) es alerta; T4 (Completed, sin responsable) NO.
		self.assertEqual(pl["unassigned"]["count"], 1)
		self.assertEqual([t["name"] for t in pl["unassigned"]["tasks"]], ["T3"])

	def test_no_baseline_component_none(self):
		gl, ga, gv = self._mocks(self._leaves(), assigned=["T1", "T2"], baseline_names=None)
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": None})
		self.assertIsNone(pl["components"]["in_baseline_pct"])  # None, no cero
		self.assertEqual(pl["maturity_pct"], round((50 + 75 + 50 + 25) / 4))  # promedio de 4 evaluables

	def test_responsible_uses_open_todo_only(self):
		# Guard de semántica: "responsable" = ToDo Open (no != Cancelled, que incluiría Closed).
		captured = {}

		def ga(*a, **k):
			captured.update(k.get("filters") or {})
			return []

		with patch("pmo.project_control.frappe.get_all", side_effect=ga):
			_assigned_task_names(["T1"])
		self.assertEqual(captured.get("status"), "Open")

	def test_no_tasks_all_none(self):
		gl, ga, gv = self._mocks([], assigned=[], baseline_names=None)
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": None})
		self.assertIsNone(pl["maturity_pct"])
		self.assertTrue(all(v is None for v in pl["components"].values()))
		self.assertEqual(pl["unassigned"]["count"], 0)


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
			{"audience", "cutoff", "note", "project", "executive", "schedule", "planning", "scope_changes"},
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
			# CR con los TRES impactos: recorre la rama de bits que causó la regresión de shadowing de `_`.
			"scope_changes": {
				"change_requests": [
					{
						"name": "CR-9",
						"title": "Cambio con impactos",
						"workflow_state": "Approved",
						"request_date": "2026-09-01",
						"impact_summary": "Alcance ampliado",
						"impact_hours": 12,
						"impact_days": 5,
						"impact_amount": 10000,
						"currency": "MXN",
						"baseline_before": "BL0",
						"baseline_after": "BL1",
					}
				]
			},
			"planning": {
				"maturity_pct": 55 if has_baseline else 50,
				"components": {
					"with_responsible_pct": 50,
					"with_start_pct": 75,
					"with_end_pct": 50,
					"with_estimate_pct": 25,
					"in_baseline_pct": 75 if has_baseline else None,
				},
				"unassigned": {"count": 1, "tasks": [{"name": "T3", "subject": "T3"}]},
			},
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
		# KPIs de baseline None → ausencia: la tarjeta muestra "—" y el componente de baseline "Not evaluable"
		self.assertIn("—", html)
		self.assertIn("Not evaluable", html)
		# Y NO debe pintar esas ausencias como "0%": las tarjetas de tasks_due/compliance rinden "—".
		self.assertIn('<div class="val">—</div>', html)

	def test_planning_section_renders(self):
		html = self._render(self._pc(has_baseline=True))
		self.assertIn("Planning quality", html)
		self.assertIn("Planning Maturity", html)
		self.assertIn("active task(s) without owner", html)  # excepción visible (unassigned.count=1)

	def test_change_request_with_impacts_renders_and_translation_survives(self):
		# Regresión: un CR con impact_hours/days/amount recorre la rama que shadoweaba `_` (traducción).
		# El template completo debe renderizar sin excepción, mostrar los impactos y seguir traduciendo
		# etiquetas POSTERIORES (prueba de que `_` no quedó sobrescrito por el append de bits).
		html = self._render(self._pc(has_baseline=True))
		self.assertIn("Cambio con impactos", html)  # fila del CR (rama ejecutada)
		for token in ("12", "5", "10000"):  # impact_hours / impact_days / impact_amount
			self.assertIn(token, html)
		# `_()` sigue viva tras construir los bits: se renderizan encabezados traducibles posteriores.
		self.assertIn("Change Requests", html)
		self.assertIn("Planning quality", html)


class TestSummaryView(IntegrationTestCase):
	"""Pestaña Resumen (get_summary_html → resumen.html): reusa motores, es-MX, 4 bloques, drill-down.
	No toca executive.html/get_executive_html (Print Format intactos)."""

	def _ctx(self, with_derived=False):
		ctx = frappe._dict(
			{
				"audience": "internal",
				"cutoff": "2026-09-11",
				"note": None,
				"project": {
					"name": "PROJ-X",
					"project_name": "Proyecto X",
					"status": "Open",
					"customer_name": "Cliente Demo",
					"start_date": "2026-09-01",
					"committed_end": "2026-10-15",
					"forecast_end": "2026-10-30",
					"has_baseline": True,
					"baseline_end": "2026-10-01",
				},
				"executive": {
					"kpis": {
						"health": "on_track",
						"health_label": "On track",
						"percent_complete": 68,
						"overdue_tasks": 3,
						"planned_hours": 120.0,
						"actual_hours": 96.0,
						"slip_baseline_days": -2,
						"slip_committed_days": -2,
					}
				},
				"schedule": {
					"counts": {"overdue_at_cutoff": 3},
					"milestones": [{"slip_days": 3}, {"slip_days": 0}, {"slip_days": None}],
				},
				"risk": {
					"assessment_exists": True,
					"assessment": "PMO-RA-1",
					"assessment_state": "assessed",
					"open": 2,
					"high_exposure": 1,
					"no_owner": 0,
					"no_response": 1,
				},
				"governance": {
					"handoff": {"available": True, "reference": "PMO-HOF-1", "date": "2026-09-05"},
					"baseline": {"available": True, "reference": "BL-002", "date": "2026-09-06"},
					"closure": {"available": False, "reference": None, "date": None},
					"review": {"available": False, "reference": None, "date": None},
					"change_requests": {"total": 3, "open": 1},
					"lifecycle_state": "execution",
				},
			}
		)
		if with_derived:
			ctx["milestones_with_deviation"] = 1
			ctx["milestones_total"] = 3
			ctx["governance_flags"] = {
				"has_handoff": True,
				"needs_baseline": False,
				"needs_closure": False,
				"needs_review": False,
				"open_change_requests": 1,
			}
		return ctx

	def _render(self, pc):
		return frappe.render_template("pmo/templates/project_control/resumen.html", {"pc": pc})

	def test_endpoint_composition_and_derivation(self):
		flags = {
			"has_handoff": True,
			"needs_baseline": False,
			"needs_closure": False,
			"needs_review": False,
			"open_change_requests": 1,
		}
		with (
			patch("pmo.project_control.build_project_control", return_value=self._ctx()) as b,
			patch("pmo.project_control.governance_flags", return_value=flags),
		):
			html = get_summary_html("PROJ-X", cutoff="2026-09-11")
		_, kw = b.call_args
		# Resumen pide gobernanza + riesgo + cronograma; NUNCA economía (Financiera tiene su pestaña).
		self.assertIn("governance", kw["sections"])
		self.assertIn("risk", kw["sections"])
		self.assertIn("schedule", kw["sections"])
		self.assertNotIn("costs", kw["sections"])
		# Derivación de presentación: hitos con desviación = milestones con slip>0 (1 de 3).
		self.assertIn("1 / 3", html)
		self.assertIn("Avance del proyecto", html)
		self.assertIn("Gobernanza del proyecto", html)

	def test_render_blocks_and_semantics_es_mx(self):
		html = self._render(self._ctx(with_derived=True))
		# 1) Identidad y estado + 2) Avance + 3) Excepciones + 4) Gobernanza (es-MX)
		self.assertIn("Proyecto X", html)
		self.assertIn("Cliente Demo", html)
		self.assertIn("En plan", html)  # salud mapeada es-MX (no "On track")
		self.assertIn("68%", html)  # progreso
		self.assertIn("120 h", html)  # horas planificadas
		# Riesgos: señales existentes (sin agregado artificial de "requieren atención")
		self.assertIn("Sin responsable", html)
		self.assertIn("Sin tratamiento", html)
		self.assertNotIn("Requieren atención", html)
		self.assertNotIn("Requiere atención", html)
		# Cambios: solo totales / abiertas
		self.assertIn("Solicitudes totales", html)
		self.assertIn("Solicitudes abiertas", html)
		# Gobernanza: Acta de transferencia (NO "Charter"); Cierre/Revisión "No requerido"
		self.assertIn("Acta de transferencia", html)
		self.assertNotIn("Charter", html)
		self.assertIn("BL-002", html)  # línea base vigente
		self.assertIn("No requerido", html)  # closure/review no requeridos

	def test_no_costs_block_in_summary(self):
		# Economía vive en la pestaña Financiera: el Resumen no la muestra aunque el gate pasara.
		html = self._render(self._ctx(with_derived=True))
		for token in ("Situación económica", "Valor autorizado", "Facturado", "Costo real", "economics"):
			self.assertNotIn(token, html)


class TestScheduleView(IntegrationTestCase):
	"""Pestaña Estado / Cronograma: Gantt comparativo (línea base vs plan vigente), estado de ejecución y
	excepciones. Reutiliza motores; NO recalcula fechas/slips. Solo lectura."""

	def test_exc_type(self):
		# El tipo etiqueta la RAZÓN de la desviación temporal; prioriza vencida > desplazada/hito desviado >
		# adelantada > excede compromiso. Ya no clasifica composición (Fuera de línea base / Retirada): esos
		# cambios viven en el Gantt y no son desviaciones.
		self.assertEqual(_exc_type({"overdue_at_status_date": True, "slip_days": 3}), "Vencida")
		self.assertEqual(_exc_type({"is_milestone": 1, "slip_days": 4}), "Hito desviado")
		self.assertEqual(_exc_type({"slip_days": 2}), "Desplazada")
		self.assertEqual(_exc_type({"slip_days": -3}), "Adelantada")
		self.assertEqual(_exc_type({"exceeds_deadline": True, "slip_days": 0}), "Excede compromiso")
		# Un hito sin desviación no debe etiquetarse como desviación (además el filtro lo excluye del bloque).
		self.assertEqual(_exc_type({"is_milestone": 1, "slip_days": 0}), "—")
		self.assertEqual(_exc_type({"slip_days": 0}), "—")

	def test_exc_deviation_reference(self):
		# 2.1 — la desviación indica inequívocamente su referencia (línea base vs compromiso).
		self.assertEqual(_exc_deviation("Desplazada", {"slip_days": 5}), (5, "línea base"))
		self.assertEqual(_exc_deviation("Adelantada", {"slip_days": -2}), (-2, "línea base"))
		# «Excede compromiso» se mide contra la fecha comprometida, no contra baseline (evita el "0 d" ambiguo).
		self.assertEqual(
			_exc_deviation(
				"Excede compromiso",
				{"slip_days": 0, "current_exp_end_date": "2026-09-25", "pmo_deadline": "2026-09-20"},
			),
			(5, "compromiso"),
		)

	def test_schedule_deviations_only_real_deviations(self):
		"""«Desviaciones del cronograma» = SOLO desviaciones temporales reales. Un hito sin desviación, una
		tarea nueva sin desviación y una retirada NO aparecen por su sola clasificación (viven en el Gantt).
		Una añadida sí aparece si excede el compromiso, y entonces por ESA razón. La capacidad de detectar
		añadidas/retiradas/hitos sigue intacta (compare_snapshots); solo no contamina este bloque."""
		# Filas vs línea base ya anotadas (is_milestone / exceeds_deadline ya resueltos).
		annotated = [
			{
				"name": "PRUEBAS",
				"subject": "Pruebas",
				"overdue_at_status_date": True,
				"slip_days": 2,
				"is_milestone": 0,
				"exceeds_deadline": False,
				"baseline_exp_end_date": "2026-09-01",
				"current_exp_end_date": "2026-09-03",
				"pmo_deadline": None,
			},
			{
				"name": "REPLAN",
				"subject": "Reingeniería",
				"overdue_at_status_date": False,
				"slip_days": 4,
				"is_milestone": 0,
				"exceeds_deadline": False,
				"baseline_exp_end_date": "2026-09-10",
				"current_exp_end_date": "2026-09-14",
				"pmo_deadline": None,
			},
			# Hito SIN desviación (0 d vs línea base, no vencido, no excede) → NO debe aparecer.
			{
				"name": "HITO",
				"subject": "Entrega a cliente",
				"overdue_at_status_date": False,
				"slip_days": 0,
				"is_milestone": 1,
				"exceeds_deadline": False,
				"baseline_exp_end_date": "2026-09-20",
				"current_exp_end_date": "2026-09-20",
				"pmo_deadline": None,
			},
			# Tarea de línea base sin desviación → NO debe aparecer.
			{
				"name": "DISENO",
				"subject": "Diseño",
				"overdue_at_status_date": False,
				"slip_days": 0,
				"is_milestone": 0,
				"exceeds_deadline": False,
				"baseline_exp_end_date": "2026-09-05",
				"current_exp_end_date": "2026-09-05",
				"pmo_deadline": None,
			},
		]
		diff = {
			"tasks_added": [{"name": "DESPLIEGUE"}, {"name": "SOPORTE"}],
			"tasks_removed": [{"name": "CANCELADA"}],
		}

		def gv_all(dt, filters=None, fields=None, **k):
			# Añadidas (con is_group en el filtro): DESPLIEGUE excede compromiso; SOPORTE no.
			if filters and "is_group" in filters:
				return [
					frappe._dict(
						name="DESPLIEGUE",
						subject="Despliegue",
						status="Open",
						exp_end_date="2026-09-25",
						pmo_deadline="2026-09-20",
						is_milestone=0,
					),
					frappe._dict(
						name="SOPORTE",
						subject="Soporte extra",
						status="Open",
						exp_end_date="2026-09-10",
						pmo_deadline=None,
						is_milestone=0,
					),
				]
			# Estado vigente de las filas restantes.
			return [frappe._dict(name=n, status="Working") for n in filters["name"][1]]

		with (
			patch("pmo.project_control._annotate", return_value=annotated),
			patch("pmo.project_control.compare_snapshots", return_value=diff),
			patch("pmo.project_control._current_owners", return_value={}),
			patch("pmo.project_control.frappe.get_all", side_effect=gv_all),
		):
			out = _schedule_deviations("X", {"tasks_vs_baseline": annotated}, {"tasks": []}, {"tasks": []})

		by_name = {r["name"]: r for r in out}
		# Aparecen SOLO las desviaciones reales, cada una por su razón.
		self.assertEqual(set(by_name), {"PRUEBAS", "REPLAN", "DESPLIEGUE"})
		self.assertEqual(by_name["PRUEBAS"]["type"], "Vencida")
		self.assertEqual(by_name["REPLAN"]["type"], "Desplazada")
		self.assertEqual(by_name["REPLAN"]["dev_ref"], "línea base")
		self.assertEqual(by_name["DESPLIEGUE"]["type"], "Excede compromiso")
		self.assertEqual(by_name["DESPLIEGUE"]["dev_ref"], "compromiso")
		self.assertEqual(by_name["DESPLIEGUE"]["dev_days"], 5)
		# NO aparecen por su sola clasificación.
		self.assertNotIn("HITO", by_name)  # hito sin desviación
		self.assertNotIn("SOPORTE", by_name)  # añadida sin desviación (solo en el Gantt)
		self.assertNotIn("CANCELADA", by_name)  # retirada (solo en el Gantt)
		self.assertNotIn("DISENO", by_name)  # sin desviación

	def test_execution_state_buckets_and_exclusivity(self):
		leaves = [
			frappe._dict(name="A", status="Completed"),
			frappe._dict(name="B", status="Working"),  # en curso
			frappe._dict(name="C", status="Open"),  # vencida (tvb overdue)
			frappe._dict(name="D", status="Open"),  # pendiente
			frappe._dict(name="E", status="Overdue"),  # vencida (fallback nativo, no en tvb)
			frappe._dict(name="F", status="Cancelled"),  # excluida
		]
		tvb = {"C": {"overdue_at_status_date": True}, "B": {"overdue_at_status_date": False}}
		with patch("pmo.project_control.frappe.get_all", return_value=leaves):
			ex = _execution_state("X", tvb, has_baseline=True)
		self.assertEqual(ex["completadas"], 1)  # A
		self.assertEqual(ex["en_curso"], 1)  # B
		self.assertEqual(ex["vencidas"], 2)  # C (tvb) + E (nativo)
		self.assertEqual(ex["pendientes"], 1)  # D
		self.assertEqual(ex["total"], 5)  # F excluida
		self.assertEqual(ex["completadas"] + ex["en_curso"] + ex["vencidas"] + ex["pendientes"], ex["total"])
		self.assertEqual(ex["overdue_source"], "overdue_at_status_date")

	def test_execution_state_fallback_without_baseline(self):
		leaves = [frappe._dict(name="A", status="Overdue")]
		with patch("pmo.project_control.frappe.get_all", return_value=leaves):
			ex = _execution_state("X", {}, has_baseline=False)
		self.assertEqual(ex["vencidas"], 1)  # sin baseline → estado nativo Overdue
		self.assertIn("nativo", ex["overdue_source"])

	def test_comparative_gantt_bars_added_removed_milestone(self):
		live = [
			frappe._dict(
				name="T1",
				subject="T1",
				status="Working",
				exp_start_date="2026-09-01",
				exp_end_date="2026-09-10",
				progress=50,
				is_group=0,
				is_milestone=0,
				lft=1,
				parent_task=None,
			),
			frappe._dict(
				name="T2",
				subject="Hito",
				status="Open",
				exp_start_date="2026-09-20",
				exp_end_date="2026-09-20",
				progress=0,
				is_group=0,
				is_milestone=1,
				lft=2,
				parent_task=None,
			),
			frappe._dict(
				name="T3",
				subject="Nueva",
				status="Open",
				exp_start_date="2026-09-05",
				exp_end_date="2026-09-15",
				progress=0,
				is_group=0,
				is_milestone=0,
				lft=3,
				parent_task=None,
			),
		]
		baseline_snap = {
			"tasks": [
				{
					"name": "T1",
					"subject": "T1",
					"exp_start_date": "2026-08-25",
					"exp_end_date": "2026-09-05",
					"is_group": 0,
					"is_milestone": 0,
				},
				{
					"name": "T2",
					"subject": "Hito",
					"exp_start_date": "2026-09-15",
					"exp_end_date": "2026-09-15",
					"is_group": 0,
					"is_milestone": 1,
				},
				{
					"name": "T9",
					"subject": "Retirada",
					"exp_start_date": "2026-09-01",
					"exp_end_date": "2026-09-08",
					"is_group": 0,
					"is_milestone": 0,
				},
			]
		}
		tvb = {"T1": {"overdue_at_status_date": True, "slip_days": 5}, "T2": {"slip_days": 5}}
		with patch("pmo.project_control.frappe.get_list", return_value=live):
			g = _comparative_gantt("X", baseline_snap, {}, "2026-09-08", tvb)
		self.assertTrue(g["has_baseline"])
		rows = {r["name"]: r for r in g["tasks"]}
		self.assertEqual(len(g["tasks"]), 4)  # 3 vivas + 1 retirada
		# T1: dos barras + vencida
		self.assertIsNotNone(rows["T1"]["baseline_bar"])
		self.assertIsNotNone(rows["T1"]["current_bar"])
		self.assertTrue(rows["T1"]["overdue"])
		self.assertFalse(rows["T1"]["added"])
		# T2: hito con ambas referencias
		self.assertEqual(rows["T2"]["is_milestone"], 1)
		# T3: añadida (solo plan vigente)
		self.assertTrue(rows["T3"]["added"])
		self.assertIsNone(rows["T3"]["baseline_bar"])
		self.assertIsNotNone(rows["T3"]["current_bar"])
		# T9: retirada (solo línea base)
		self.assertTrue(rows["T9"]["removed"])
		self.assertIsNone(rows["T9"]["current_bar"])
		self.assertIsNotNone(rows["T9"]["baseline_bar"])
		# eje + corte
		self.assertIsNotNone(g["cutoff_pct"])
		self.assertGreaterEqual(g["cutoff_pct"], 0)

	def _sv(self):
		return frappe._dict(
			{
				"header": {
					"name": "PROJ-X",
					"project_name": "Proyecto X",
					"status": "Open",
					"customer_name": "Cliente Demo",
					"start_date": "2026-09-01",
					"cutoff": "2026-09-30",
					"has_baseline": True,
					"baseline_ref": "BL-001",
					"baseline_name": "PMO-BL-1",
					"baseline_end": "2026-11-30",
					"current_end": "2026-12-12",
					"committed_end": "2026-11-30",
					"slip_baseline": 12,
					"slip_committed": -3,
					"note": None,
				},
				"gantt": {
					"has_baseline": True,
					"min_start": "2026-09-01",
					"max_end": "2026-12-12",
					"cutoff_pct": 40.0,
					"tasks": [
						{
							"name": "T1",
							"subject": "Diseño",
							"depth": 0,
							"is_group": 0,
							"is_milestone": 0,
							"progress": 50,
							"start": "2026-09-01",
							"end": "2026-09-10",
							"baseline_bar": {"offset": 0, "width": 10},
							"current_bar": {"offset": 2, "width": 10},
							"overdue": True,
							"completed": False,
							"added": False,
							"removed": False,
							"slip_days": 5,
						},
					],
				},
				"execution": {
					"completadas": 12,
					"en_curso": 8,
					"pendientes": 8,
					"vencidas": 4,
					"total": 32,
					"overdue_source": "overdue_at_status_date",
				},
				# Solo desviaciones temporales reales. Añadida/retirada (composición) NO entran a la tabla:
				# viven en el Gantt/leyenda. Aquí, Vencida (vs línea base) y Excede compromiso (vs compromiso).
				"deviations": [
					{
						"type": "Vencida",
						"name": "T1",
						"subject": "Diseño",
						"is_milestone": 0,
						"owner": "user@x.com",
						"baseline_exp_end_date": "2026-09-05",
						"current_exp_end_date": "2026-09-10",
						"dev_days": 5,
						"dev_ref": "línea base",
						"status": "Working",
					},
					{
						"type": "Excede compromiso",
						"name": "T2",
						"subject": "Despliegue",
						"is_milestone": 0,
						"owner": None,
						"baseline_exp_end_date": "2026-09-20",
						"current_exp_end_date": "2026-09-25",
						"dev_days": 5,
						"dev_ref": "compromiso",
						"status": "Open",
					},
				],
			}
		)

	def test_render_es_mx_and_no_effort_or_economics(self):
		with patch("pmo.project_control._schedule_view", return_value=dict(self._sv())):
			html = get_schedule_html("PROJ-X", cutoff="2026-09-30")
		# 4 bloques es-MX
		self.assertIn("Estado del cronograma", html)
		self.assertIn("línea base vs plan vigente", html)
		self.assertIn("Estado de ejecución", html)
		# Renombrado: el bloque responde «¿dónde está desviado el cronograma?».
		self.assertIn("Desviaciones del cronograma", html)
		self.assertNotIn("Excepciones del cronograma", html)
		# semántica: "plan vigente", NO "pronosticado"
		self.assertIn("Fin plan vigente", html)
		self.assertNotIn("pronosticado", html.lower())
		# Gantt: barras + corte + drill a Task
		self.assertIn("Línea base", html)
		self.assertIn("Plan vigente", html)
		self.assertIn('data-task="T1"', html)
		# 2.1 — desviación con referencia inequívoca (línea base vs compromiso)
		self.assertIn("5 d vs línea base", html)
		self.assertIn("5 d vs compromiso", html)
		# Composición (añadida/retirada) se diferencia en la LEYENDA del Gantt, no como fila de desviación.
		self.assertIn("Fuera de línea base", html)
		self.assertIn("Retirada del plan", html)
		# ejecución (barra segmentada) + total
		self.assertIn("Total tareas", html)
		# NADA de esfuerzo/economía/riesgos/CR/gobernanza
		for token in (
			"Horas planificadas",
			"Horas reales",
			"% consumido",
			"Costo real",
			"Situación económica",
			"Riesgos",
			"Gobernanza",
		):
			self.assertNotIn(token, html)


class TestCostsSection(IntegrationTestCase):
	"""_costs_section compone (no calcula): autorizado desde la frontera + reales nativos de Project."""

	def _gv_router(self, nat):
		def gv(dt, name, fields=None, **k):
			if dt == "Project":
				return nat  # as_dict de campos nativos
			if dt == "Company":
				return "USD"  # default_currency
			return None

		return gv

	def test_maps_native_and_authorized_passthrough(self):
		data = {
			"authorized_cost": 100.0,
			"authorized_revenue": 150.0,
			"currency": "USD",
			"quotations": [{"role": "root"}, {"role": "applied_change"}, {"role": "applied_change"}],
			"pending_changes": [{"name": "Q-9"}],
		}
		nat = frappe._dict(
			company="C",
			total_sales_amount=120,
			total_billed_amount=80,
			total_costing_amount=30,
			total_purchase_cost=20,
			total_consumed_material_cost=5,
			gross_margin=30,
			per_gross_margin=25,
		)
		with (
			patch(
				"pmo.project_control.get_authorized_economics",
				return_value={"available": True, "reason": None, "data": data, "message": None},
			),
			patch("pmo.project_control.frappe.db.get_value", side_effect=self._gv_router(nat)),
		):
			c = _costs_section("X")
		self.assertTrue(c["authorized_available"])
		self.assertEqual(c["authorized"], data)  # passthrough sin recalcular
		self.assertEqual(c["commercial"]["total_billed_amount"], 80)
		# Comparable contra authorized (labor+externo, SIN material) vs base del gross_margin (CON material)
		self.assertEqual(c["real_cost"]["comparable_cost"], 50)  # 30+20
		self.assertEqual(c["real_cost"]["gross_margin_cost_basis"], 55)  # 30+20+5
		self.assertEqual(c["real_cost"]["material"], 5)  # material queda visible como componente aparte
		self.assertEqual(c["changes"], {"applied_count": 2, "pending_count": 1})  # derivado de las listas
		self.assertEqual(c["base_currency"], "USD")
		self.assertEqual(c["as_of"], "current")

	def test_no_proposal_authorized_none_not_zero_but_reals_present(self):
		nat = frappe._dict(
			company="C",
			total_sales_amount=0,
			total_billed_amount=0,
			total_costing_amount=30,
			total_purchase_cost=20,
			total_consumed_material_cost=0,
			gross_margin=-50,
			per_gross_margin=0,
		)
		with (
			patch(
				"pmo.project_control.get_authorized_economics",
				return_value={"available": False, "reason": "no_proposal", "data": None, "message": None},
			),
			patch("pmo.project_control.frappe.db.get_value", side_effect=self._gv_router(nat)),
		):
			c = _costs_section("X")
		self.assertIsNone(c["authorized"])  # None, NUNCA 0
		self.assertEqual(c["authorized_reason"], "no_proposal")
		self.assertEqual(c["real_cost"]["comparable_cost"], 50)  # reales nativos sí se muestran
		self.assertEqual(c["real_cost"]["gross_margin_cost_basis"], 50)  # sin material


class TestCostsGate(IntegrationTestCase):
	"""La sección económica solo se compone con audience interno + gate económico; nunca por defecto."""

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
			if k.get("as_dict"):
				return frappe._dict(project_name="P", status="Open", company=None, customer=None)
			return None

		return gl, ga, gv

	def _build(self, audience, can_see, with_costs=True):
		gl, ga, gv = self._routers()
		sections = [*DEFAULT_SECTIONS, SECTION_COSTS] if with_costs else None
		with (
			patch("pmo.project_control.build_status_report", return_value=_sr(baseline=False, total=0)),
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
			patch("pmo.project_control.can_see_project_economics", return_value=can_see),
			patch("pmo.project_control._costs_section", return_value={"sentinel": True}) as cs,
		):
			ctx = build_project_control("X", cutoff="2026-09-11", audience=audience, sections=sections)
		return ctx, cs

	def test_internal_authorized_includes_costs(self):
		ctx, cs = self._build("internal", can_see=True)
		self.assertIn("costs", ctx)
		cs.assert_called_once()

	def test_internal_not_authorized_excludes_costs(self):
		ctx, cs = self._build("internal", can_see=False)
		self.assertNotIn("costs", ctx)
		cs.assert_not_called()  # gate ANTES de componer

	def test_portal_never_includes_costs(self):
		ctx, _cs = self._build("portal", can_see=True)
		self.assertNotIn("costs", ctx)

	def test_not_requested_by_default_sections(self):
		# Print Format / wrapper usan DEFAULT_SECTIONS (sin costs) → nunca economía aunque haya acceso.
		ctx, cs = self._build("internal", can_see=True, with_costs=False)
		self.assertNotIn("costs", ctx)
		cs.assert_not_called()


class TestFinancialView(IntegrationTestCase):
	"""Vista financiera de detalle (BLOQUE 4): render de financial.html + gate del endpoint."""

	def _authorized(self):
		return {
			"original_revenue": 100,
			"applied_changes_revenue": 20,
			"authorized_revenue": 120,
			"original_cost": 60,
			"applied_changes_cost": 10,
			"authorized_cost": 70,
			"original_labor": 40,
			"applied_changes_labor": 5,
			"authorized_labor": 45,
			"original_external": 20,
			"applied_changes_external": 5,
			"authorized_external": 25,
			"original_margin": 40,
			"applied_changes_margin": 10,
			"authorized_margin": 50,
			"authorized_margin_pct": 42.0,
			"pending_changes": ["Q-9"],
		}

	def _pc_with_costs(self, authorized=None, reason=None, message=None):
		return {
			"project": {"name": "PROJ-X", "project_name": "Proyecto X"},
			"costs": {
				"as_of": "current",
				"authorized_available": authorized is not None,
				"authorized_reason": reason,
				"authorized_message": message,
				"authorized": authorized,
				"commercial": {"total_sales_amount": 110, "total_billed_amount": 70},
				"real_cost": {
					"costing": 38,
					"purchase": 15,
					"material": 5,
					"comparable_cost": 53,
					"gross_margin_cost_basis": 58,
				},
				"native_margin": {"gross_margin": 12, "per_gross_margin": 17},
				"changes": {"applied_count": 2, "pending_count": 1},
				"currency": "USD",
				"base_currency": "USD",
			},
		}

	def _render(self, pc):
		return frappe.render_template("pmo/templates/project_control/financial.html", {"pc": pc})

	def test_render_authorized_contract_and_reals(self):
		html = self._render(self._pc_with_costs(authorized=self._authorized()))
		self.assertIn("Contract", html)
		self.assertIn("USD 120", html)  # authorized_revenue
		self.assertIn("Ordered (Sales Orders)", html)  # etiqueta pmo-propia (no "Ordenado/a")
		self.assertIn("USD 53", html)  # comparable_cost (labor+purchase, SIN material)
		self.assertIn("Material", html)  # material separado como base del margen
		self.assertIn("Q-9", html)  # cambio pendiente identificado

	def test_render_no_costs_shows_no_access(self):
		html = self._render({"project": {"name": "PROJ-X"}})  # sin pc.costs
		self.assertIn("You do not have economic access to this project.", html)

	def test_render_no_proposal_state(self):
		html = self._render(self._pc_with_costs(authorized=None, reason="no_proposal"))
		self.assertIn("No authorized reference", html)
		self.assertIn("USD 53", html)  # reales nativos siguen visibles

	def test_endpoint_renders_when_costs_composed(self):
		pc = self._pc_with_costs(authorized=self._authorized())
		with patch("pmo.project_control.build_project_control", return_value=pc) as b:
			html = get_financial_html("PROJ-X", cutoff="2026-09-11")
		self.assertIn("Contract", html)
		# el endpoint pide solo project + costs (no el reporte completo)
		_, kw = b.call_args
		self.assertEqual(kw.get("audience"), "internal")

	def test_endpoint_no_access_when_costs_absent(self):
		with patch("pmo.project_control.build_project_control", return_value={"project": {"name": "X"}}):
			html = get_financial_html("PROJ-X")
		self.assertIn("You do not have economic access to this project.", html)


class TestEconomicSecurity(IntegrationTestCase):
	"""Seguridad económica: el contrato NO se invoca sin permiso; el endpoint no salta P4."""

	def test_contract_not_called_without_economic_permission(self):
		# El gate va ANTES de componer: si no hay permiso, get_authorized_economics NO se llama.
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
			return frappe._dict(project_name="P", status="Open", company=None) if k.get("as_dict") else None

		with (
			patch("pmo.project_control.build_status_report", return_value=_sr(baseline=False, total=0)),
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
			patch("pmo.project_control.can_see_project_economics", return_value=False),
			patch("pmo.project_control.get_authorized_economics") as contract,
		):
			ctx = build_project_control("X", cutoff="2026-09-11", sections=[*DEFAULT_SECTIONS, SECTION_COSTS])
		self.assertNotIn("costs", ctx)
		contract.assert_not_called()  # ni siquiera se consultó el contrato económico

	def test_financial_endpoint_propagates_p4(self):
		# get_financial_html no permite saltar P4: si build_status_report niega READ, se propaga.
		with patch("pmo.project_control.build_status_report", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				get_financial_html("PROJ-ARBITRARIO")
