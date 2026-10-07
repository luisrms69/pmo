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

from pmo.capacity import get_capacity, get_capacity_detail

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


def _set_default(hours):
	"""Default global en PMO Settings (Single). 0 = sin default global."""
	frappe.db.set_single_value("PMO Settings", "default_capacity_hours_per_day", hours)


class TestPMOCapacity(IntegrationTestCase):
	def setUp(self):
		# Aislamiento explícito: cada test parte sin filas de PMO Capacity y sin default global.
		frappe.db.delete("PMO Capacity")
		_set_default(0)

	def tearDown(self):
		# No filtrar el default global (Single compartido) a otros módulos de test.
		_set_default(0)

	# --- Resolución ---------------------------------------------------------

	def test_global_baseline_applies_to_anyone(self):
		_cap("2026-01-01", 8.0)  # fila global legacy (fallback transitorio; Settings=0 en setUp)
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 8.0)
		self.assertEqual(get_capacity("EMP-CUALQUIERA", "2026-06-15"), 8.0)

	def test_override_beats_global(self):
		_cap("2026-01-01", 8.0)  # fila global legacy (fallback transitorio)
		_cap("2026-01-01", 6.0, employee=EMP1)  # override EMP1
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 6.0)  # override
		self.assertEqual(get_capacity(EMP2, "2026-06-15"), 8.0)  # sin override → fila global legacy

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

	# --- Default global desde PMO Settings (Paso 1) -------------------------

	def test_settings_default_applies_to_anyone_without_rows(self):
		# sin NINGUNA fila PMO Capacity, el default global de Settings basta (sin registro fantasma)
		_set_default(8.0)
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 8.0)
		self.assertEqual(get_capacity("EMP-CUALQUIERA", "2026-06-15"), 8.0)
		detail = get_capacity_detail(EMP1, "2026-06-15")
		self.assertEqual(detail["origin"], "global")
		self.assertIsNone(detail["from_date"])  # el default de Settings no está efectivo-datado

	def test_override_beats_settings_default(self):
		_set_default(8.0)
		_cap("2026-01-01", 6.0, employee=EMP1)  # override individual
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 6.0)  # override manda
		self.assertEqual(get_capacity(EMP2, "2026-06-15"), 8.0)  # sin override → default Settings

	def test_settings_default_precedes_legacy_global_row(self):
		# fallback transitorio: la fila global vieja existe, pero Settings tiene precedencia
		_set_default(9.0)
		_cap("2026-01-01", 8.0)  # fila global legacy (employee vacío)
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 9.0)

	def test_settings_unset_falls_back_to_legacy_global_row(self):
		# sin default en Settings, aún se honra la fila global vieja (sitios no migrados)
		_set_default(0)
		_cap("2026-01-01", 8.0)
		self.assertEqual(get_capacity(EMP1, "2026-06-15"), 8.0)

	# --- Patch de inicialización del default (sitios existentes) ------------

	def test_patch_initializes_default_when_unset(self):
		from pmo.patches.v0_0_1.init_default_capacity_hours import execute

		_set_default(0)  # sitio existente sin valor
		execute()
		self.assertEqual(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"), 8)

	def test_patch_does_not_overwrite_configured(self):
		from pmo.patches.v0_0_1.init_default_capacity_hours import execute

		_set_default(6)  # valor ya configurado por un admin
		execute()
		self.assertEqual(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"), 6)

	# --- Ausencia de configuración (no asumir 8h en código) -----------------

	def test_missing_config_returns_none(self):
		# sin override, sin default en Settings y sin fila global → None (no se asume 8h)
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
