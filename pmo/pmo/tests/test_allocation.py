# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0003 Incremento 2 — PMO Resource Allocation. Datos ficticios.

Cubre: materialización Even respetando Holiday List real (helpers nativos), ciclo de vida submittable
(Draft materializa/edita, Submit congela, Amend replanifica), y validaciones (task pertenece al Project,
fechas, planned_hours > 0, coherencia de la distribución diaria).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from pmo.allocation import build_allocation_days

HL = "PMO-HL-TEST"


def _holiday_list():
	if not frappe.db.exists("Holiday List", HL):
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HL,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [{"holiday_date": "2026-01-06", "description": "Festivo"}],
			}
		).insert(ignore_permissions=True)
	return HL


def _employee():
	existing = frappe.db.exists("Employee", {"employee_name": "PMO Cap Test"})
	if existing:
		return existing
	emp = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "PMO Cap Test",
			"holiday_list": _holiday_list(),
			"status": "Active",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
		}
	)
	emp.insert(ignore_permissions=True, ignore_mandatory=True)
	return emp.name


def _project(name):
	existing = frappe.db.exists("Project", {"project_name": name})
	if existing:
		return existing
	p = frappe.get_doc({"doctype": "Project", "project_name": name})
	p.insert(ignore_permissions=True, ignore_mandatory=True)
	return p.name


def _task(subject, project):
	existing = frappe.db.exists("Task", {"subject": subject, "project": project})
	if existing:
		return existing
	return (
		frappe.get_doc({"doctype": "Task", "subject": subject, "project": project})
		.insert(ignore_permissions=True, ignore_mandatory=True)
		.name
	)


def _allocation(employee, project, planned=20.0, from_date="2026-01-05", to_date="2026-01-09", task=None):
	return frappe.get_doc(
		{
			"doctype": "PMO Resource Allocation",
			"employee": employee,
			"project": project,
			"task": task,
			"from_date": from_date,
			"to_date": to_date,
			"planned_hours": planned,
		}
	)


class TestAllocationMaterialization(IntegrationTestCase):
	def setUp(self):
		_holiday_list()

	# --- helper puro build_allocation_days ---------------------------------

	def test_build_even_respects_holidays(self):
		# rango 05..09 con 06 festivo → 4 días laborables → 20/4 = 5h
		rows = build_allocation_days("2026-01-05", "2026-01-09", 20, HL)
		self.assertEqual(len(rows), 4)
		self.assertNotIn(getdate("2026-01-06"), [r["date"] for r in rows])
		self.assertTrue(all(r["hours"] == 5.0 for r in rows))
		self.assertEqual(flt(sum(r["hours"] for r in rows), 2), 20.0)

	def test_build_rounding_absorbed_by_last_day(self):
		# rango 05..08 con 06 festivo → 3 días → 10h → 3.33, 3.33, 3.34 (suma exacta 10)
		rows = build_allocation_days("2026-01-05", "2026-01-08", 10, HL)
		self.assertEqual(len(rows), 3)
		self.assertEqual(flt(sum(r["hours"] for r in rows), 2), 10.0)

	def test_build_no_working_days_raises(self):
		with self.assertRaises(frappe.ValidationError):
			build_allocation_days("2026-01-06", "2026-01-06", 8, HL)  # único día es festivo

	def test_build_invalid_range_raises(self):
		with self.assertRaises(frappe.ValidationError):
			build_allocation_days("2026-01-09", "2026-01-05", 8, HL)


class TestAllocationLifecycle(IntegrationTestCase):
	def setUp(self):
		# Aislamiento: cada test parte sin planes previos (Project/Employee/HL son idempotentes).
		frappe.db.delete("PMO Resource Allocation")
		frappe.db.delete("PMO Allocation Day")
		_holiday_list()
		self.emp = _employee()
		self.proj = _project("PMO-ALLOC-P1")

	def test_materialize_on_validate(self):
		doc = _allocation(self.emp, self.proj, planned=20.0).insert(ignore_permissions=True)
		self.assertEqual(len(doc.allocation_days), 4)  # 06 festivo excluido
		self.assertEqual(flt(sum(flt(d.hours) for d in doc.allocation_days), 2), 20.0)

	def test_submit_freezes_distribution(self):
		doc = _allocation(self.emp, self.proj).insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
		# regenerar tras submit está bloqueado (congelado nativamente)
		with self.assertRaises(frappe.ValidationError):
			doc.materialize_days()

	def test_amend_creates_new_editable_plan(self):
		doc = _allocation(self.emp, self.proj).insert(ignore_permissions=True)
		doc.submit()
		doc.cancel()
		amended = frappe.copy_doc(doc)
		amended.amended_from = doc.name
		amended.docstatus = 0
		amended.insert(ignore_permissions=True)
		self.assertEqual(amended.amended_from, doc.name)
		self.assertEqual(amended.docstatus, 0)
		self.assertTrue(amended.allocation_days)

	# --- validaciones -------------------------------------------------------

	def test_task_must_belong_to_project(self):
		other = _project("PMO-ALLOC-P2")
		foreign_task = _task("Ajena", other)
		with self.assertRaises(frappe.ValidationError):
			_allocation(self.emp, self.proj, task=foreign_task).insert(ignore_permissions=True)

	def test_task_of_same_project_allowed(self):
		own_task = _task("Propia", self.proj)
		doc = _allocation(self.emp, self.proj, task=own_task).insert(ignore_permissions=True)
		self.assertEqual(doc.task, own_task)

	def test_invalid_dates_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_allocation(self.emp, self.proj, from_date="2026-01-09", to_date="2026-01-05").insert(
				ignore_permissions=True
			)

	def test_planned_hours_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			_allocation(self.emp, self.proj, planned=0).insert(ignore_permissions=True)

	def test_days_coherence_enforced(self):
		doc = _allocation(self.emp, self.proj, planned=20.0)
		doc.append("allocation_days", {"date": "2026-01-05", "hours": 5.0})  # suma 5 ≠ 20
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)
