# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Status Date (ADR-0006). Bloque 1: validación de `Project.pmo_status_date` (<= today, D2).

Se prueba la función de validación directamente sobre un `Project` en memoria (sin `insert` ni Company):
D2 es lógica pura sobre el valor del campo y no depende del alta completa del Project.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError
from frappe.utils import add_days, today

from pmo.status_date import validate_project_status_date


class TestStatusDateValidation(unittest.TestCase):
	def _project(self, status_date):
		doc = frappe.new_doc("Project")
		doc.project_name = "SD Test " + frappe.generate_hash(length=6)
		doc.pmo_status_date = status_date
		return doc

	def test_future_status_date_rejected(self):
		doc = self._project(add_days(today(), 1))
		with self.assertRaises(ValidationError):
			validate_project_status_date(doc)

	def test_today_status_date_allowed(self):
		doc = self._project(today())
		validate_project_status_date(doc)  # no debe lanzar

	def test_past_status_date_allowed(self):
		doc = self._project(add_days(today(), -30))
		validate_project_status_date(doc)  # no debe lanzar

	def test_empty_status_date_allowed(self):
		doc = self._project(None)
		validate_project_status_date(doc)  # vacío = sin corte, válido
