# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0004 (D1/D2/D3) — Schedule Governance sobre Task (mixin via extend_doctype_class). Datos ficticios.

Verifica que el mixin PMO redefine SOLO las dos validaciones de fecha objetivo:
- una hija puede extenderse mas alla del parent (summary = envelope no vinculante);
- el Actual (act_*) y el forecast (exp_*) no se bloquean por `Project.expected_end_date`;
manteniendo el resto del comportamiento nativo, y con un guard de drift que falla si `Task` deja de
definir esos metodos.

Nota tecnica: la validacion nativa `validate_parent_project_dates` hace `return if frappe.in_test`
(task.py:122), asi que los tests fuerzan `frappe.in_test = False` (atributo de modulo, frappe/__init__.py:83)
dentro de un context manager con restauracion, para ejercer la ruta de produccion.

Nota de drift (upstream `version-16`, post 16.34.2): ERPNext restringio el loop de
`validate_parent_project_dates` a solo `exp_start_date`/`exp_end_date`, excluyendo `act_*`. Es decir,
upstream se alineo con la semantica PMO para el Actual: ya no bloquea `act_end_date > expected_end_date`.
El mixin PMO sigue siendo necesario para la ruta forecast (`exp_*`), que upstream sigue bloqueando. Ver
`test_native_no_longer_blocks_actual_beyond_project_end` abajo: documenta la nueva invariante y actuaria
como guard de drift si upstream revirtiera el cambio.
"""

import frappe
from frappe.tests import IntegrationTestCase

PROJECT = "SG-P"
PROJ_START = "2026-01-01"
PROJ_END = "2026-01-10"


class _prod_path:
	"""Fuerza la ruta de produccion (frappe.in_test=False) y restaura el valor previo."""

	def __enter__(self):
		self._prev = frappe.in_test
		frappe.in_test = False
		return self

	def __exit__(self, *exc):
		frappe.in_test = self._prev
		return False


def _project(name=PROJECT):
	pid = frappe.db.exists("Project", {"project_name": name})
	if not pid:
		pid = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": name,
					"expected_start_date": PROJ_START,
					"expected_end_date": PROJ_END,
					"status": "Open",
				}
			)
			.insert(ignore_permissions=True, ignore_mandatory=True)
			.name
		)
	return pid


def _task(subject, project=None, parent=None, is_group=0, exp_start=None, exp_end=None):
	tid = frappe.db.exists("Task", {"subject": subject})
	if tid:
		return tid
	doc = {
		"doctype": "Task",
		"subject": subject,
		"project": project,
		"is_group": is_group,
		"status": "Open",
	}
	if parent:
		doc["parent_task"] = parent
	if exp_start:
		doc["exp_start_date"] = exp_start
	if exp_end:
		doc["exp_end_date"] = exp_end
	return frappe.get_doc(doc).insert(ignore_permissions=True, ignore_mandatory=True).name


class TestScheduleGovernance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.project = _project()

	# --- guard de drift / activacion del hook ----------------------------------

	def test_native_task_still_defines_target_methods(self):
		"""Si upstream renombra/inlinea estos metodos, el override deja de aplicar -> re-evaluar."""
		from erpnext.projects.doctype.task.task import Task as NativeTask

		self.assertIn("validate_parent_expected_end_date", vars(NativeTask))
		self.assertIn("validate_parent_project_dates", vars(NativeTask))

	def test_mixin_active_in_task_controller(self):
		"""El hook extend_doctype_class debe insertar el mixin en la MRO del controlador de Task."""
		from frappe.model.base_document import get_controller

		from pmo.overrides import PMOTaskScheduleMixin

		controller = get_controller("Task")
		self.assertIn(PMOTaskScheduleMixin, controller.__mro__)

	# --- comportamiento nativo (documenta la nueva invariante upstream) --------

	def test_native_no_longer_blocks_actual_beyond_project_end(self):
		"""ERPNext upstream `version-16` (post 16.34.2) restringio el loop de
		`validate_parent_project_dates` a solo `exp_start_date`/`exp_end_date`:
		`act_*` quedo FUERA del alcance de esa validacion.

		Documenta la nueva invariante: la ruta nativa (con `frappe.in_test=False`)
		YA NO levanta `InvalidDates` cuando `act_end_date` excede
		`Project.expected_end_date`.

		Guard de drift: si upstream regresa a bloquear `act_*` en el futuro, este
		test fallara (al lanzar `InvalidDates` inesperada), forzando a re-evaluar
		el mixin PMO — que hoy devuelve sin validar; ver
		`pmo/overrides.py:PMOTaskScheduleMixin.validate_parent_project_dates`.
		"""
		from erpnext.projects.doctype.task.task import Task as NativeTask

		t = _task("SG-T-NATIVE", project=self.project, exp_start="2026-01-02", exp_end="2026-01-05")
		doc = frappe.get_doc("Task", t)
		doc.act_end_date = "2026-02-01"  # mas alla del fin del Project (2026-01-10)
		with _prod_path():
			# Antes del cambio upstream, esto lanzaba InvalidDates; ya no.
			NativeTask.validate_parent_project_dates(doc)

	# --- comportamiento del mixin PMO ------------------------------------------

	def test_mixin_allows_actual_beyond_project_end(self):
		t = _task("SG-T-ACT", project=self.project, exp_start="2026-01-02", exp_end="2026-01-05")
		doc = frappe.get_doc("Task", t)
		doc.act_end_date = "2026-02-01"
		with _prod_path():
			doc.validate_parent_project_dates()  # no debe lanzar (mixin)

	def test_mixin_allows_child_beyond_parent(self):
		parent = _task("SG-G", project=self.project, is_group=1, exp_start="2026-01-02", exp_end="2026-01-05")
		child = _task(
			"SG-C", project=self.project, parent=parent, exp_start="2026-01-03", exp_end="2026-01-20"
		)
		doc = frappe.get_doc("Task", child)
		with _prod_path():
			doc.validate_parent_expected_end_date()  # hija mas alla del parent: no debe lanzar (mixin)

	def test_task_save_with_actual_beyond_project_succeeds(self):
		"""Path EXACTO que ejecuta Timesheet.update_task_and_project: fijar act_* y task.save()."""
		t = _task("SG-T-SAVE", project=self.project, exp_start="2026-01-02", exp_end="2026-01-05")
		doc = frappe.get_doc("Task", t)
		doc.act_start_date = "2026-01-20"
		doc.act_end_date = "2026-02-01"  # Actual fuera del rango del Project
		with _prod_path():
			doc.save(ignore_permissions=True)  # no debe lanzar
		self.assertEqual(str(frappe.db.get_value("Task", t, "act_end_date")), "2026-02-01")
