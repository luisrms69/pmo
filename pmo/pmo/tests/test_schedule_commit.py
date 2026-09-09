# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — Fecha comprometida de cronograma (ADR-0007, bloque 1).

Se prueban las validaciones suaves (`validate_task_deadline`, `validate_project_committed_end`) directamente
sobre docs en memoria: avisan (msgprint) cuando el fin planeado excede el compromiso y NO lanzan/bloquean.
No dependen de Company ni de `insert` (leen `doc.get(...)`).
"""

import unittest

import frappe
from frappe.utils import add_days, today

from pmo.schedule_commit import validate_project_committed_end, validate_task_deadline


class TestScheduleCommit(unittest.TestCase):
	def setUp(self):
		frappe.clear_messages()

	def _task(self, exp_end, deadline):
		d = frappe.new_doc("Task")
		d.subject = "SC " + frappe.generate_hash(length=4)
		if exp_end is not None:
			d.exp_end_date = exp_end
		d.pmo_deadline = deadline
		return d

	def _project(self, expected_end, committed):
		d = frappe.new_doc("Project")
		d.project_name = "SC " + frappe.generate_hash(length=4)
		if expected_end is not None:
			d.expected_end_date = expected_end
		d.pmo_committed_end_date = committed
		return d

	# ── Task.pmo_deadline ──────────────────────────────────────────────
	def test_task_deadline_breach_warns_no_raise(self):
		d = self._task(f"{add_days(today(), 5)} 17:00:00", add_days(today(), 3))
		validate_task_deadline(d)  # no debe lanzar
		self.assertTrue(frappe.get_message_log(), "debía emitir un aviso")

	def test_task_no_breach_no_warn(self):
		d = self._task(f"{add_days(today(), 2)} 17:00:00", add_days(today(), 5))
		validate_task_deadline(d)
		self.assertFalse(frappe.get_message_log())

	def test_task_empty_deadline_no_warn(self):
		d = self._task(f"{add_days(today(), 5)} 17:00:00", None)
		validate_task_deadline(d)
		self.assertFalse(frappe.get_message_log())

	# ── Project.pmo_committed_end_date ─────────────────────────────────
	def test_project_committed_breach_warns_no_raise(self):
		d = self._project(add_days(today(), 10), add_days(today(), 4))
		validate_project_committed_end(d)
		self.assertTrue(frappe.get_message_log(), "debía emitir un aviso")

	def test_project_no_breach_no_warn(self):
		d = self._project(add_days(today(), 3), add_days(today(), 10))
		validate_project_committed_end(d)
		self.assertFalse(frappe.get_message_log())

	def test_project_empty_committed_no_warn(self):
		d = self._project(add_days(today(), 10), None)
		validate_project_committed_end(d)
		self.assertFalse(frappe.get_message_log())
