# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — pmo.project_economics: frontera opcional a erpnext_proposals + gate único de acceso económico.

PMO no reproduce fórmulas: solo compone/gatea. Se prueban los TRES estados (app ausente / sin propuesta /
inconsistencia real) sin degradar la inconsistencia a ausencia, y la decisión única de permiso."""

from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from pmo import project_economics as pe


class TestEconomicAccess(IntegrationTestCase):
	"""can_see_project_economics = rol económico AND READ del Project (decisión única)."""

	def test_role_and_read_grants(self):
		with (
			patch("pmo.project_economics.frappe.get_roles", return_value=["PMO Manager", "Employee"]),
			patch("pmo.project_economics.frappe.has_permission", return_value=True) as hp,
		):
			self.assertTrue(pe.can_see_project_economics("PROJ-X", user="u@x"))
		hp.assert_called_once()  # se evaluó READ del Project

	def test_no_economic_role_denies_without_checking_read(self):
		with (
			patch("pmo.project_economics.frappe.get_roles", return_value=["Projects Manager", "Employee"]),
			patch("pmo.project_economics.frappe.has_permission", return_value=True) as hp,
		):
			self.assertFalse(pe.can_see_project_economics("PROJ-X", user="u@x"))  # Projects Manager NO basta
		hp.assert_not_called()  # sin rol económico ni siquiera consulta READ

	def test_role_but_no_read_denies(self):
		with (
			patch("pmo.project_economics.frappe.get_roles", return_value=["PMO Executive Access"]),
			patch("pmo.project_economics.frappe.has_permission", return_value=False),
		):
			self.assertFalse(pe.can_see_project_economics("PROJ-X", user="u@x"))


class TestEconomicFrontier(IntegrationTestCase):
	"""get_authorized_economics: 3 estados; inconsistencia real NUNCA se degrada a ausencia."""

	def test_app_absent(self):
		with patch(
			"pmo.project_economics.frappe.get_installed_apps", return_value=["frappe", "erpnext", "pmo"]
		):
			out = pe.get_authorized_economics("PROJ-X")
		self.assertFalse(out["available"])
		self.assertEqual(out["reason"], "app_absent")
		self.assertIsNone(out["data"])

	def test_no_proposal(self):
		with (
			patch("pmo.project_economics.frappe.get_installed_apps", return_value=["erpnext_proposals"]),
			patch("pmo.project_economics._has_linked_quotation", return_value=False),
			patch("pmo.project_economics._authorized_from_proposals") as contract,
		):
			out = pe.get_authorized_economics("PROJ-X")
		self.assertEqual(out["reason"], "no_proposal")
		contract.assert_not_called()  # no se invoca el contrato si no hay propuesta vinculada

	def test_inconsistent_is_not_degraded_to_absence(self):
		with (
			patch("pmo.project_economics.frappe.get_installed_apps", return_value=["erpnext_proposals"]),
			patch("pmo.project_economics._has_linked_quotation", return_value=True),
			patch(
				"pmo.project_economics._authorized_from_proposals",
				side_effect=ValueError("snapshot incompleto"),
			),
		):
			out = pe.get_authorized_economics("PROJ-X")
		# La propuesta EXISTE y el contrato falló → inconsistencia real, NO "no_proposal".
		self.assertFalse(out["available"])
		self.assertEqual(out["reason"], "inconsistent")
		self.assertNotEqual(out["reason"], "no_proposal")
		# Mensaje funcional estable; NO se filtra el texto crudo de la excepción a la UI.
		self.assertTrue(out["message"])
		self.assertNotIn("snapshot incompleto", out["message"])

	def test_ok_passthrough(self):
		fake = {"authorized_cost": 100.0, "authorized_revenue": 150.0, "currency": "USD"}
		with (
			patch("pmo.project_economics.frappe.get_installed_apps", return_value=["erpnext_proposals"]),
			patch("pmo.project_economics._has_linked_quotation", return_value=True),
			patch("pmo.project_economics._authorized_from_proposals", return_value=fake),
		):
			out = pe.get_authorized_economics("PROJ-X")
		self.assertTrue(out["available"])
		self.assertIsNone(out["reason"])
		self.assertEqual(out["data"], fake)  # passthrough sin recalcular
