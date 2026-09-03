# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Resource Allocation — plan de asignación (ADR-0003 D2/D3, Incremento 2).

Submittable: Draft (docstatus 0) editable/materializable; Submitted (docstatus 1) congelado
nativamente; replanificar = Amend nativo (nuevo doc con amended_from). El plan NO concede acceso al
Project ni crea membresía/asignación/ToDo. Privacidad (ADR-0002/P4) por hooks en pmo.permissions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from pmo.allocation import build_allocation_days

_HOURS_TOLERANCE = 0.01


class PMOResourceAllocation(Document):
	def validate(self):
		self._validate_dates()
		self._validate_planned_hours()
		self._validate_task_belongs_to_project()
		if self.docstatus == 0 and not self.allocation_days:
			self.materialize_days()
		self._validate_days_coherence()

	def before_submit(self):
		if not self.allocation_days:
			self.materialize_days()
		self._validate_days_coherence(require=True)

	# --- validaciones -------------------------------------------------------

	def _validate_dates(self):
		if self.from_date and self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date no puede ser anterior a From Date."))

	def _validate_planned_hours(self):
		if not self.planned_hours or flt(self.planned_hours) <= 0:
			frappe.throw(_("Planned Hours debe ser mayor que 0."))

	def _validate_task_belongs_to_project(self):
		if not self.task:
			return
		task_project = frappe.db.get_value("Task", self.task, "project")
		if task_project != self.project:
			frappe.throw(_("La Task {0} no pertenece al Project {1}.").format(self.task, self.project))

	def _validate_days_coherence(self, require=False):
		if not self.allocation_days:
			if require:
				frappe.throw(_("No hay distribución diaria materializada."))
			return
		total_days = flt(sum(flt(d.hours) for d in self.allocation_days), 2)
		if abs(total_days - flt(self.planned_hours, 2)) > _HOURS_TOLERANCE:
			frappe.throw(
				_("La suma de la distribución diaria ({0}) no coincide con Planned Hours ({1}).").format(
					total_days, flt(self.planned_hours, 2)
				)
			)

	# --- materialización ----------------------------------------------------

	def materialize_days(self):
		"""(Re)genera la distribución diaria Even sobre días laborables (Holiday List del Employee).

		Solo permitido en Draft. Usa los helpers nativos de ERPNext para resolver la Holiday List
		(Employee → Company → Global Defaults; override HRMS si está instalado).
		"""
		if self.docstatus != 0:
			frappe.throw(_("La distribución diaria solo puede regenerarse en Draft."))
		if not (self.employee and self.from_date and self.to_date and self.planned_hours):
			return

		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=True)
		rows = build_allocation_days(self.from_date, self.to_date, self.planned_hours, holiday_list)
		self.set("allocation_days", rows)
