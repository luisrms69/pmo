# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del compositor PURO del PMO Project Health Index (PHI) v1 — ADR-0013/0013a.

`compute_phi(signals, weights)` no hace IO → se prueba con dicts fabricados. Cubre: sano, deterioro por
dimensión, guardrails/caps, exención, gate Execution-evaluable, piso de Model Scope, cobertura, pesos
configurables, y no-regresión de `_health()`."""

import unittest

from pmo.health import (
	CHECK_EVALUABLE,
	CHECK_NA,
	CHECK_NE,
	HEALTH_AT_RISK,
	HEALTH_DEVIATED,
	HEALTH_ON_TRACK,
	PHI_CALIBRATION_ID,
	PHI_REASON_EXECUTION_NE,
	PHI_REASON_EXEMPT,
	PHI_REASON_LOW_SCOPE,
	_health,
	compute_phi,
)


def _healthy() -> dict:
	"""Señales de un proyecto sano: las 4 checks verdes → PHI 100, On Track, sin condiciones."""
	return {
		"exempt": False,
		"started": True,
		"has_baseline": True,
		"due_by_cutoff": 10,
		"completed_by_cutoff": 10,
		"slip_baseline_days": 0,
		"baseline_duration_days": 100,
		"slip_committed_days": 0,
		"has_committed": True,
		"financial_inconsistent": False,
		"authorized_cost": 1000.0,
		"comparable_cost": 500.0,
		"percent_complete": 50.0,
		"budget_hours": 100.0,
		"actual_hours": 50.0,
		"gov_required": 3,
		"gov_fulfilled": 3,
		"risk_assessment_exists": True,
		"risk_high_exposure": 0,
		"risk_no_owner": 0,
		"risk_no_response": 0,
	}


def _check(res, cid):
	return next(c for c in res["checks"] if c["id"] == cid)


class TestPHIEngine(unittest.TestCase):
	# 1) Proyecto sano
	def test_healthy_project(self):
		r = compute_phi(_healthy())
		self.assertTrue(r["applicable"])
		self.assertEqual(r["phi"], 100)
		self.assertEqual(r["band"], HEALTH_ON_TRACK)
		self.assertEqual(r["band_raw"], HEALTH_ON_TRACK)
		self.assertIsNone(r["cap_applied"])
		self.assertEqual(r["critical_conditions"], [])
		self.assertEqual(r["calibration_id"], PHI_CALIBRATION_ID)
		self.assertEqual(r["model_scope"], 1.0)
		self.assertEqual(r["evidence_coverage"], 1.0)
		self.assertEqual(r["coverage_level"], "sufficient")
		self.assertTrue(r["portfolio_comparable"])

	# 2) Execution deteriorada (mayor peso) → cae a At Risk
	def test_execution_degraded(self):
		s = _healthy()
		s["completed_by_cutoff"] = 5  # 50% → rojo
		r = compute_phi(s)
		self.assertEqual(r["phi"], 50)  # (0*50 + 20 + 15 + 15)/100
		self.assertEqual(r["band"], HEALTH_AT_RISK)
		self.assertEqual(r["dimensions"]["execution"]["score"], 0)

	# 3) Schedule deteriorado
	def test_schedule_degraded(self):
		s = _healthy()
		s["slip_baseline_days"] = 20  # 20% → rojo SCH-1
		s["slip_committed_days"] = 30  # > 10d → rojo SCH-2
		r = compute_phi(s)
		self.assertEqual(r["phi"], 65)  # (50 + 0 + 0 + 15)/100
		self.assertEqual(r["band"], HEALTH_AT_RISK)

	# 4) Governance deteriorada — se refleja en el score (peso 15), sigue On Track (85)
	def test_governance_degraded_stays_on_track(self):
		s = _healthy()
		s["gov_fulfilled"] = 1  # 1/3 → rojo
		r = compute_phi(s)
		self.assertEqual(r["phi"], 85)  # (50 + 20 + 15 + 0)/100
		self.assertEqual(r["band"], HEALTH_ON_TRACK)  # governance sola no baja de On Track

	# 5) Inconsistencia económica → cap At Risk (número intacto), banda cruda On Track
	def test_financial_inconsistent_caps_band(self):
		s = _healthy()
		s["financial_inconsistent"] = True
		r = compute_phi(s)
		self.assertEqual(r["phi"], 100)
		self.assertEqual(r["band_raw"], HEALTH_ON_TRACK)
		self.assertEqual(r["band"], HEALTH_AT_RISK)
		self.assertIn("economic_reference_inconsistent", r["cap_applied"]["conditions"])

	# 6) Riesgo de exposición alta no gestionado → cap At Risk
	def test_high_exposure_risk_caps_band(self):
		s = _healthy()
		s["risk_high_exposure"] = 2
		s["risk_no_owner"] = 1
		r = compute_phi(s)
		self.assertEqual(r["phi"], 100)
		self.assertEqual(r["band"], HEALTH_AT_RISK)
		self.assertIn("high_exposure_risk_unmanaged", r["cap_applied"]["conditions"])

	# 6b) Riesgo alto gestionado (dueño + respuesta) → no condición, no cap
	def test_high_exposure_risk_managed_no_cap(self):
		s = _healthy()
		s["risk_high_exposure"] = 2
		r = compute_phi(s)
		self.assertEqual(r["band"], HEALTH_ON_TRACK)
		self.assertIsNone(r["cap_applied"])

	# 6c) REGRESIÓN: riesgo de alta exposición SIN evaluación formal → NO finge riesgo crítico (no cap).
	# La ausencia de evaluación es carencia de Governance, no un critical risk (bug PROJ-0036).
	def test_high_exposure_without_assessment_no_cap(self):
		s = _healthy()
		s["risk_assessment_exists"] = False  # existe item de riesgo pero sin evaluación establecida
		s["risk_high_exposure"] = 2
		s["risk_no_owner"] = 1
		r = compute_phi(s)
		codes = [c["code"] for c in r["critical_conditions"]]
		self.assertNotIn("high_exposure_risk_unmanaged", codes)
		self.assertIsNone(r["cap_applied"])
		self.assertEqual(r["band"], HEALTH_ON_TRACK)

	# 7) El cap NO altera el score y NUNCA fuerza Deviated
	def test_cap_preserves_score_and_never_forces_deviated(self):
		s = _healthy()
		s["completed_by_cutoff"] = 0
		s["slip_baseline_days"] = 50
		s["slip_committed_days"] = 40
		s["gov_fulfilled"] = 0
		s["financial_inconsistent"] = True  # cap
		r = compute_phi(s)
		self.assertEqual(r["phi"], 0)
		self.assertEqual(r["band"], HEALTH_DEVIATED)  # cap no lo "sube"
		self.assertIsNone(r["cap_applied"])
		s2 = _healthy()
		s2["completed_by_cutoff"] = 5  # phi 50 At Risk
		s2["financial_inconsistent"] = True
		r2 = compute_phi(s2)
		self.assertEqual(r2["phi"], 50)
		self.assertEqual(r2["band"], HEALTH_AT_RISK)

	# 8) Múltiples critical conditions → determinista, sin manipular score
	def test_multiple_criticals(self):
		s = _healthy()
		s["financial_inconsistent"] = True
		s["risk_high_exposure"] = 2
		s["risk_no_response"] = 1
		s["comparable_cost"] = 1500.0
		s["actual_hours"] = 150.0
		r = compute_phi(s)
		self.assertEqual(r["phi"], 100)
		self.assertEqual(r["band"], HEALTH_AT_RISK)
		codes = {c["code"] for c in r["critical_conditions"]}
		self.assertEqual(
			codes,
			{
				"economic_reference_inconsistent",
				"high_exposure_risk_unmanaged",
				"cost_overrun",
				"effort_overrun",
			},
		)

	# 9) Sobrecosto / sobreconsumo → reportados como guardrails, sin cap ni cambio de banda
	def test_overrun_guardrails_no_cap(self):
		s = _healthy()
		s["comparable_cost"] = 1500.0
		s["actual_hours"] = 150.0
		r = compute_phi(s)
		codes = {c["code"] for c in r["critical_conditions"]}
		self.assertIn("cost_overrun", codes)
		self.assertIn("effort_overrun", codes)
		self.assertEqual(r["phi"], 100)
		self.assertEqual(r["band"], HEALTH_ON_TRACK)
		self.assertIsNone(r["cap_applied"])

	# 10) PMO-exempt → NO tiene PHI
	def test_exempt_has_no_phi(self):
		r = compute_phi({"exempt": True})
		self.assertFalse(r["applicable"])
		self.assertIsNone(r["phi"])
		self.assertEqual(r["reason"], PHI_REASON_EXEMPT)

	# ── Gate estructural: Execution debe ser EVALUABLE ──

	# 11) EXE N/A (due==0) con baseline → SIN número (execution_not_evaluable)
	def test_execution_na_due_zero_no_number(self):
		s = _healthy()
		s["due_by_cutoff"] = 0  # nada debía entregarse → EXE-1 N/A
		r = compute_phi(s)
		self.assertIsNone(r["phi"])
		self.assertIsNone(r["band"])
		self.assertEqual(r["reason"], PHI_REASON_EXECUTION_NE)
		self.assertEqual(_check(r, "EXE-1")["state"], CHECK_NA)

	# 12) EXE N/E (sin baseline) → SIN número; la carencia NO se esconde (checks N/E + condición)
	def test_missing_baseline_no_number_but_flagged(self):
		s = _healthy()
		s["has_baseline"] = False
		s["due_by_cutoff"] = None
		s["slip_baseline_days"] = None
		s["baseline_duration_days"] = None
		s["gov_fulfilled"] = 1
		r = compute_phi(s)
		self.assertIsNone(r["phi"])
		self.assertEqual(r["reason"], PHI_REASON_EXECUTION_NE)
		self.assertEqual(_check(r, "EXE-1")["state"], CHECK_NE)
		self.assertEqual(_check(r, "SCH-1")["state"], CHECK_NE)
		codes = [c["code"] for c in r["critical_conditions"]]
		self.assertIn("governance_baseline_missing", codes)  # deficiencia visible

	# 13) EXE evaluable pero SCH-2 N/A → número emitido; N/A baja Model Scope
	def test_na_reduces_model_scope_but_emits(self):
		s = _healthy()
		s["has_committed"] = False  # SCH-2 N/A
		s["slip_committed_days"] = None
		r = compute_phi(s)
		self.assertEqual(_check(r, "SCH-2")["state"], CHECK_NA)
		self.assertIsNotNone(r["phi"])  # EXE evaluable → sí hay número
		self.assertEqual(r["model_scope"], 0.85)  # 85/100

	# 14) EXE evaluable + SCH-1 N/E → cobertura parcial
	def test_partial_coverage(self):
		s = _healthy()
		s["baseline_duration_days"] = None  # SCH-1 N/E
		s["has_committed"] = False  # SCH-2 N/A
		s["slip_committed_days"] = None
		r = compute_phi(s)
		self.assertEqual(_check(r, "SCH-1")["state"], CHECK_NE)
		self.assertIsNotNone(r["phi"])
		self.assertEqual(r["coverage_level"], "partial")  # EC 65/85 = 0.765
		self.assertFalse(r["portfolio_comparable"])

	# 15) Piso de Model Scope: con pesos que dejan MS<0.50 → sin número
	def test_low_model_scope_no_number(self):
		w = {"execution": 30, "schedule": 14, "governance": 56}
		s = _healthy()
		s["has_committed"] = False  # SCH-2 N/A
		s["slip_committed_days"] = None
		s["gov_required"] = 0  # GOV N/A
		s["gov_fulfilled"] = 0
		r = compute_phi(s, weights=w)
		# aplicable = EXE(30 eval) + SCH-1(8 eval) = 38 → MS 0.38 < 0.50
		self.assertLess(r["model_scope"], 0.50)
		self.assertIsNone(r["phi"])
		self.assertEqual(r["reason"], PHI_REASON_LOW_SCOPE)

	# ── Pesos configurables ──
	def test_configurable_weights(self):
		w = {"execution": 60, "schedule": 30, "governance": 10}
		s = _healthy()
		s["completed_by_cutoff"] = 0  # EXE rojo
		r = compute_phi(s, weights=w)
		self.assertEqual(r["dimensions"]["execution"]["weight"], 60)
		self.assertEqual(r["phi"], 40)  # (0*60 + 30 + 10)/100 → Deviated
		self.assertEqual(r["band"], HEALTH_DEVIATED)

	# Buckets amarillos → 50
	def test_yellow_buckets(self):
		s = _healthy()
		s["completed_by_cutoff"] = 8
		s["slip_baseline_days"] = 5
		s["slip_committed_days"] = 5
		s["gov_fulfilled"] = 2
		r = compute_phi(s)
		self.assertEqual(r["phi"], 50)
		self.assertEqual(r["band"], HEALTH_AT_RISK)


class TestHealthNoRegression(unittest.TestCase):
	"""El semáforo `_health()` (ADR-0011 D2) permanece intacto."""

	def test_on_track(self):
		self.assertEqual(_health(0, 0, 0, 0), HEALTH_ON_TRACK)
		self.assertEqual(_health(None, None, None, None), HEALTH_ON_TRACK)

	def test_at_risk(self):
		self.assertEqual(_health(3, 0, 0, 0), HEALTH_AT_RISK)

	def test_deviated(self):
		self.assertEqual(_health(0, 2, 0, 0), HEALTH_DEVIATED)
		self.assertEqual(_health(0, 0, 1, 0), HEALTH_DEVIATED)
		self.assertEqual(_health(0, 0, 0, 1), HEALTH_DEVIATED)


if __name__ == "__main__":
	unittest.main()
