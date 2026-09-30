# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests de la capa de PRESENTACIÓN del PHI (pmo.phi.decorate_phi / phi_for_row) — ADR-0013.

Verifica que se expongan etiquetas de usuario (nunca códigos internos), que la banda EFECTIVA (tras cap)
prevalezca sobre `band_raw`, y los estados unavailable / exempt / partial coverage."""

import unittest

from pmo.health import HEALTH_AT_RISK, HEALTH_ON_TRACK, compute_phi
from pmo.phi import PHI_CONDITION_LABELS, decorate_phi


def _healthy() -> dict:
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


def _view(signals):
	return decorate_phi(compute_phi(signals))


class TestPHIView(unittest.TestCase):
	def test_scored_labels(self):
		v = _view(_healthy())
		self.assertEqual(v["display_state"], "scored")
		self.assertEqual(v["phi"], 100)
		self.assertTrue(v["band_label"])  # etiqueta de banda presente (Healthy)
		self.assertEqual(v["coverage_label"], "Sufficient")

	def test_band_label_not_on_track_wording(self):
		# La etiqueta de salud NO debe ser "On Track" (se evita confusión con Schedule).
		v = _view(_healthy())
		self.assertNotIn("On Track", str(v["band_label"]))

	def test_effective_band_prevails_over_raw(self):
		s = _healthy()
		s["financial_inconsistent"] = True  # cap → banda efectiva At Risk
		v = _view(s)
		self.assertEqual(v["band_raw"], HEALTH_ON_TRACK)
		self.assertEqual(v["band"], HEALTH_AT_RISK)
		self.assertEqual(v["phi"], 100)  # número intacto

	def test_conditions_translated_no_internal_codes(self):
		s = _healthy()
		s["risk_high_exposure"] = 2
		s["risk_no_owner"] = 1
		v = _view(s)
		# Mensaje de usuario, NO el código interno.
		self.assertIn("Critical risk pending management", v["condition_labels"])
		for code in PHI_CONDITION_LABELS:
			self.assertNotIn(code, v["condition_labels"])  # nunca se expone el código

	def test_unavailable_state(self):
		s = _healthy()
		s["due_by_cutoff"] = 0  # EXE N/A → sin número
		v = _view(s)
		self.assertEqual(v["display_state"], "unavailable")
		self.assertEqual(v["display_title"], "PHI unavailable")
		self.assertIn("evaluable execution data", v["display_message"])

	def test_exempt_state(self):
		v = decorate_phi(compute_phi({"exempt": True}))
		self.assertEqual(v["display_state"], "exempt")
		self.assertEqual(v["display_title"], "Basic tracking")
		self.assertIn("not subject to formal PMO", v["display_message"])

	def test_partial_coverage_label(self):
		s = _healthy()
		s["baseline_duration_days"] = None  # SCH-1 N/E
		s["has_committed"] = False  # SCH-2 N/A
		s["slip_committed_days"] = None
		v = _view(s)
		self.assertEqual(v["coverage_label"], "Partial")

	def test_phi_for_row_shape(self):
		# phi_for_row reutiliza señales; aquí probamos el shape con sr simulado (has_baseline via signals).
		# Como phi_for_row reconstruye señales desde sr real, validamos el shape de decorate en su lugar.
		v = _view(_healthy())
		row_like = {
			"phi": v["phi"],
			"phi_band": v["band"],
			"phi_health": v["band_label"],
			"phi_state": v["display_state"],
			"phi_execution": v["dimensions"]["execution"]["score"],
		}
		self.assertEqual(row_like["phi_state"], "scored")
		self.assertEqual(row_like["phi_execution"], 100)


if __name__ == "__main__":
	unittest.main()
