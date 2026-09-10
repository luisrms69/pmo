# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests — PMO Project Status (Print Format presentable). Contexto `pmo.print_status` + render.

Puro: `_relevant` (solo tareas relevantes para evaluación). Integración: `pmo_project_status` end-to-end
(reusa build_status_report; P4) y render del Print Format vía `frappe.get_print` (Jinja method cableado)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from pmo.print_status import _relevant, pmo_project_status


class TestPrintStatusPure(unittest.TestCase):
	def _r(self, **kw):
		base = {
			"name": "T",
			"slip_days": None,
			"overdue_at_status_date": False,
			"exceeds_deadline": False,
			"is_milestone": 0,
		}
		base.update(kw)
		return base

	def test_relevant_selects_only_deviations(self):
		rows = [
			self._r(name="ok", slip_days=0),  # sin desviación → fuera
			self._r(name="slip", slip_days=5),  # slip != 0 → dentro
			self._r(name="overdue", overdue_at_status_date=True),  # vencida → dentro
			self._r(name="deadline", exceeds_deadline=True),  # forecast > compromiso → dentro
			self._r(name="hito", is_milestone=1),  # hito → dentro
			self._r(name="none"),  # sin nada → fuera
		]
		got = {r["name"] for r in _relevant(rows)}
		self.assertEqual(got, {"slip", "overdue", "deadline", "hito"})

	def test_relevant_negative_slip_counts(self):
		# slip negativo (adelanto) también es desviación medible → se muestra para evaluar.
		self.assertEqual(len(_relevant([self._r(slip_days=-2)])), 1)


def _project(name, owner="Administrator"):
	p = frappe.db.exists("Project", {"project_name": name}) or (
		frappe.get_doc({"doctype": "Project", "project_name": name})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)
	frappe.db.set_value("Project", p, "owner", owner)
	return p


def _task(subject, project, expected=0, actual=0):
	t = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": project,
			"expected_time": expected,
			"status": "Open",
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	if actual:
		frappe.db.set_value("Task", t.name, "actual_time", actual)
	return t.name


class TestPrintStatusIntegration(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_context_without_baseline(self):
		p = _project("PS-NOBASE")
		_task("PS-T1", p, expected=10, actual=4)
		ctx = pmo_project_status(p)
		self.assertIsNone(ctx["baseline"])  # sin baseline vigente
		self.assertEqual(ctx["relevant_tasks"], [])  # sin baseline → sin tabla de desviación
		self.assertEqual(ctx["omitted_tasks"], 0)
		self.assertEqual(ctx["planned_hours"], 10.0)
		self.assertEqual(ctx["actual_hours"], 4.0)
		self.assertEqual(ctx["pct_consumed"], 40.0)
		self.assertEqual(ctx["health"], "En plan")  # sin slips/vencidas
		self.assertEqual(ctx["counts"]["total"], 1)

	def test_print_format_renders(self):
		# Render real del Print Format (valida el método Jinja + plantilla). Requiere el PF sincronizado.
		if not frappe.db.exists("Print Format", "PMO Project Status"):
			self.skipTest("PMO Project Status no sincronizado (correr bench migrate)")
		p = _project("PS-RENDER")
		_task("PS-RT1", p, expected=8)
		html = frappe.get_print("Project", p, print_format="PMO Project Status")
		self.assertIn("Resumen ejecutivo", html)
		self.assertIn("Tareas a evaluar", html)

	def test_print_format_pdf(self):
		# Smoke de PDF (mismo Print Format vía wkhtmltopdf). Se omite si el backend PDF no está disponible.
		if not frappe.db.exists("Print Format", "PMO Project Status"):
			self.skipTest("PMO Project Status no sincronizado")
		p = _project("PS-PDF")
		_task("PS-PDF-T1", p, expected=8)
		try:
			pdf = frappe.get_print("Project", p, print_format="PMO Project Status", as_pdf=True)
		except Exception as e:  # backend PDF ausente en el entorno de test
			self.skipTest(f"backend PDF no disponible: {e}")
		self.assertTrue(pdf and len(pdf) > 1000)  # bytes de PDF no triviales
