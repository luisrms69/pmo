# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Orientación PMO — compositor read-only (pmo.orientation). Datos ficticios, sin BD.

Dos bloques:
  1) `get_orientation`: se prueba como COMPOSITOR puro mockeando sus dos fuentes
     (`project_governance_state` y `_planning_section`) → se verifican familias, exención, selección de
     gobernanza por etapa, priorización, límite de 3, corte=today() y P4.
  2) `_planning_section` (ampliación ADITIVA): `total` y `schedule_incomplete` (tareas DISTINTAS
     incompletas) sin alterar las claves existentes, usando el mismo patrón de mock que test_project_control.
"""

import json
import unittest
from unittest.mock import patch

import frappe

from pmo import orientation
from pmo.project_control import _planning_section

FIXED_TODAY = "2026-10-11"


def _control(key, state="no_aplica", **kw):
	c = {
		"control": key,
		"label": key,
		"description": "",
		"icon": "",
		"state": state,
		"situation": kw.get("situation"),
		"action_owner": kw.get("action_owner"),
		"na_reason": None,
		"existing": kw.get("existing"),
		"counts": kw.get("counts"),
		"can_create": kw.get("can_create", False),
	}
	return c


def _pgs(project_manager="pm@x", status="Open", exempt=False, controls=None):
	keys = ("acta", "baseline", "risk", "change", "closure", "review")
	given = {c["control"]: c for c in (controls or [])}
	full = [given.get(k) or _control(k) for k in keys]
	return {
		"project": "P1",
		"project_name": "P1",
		"project_manager": project_manager,
		"status": status,
		"started": status in ("Open", "On hold"),
		"exempt": exempt,
		"pending_count": sum(1 for c in full if c["state"] == "pendiente"),
		"controls": full,
		"baseline": {"has_baseline": False},
	}


def _plan(total=0, schedule_incomplete=0, unassigned=0):
	return {
		"maturity_pct": None,
		"components": {},
		"unassigned": {"count": unassigned, "tasks": [{"name": f"T{i}"} for i in range(unassigned)]},
		"total": total,
		"schedule_incomplete": schedule_incomplete,
	}


def _run(pgs, plan):
	with (
		patch.object(orientation, "project_governance_state", return_value=pgs),
		patch.object(orientation, "_planning_section", return_value=plan) as mps,
		patch.object(orientation, "today", return_value=FIXED_TODAY),
	):
		res = orientation.get_orientation("P1")
	return res, mps


class TestOrientationComposer(unittest.TestCase):
	def _families(self, res):
		return [r["family"] for r in res["recommendations"]]

	# --- Contrato / payload ---
	def test_no_recommendations_when_clean(self):
		res, _ = _run(_pgs(), _plan())  # PM asignado, todo no_aplica, sin tareas
		self.assertFalse(res["has_recommendations"])
		self.assertEqual(res["recommendations"], [])

	def test_payload_shape_and_cap(self):
		controls = [
			_control("acta", "pendiente", action_owner="PM", can_create=True),
			_control("baseline", "pendiente", action_owner="PM", can_create=True),
			_control("risk", "pendiente", action_owner="PM"),
		]
		res, _ = _run(
			_pgs(project_manager="", controls=controls), _plan(total=5, schedule_incomplete=2, unassigned=4)
		)
		self.assertTrue(res["has_recommendations"])
		self.assertLessEqual(len(res["recommendations"]), 3)
		for r in res["recommendations"]:
			self.assertEqual(
				{"family", "owner", "message", "action", "can_act"},
				set(r) & {"family", "owner", "message", "action", "can_act"},
			)
			self.assertIn("label", r["action"])
			self.assertIn("kind", r["action"])

	# --- Corte = today() ---
	def test_cutoff_is_today_not_status_date(self):
		_res, mps = _run(_pgs(), _plan())
		args, _kwargs = mps.call_args
		stub = args[1]
		self.assertEqual(stub["status_date"], FIXED_TODAY)
		self.assertIsNone(stub["baseline"])

	# --- Familia 1: PM ---
	def test_pm_unassigned_shown_and_disappears(self):
		res, _ = _run(_pgs(project_manager=""), _plan())
		self.assertIn("pm_unassigned", self._families(res))
		self.assertEqual(res["recommendations"][0]["owner"], "PMO")
		res2, _ = _run(_pgs(project_manager="pm@x"), _plan())
		self.assertNotIn("pm_unassigned", self._families(res2))

	def test_pm_unassigned_not_when_terminal(self):
		res, _ = _run(_pgs(project_manager="", status="Completed"), _plan())
		self.assertNotIn("pm_unassigned", self._families(res))

	# --- Familias operativas 3 y 4 ---
	def test_unassigned_tasks_count_and_message(self):
		res, _ = _run(_pgs(), _plan(total=10, unassigned=4))
		rec = next(r for r in res["recommendations"] if r["family"] == "unassigned_tasks")
		self.assertIn("4", rec["message"])
		self.assertEqual(rec["action"]["kind"], "task_list")

	def test_planning_incomplete_requires_leaves(self):
		res, _ = _run(_pgs(), _plan(total=0, schedule_incomplete=0))
		self.assertNotIn("planning_incomplete", self._families(res))
		res2, _ = _run(_pgs(), _plan(total=3, schedule_incomplete=2))
		rec = next(r for r in res2["recommendations"] if r["family"] == "planning_incomplete")
		self.assertIn("2", rec["message"])

	# --- Familias de gobernanza 2 y 5 ---
	def test_handoff_pending_and_exempt_suppresses(self):
		controls = [_control("acta", "pendiente", action_owner="PM", can_create=True, situation="X")]
		res, _ = _run(_pgs(project_manager="pm@x", controls=controls), _plan())
		h = next(r for r in res["recommendations"] if r["family"] == "handoff")
		self.assertTrue(h["can_act"])
		# exento → gobernanza suprimida
		res_ex, _ = _run(_pgs(project_manager="pm@x", exempt=True, controls=controls), _plan())
		self.assertNotIn("handoff", self._families(res_ex))

	def test_baseline_can_act_reflects_can_create(self):
		controls = [_control("baseline", "pendiente", action_owner="PM", can_create=False)]
		res, _ = _run(_pgs(controls=controls), _plan())
		b = next(r for r in res["recommendations"] if r["family"] == "baseline")
		self.assertFalse(b["can_act"])

	# --- Exención: operativas sobreviven ---
	def test_exempt_keeps_operational_families(self):
		controls = [_control("acta", "pendiente", action_owner="PM", can_create=True)]
		res, _ = _run(
			_pgs(project_manager="", exempt=True, controls=controls),
			_plan(total=3, schedule_incomplete=1, unassigned=2),
		)
		fams = self._families(res)
		self.assertIn("pm_unassigned", fams)
		self.assertIn("unassigned_tasks", fams)
		self.assertIn("planning_incomplete", fams)
		self.assertNotIn("handoff", fams)

	# --- Familia 6: selección por etapa, una sola fila ---
	def test_governance_single_row(self):
		controls = [
			_control("risk", "pendiente", action_owner="PM"),
			_control("change", "pendiente", action_owner="PM", counts={"in_review": 0}),
		]
		res, _ = _run(_pgs(controls=controls), _plan())
		govs = [r for r in res["recommendations"] if r["family"] == "governance"]
		self.assertEqual(len(govs), 1)

	def test_governance_cr_in_review_precedes_risk(self):
		controls = [
			_control("risk", "pendiente", action_owner="PM"),
			_control("change", "pendiente", action_owner="PMO", counts={"in_review": 1}),
		]
		res, _ = _run(_pgs(controls=controls), _plan())
		gov = next(r for r in res["recommendations"] if r["family"] == "governance")
		self.assertEqual(gov["control"], "change")

	def test_governance_risk_before_change_when_no_in_review(self):
		controls = [
			_control("risk", "pendiente", action_owner="PM"),
			_control("change", "pendiente", action_owner="PM", counts={"in_review": 0}),
		]
		res, _ = _run(_pgs(controls=controls), _plan())
		gov = next(r for r in res["recommendations"] if r["family"] == "governance")
		self.assertEqual(gov["control"], "risk")

	def test_governance_terminal_closure_before_review(self):
		controls = [
			_control("closure", "pendiente", action_owner="PM", can_create=True),
			_control("review", "pendiente", action_owner="PMO"),
		]
		res, _ = _run(_pgs(status="Completed", controls=controls), _plan())
		gov = next(r for r in res["recommendations"] if r["family"] == "governance")
		self.assertEqual(gov["control"], "closure")

	# --- Priorización global + cap ---
	def test_priority_order_and_cap_three(self):
		controls = [
			_control("acta", "pendiente", action_owner="PM", can_create=True),
			_control("baseline", "pendiente", action_owner="PM", can_create=True),
			_control("risk", "pendiente", action_owner="PM"),
		]
		# candidatos: pm_unassigned, handoff, baseline, unassigned_tasks, planning_incomplete, governance (6)
		res, _ = _run(
			_pgs(project_manager="", controls=controls), _plan(total=5, schedule_incomplete=2, unassigned=3)
		)
		fams = self._families(res)
		self.assertEqual(fams, ["pm_unassigned", "handoff", "baseline"])  # primeros 3 del orden

	# --- P4 ---
	def test_p4_propagates_permission_error(self):
		with patch.object(orientation, "project_governance_state", side_effect=frappe.PermissionError):
			self.assertRaises(frappe.PermissionError, orientation.get_orientation, "P1")


class TestPlanningSectionAdditive(unittest.TestCase):
	"""Ampliación aditiva de _planning_section: total + schedule_incomplete (tareas DISTINTAS incompletas)."""

	def _leaves(self):
		return [
			frappe._dict(
				name="A1",
				subject="A1",
				status="Open",
				exp_start_date="2026-09-01",
				exp_end_date="2026-09-05",
				expected_time=4,
			),  # completa
			frappe._dict(
				name="A2",
				subject="A2",
				status="Open",
				exp_start_date="2026-09-02",
				exp_end_date=None,
				expected_time=0,
			),  # incompleta
			frappe._dict(
				name="A3",
				subject="A3",
				status="Open",
				exp_start_date=None,
				exp_end_date=None,
				expected_time=0,
			),  # incompleta (los 3) = 1
		]

	def _mocks(self, leaves):
		real_gl, real_ga, real_gv = frappe.get_list, frappe.get_all, frappe.db.get_value

		def gl(*a, **k):
			return leaves if k.get("doctype", a[0] if a else None) == "Task" else real_gl(*a, **k)

		def ga(*a, **k):
			if k.get("doctype", a[0] if a else None) == "ToDo":
				return []
			return real_ga(*a, **k)

		return gl, ga, real_gv

	def test_schedule_incomplete_counts_distinct_tasks(self):
		gl, ga, gv = self._mocks(self._leaves())
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": None, "status_date": "2026-09-30"})
		self.assertEqual(pl["total"], 3)
		self.assertEqual(pl["schedule_incomplete"], 2)  # A2 y A3 (A3 cuenta 1 aunque le falten los 3)
		# claves existentes preservadas
		self.assertIn("components", pl)
		self.assertIn("unassigned", pl)

	def test_additive_keys_present_when_no_tasks(self):
		gl, ga, gv = self._mocks([])
		with (
			patch("pmo.project_control.frappe.get_list", side_effect=gl),
			patch("pmo.project_control.frappe.get_all", side_effect=ga),
			patch("pmo.project_control.frappe.db.get_value", side_effect=gv),
		):
			pl = _planning_section("X", {"baseline": None, "status_date": "2026-09-30"})
		self.assertEqual(pl["total"], 0)
		self.assertEqual(pl["schedule_incomplete"], 0)
		self.assertEqual(pl["unassigned"]["count"], 0)
