# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 Incremento 1 — PMO Capacity. Datos ficticios.

Cubre: capacidad global, override por Employee, cambio de vigencia (efectivo-datado), ausencia de
configuración (sin asumir 8h) y validaciones (valor > 0, unicidad scope + from_date con GLOBAL único).

Las filas se insertan con `ignore_links=True` y employee IDs ficticios: no se requiere HRMS ni
Employee/Company reales en el site de tests.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pmo.capacity import get_capacity

EMP1 = "EMP-CAP-0001"
EMP2 = "EMP-CAP-0002"


def _cap(from_date, hours, employee=None):
	doc = frappe.get_doc(
		{
			"doctype": "PMO Capacity",
			"employee": employee,
			"from_date": from_date,
			"capacity_hours_per_day": hours,
		}
	)
	doc.insert(ignore_permissions=True, ignore_links=True)
	return doc.name


class TestPMOCapacity(IntegrationTestCase):
	def setUp(self):
		# Aislamiento explícito: cada test parte sin filas de PMO Capacity.
		frappe.db.delete("PMO Capacity")

	# --- Resolución ---------------------------------------------------------

	def test_global_baseline_applies_to_anyone(self):
		_cap("2026-01-01", 8.0)  # global
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 8.0)
		self.assertEqual(get_capacity("EMP-CUALQUIERA", "2026-06-15"), 8.0)

	def test_override_beats_global(self):
		_cap("2026-01-01", 8.0)  # global
		_cap("2026-01-01", 6.0, employee=EMP1)  # override EMP1
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 6.0)  # override
		self.assertEqual(get_capacity(EMP2, "2026-06-15"), 8.0)  # sin override → global

	def test_effective_dating_preserves_past(self):
		_cap("2026-01-01", 8.0, employee=EMP1)
		_cap("2026-07-01", 4.0, employee=EMP1)
		self.assertEqual(get_capacity(EMP1, "2026-02-15"), 8.0)  # antes del cambio
		self.assertEqual(get_capacity(EMP1, "2026-08-15"), 4.0)  # después del cambio
		self.assertEqual(get_capacity(EMP1, "2026-07-01"), 4.0)  # el mismo día de vigencia

	def test_date_before_any_vigencia_returns_none(self):
		_cap("2026-07-01", 4.0, employee=EMP1)
		# no hay fila (ni override ni global) con from_date <= la fecha consultada
		self.assertIsNone(get_capacity(EMP1, "2026-06-30"))

	# --- Ausencia de configuración (no asumir 8h) ---------------------------

	def test_missing_config_returns_none(self):
		self.assertIsNone(get_capacity(EMP1, "2026-06-15"))

	def test_missing_config_can_throw(self):
		with self.assertRaises(frappe.ValidationError):
			get_capacity(EMP1, "2026-06-15", throw=True)

	# --- Validaciones -------------------------------------------------------

	def test_capacity_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			_cap("2026-01-01", 0.0)
		with self.assertRaises(frappe.ValidationError):
			_cap("2026-01-01", -3.0, employee=EMP1)

	def test_duplicate_global_scope_same_from_date_blocked(self):
		_cap("2026-01-01", 8.0)  # primer global
		with self.assertRaises(frappe.ValidationError):
			_cap("2026-01-01", 7.0)  # segundo global misma from_date → bloqueado

	def test_duplicate_override_scope_same_from_date_blocked(self):
		_cap("2026-01-01", 6.0, employee=EMP1)
		with self.assertRaises(frappe.ValidationError):
			_cap("2026-01-01", 5.0, employee=EMP1)

	def test_same_from_date_different_scope_allowed(self):
		# global y override del mismo día son scopes distintos → permitido
		_cap("2026-01-01", 8.0)
		_cap("2026-01-01", 6.0, employee=EMP1)
		self.assertEqual(get_capacity(EMP1, "2026-03-01"), 6.0)
