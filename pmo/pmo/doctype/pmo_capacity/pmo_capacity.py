# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Capacity — capacidad laborable efectivo-datada (ADR-0003 D1, Incremento 1).

`employee` vacío = capacidad global (baseline); informado = override individual. Una fila rige desde su
`from_date` hasta que otra del mismo scope la supersede. La resolución vive en `pmo.capacity.get_capacity`.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class PMOCapacity(Document):
	def validate(self):
		self._validate_positive_capacity()
		self._validate_unique_scope_from_date()

	def _validate_positive_capacity(self):
		if not self.capacity_hours_per_day or self.capacity_hours_per_day <= 0:
			frappe.throw(_("Capacity Hours Per Day debe ser mayor que 0."))

	def _validate_unique_scope_from_date(self):
		"""Evita configuraciones ambiguas: un solo registro por scope + from_date.

		`employee` vacío/NULL se trata como un ÚNICO scope GLOBAL → no puede haber dos capacidades
		globales vigentes desde la misma fecha, ni dos overrides del mismo Employee desde la misma fecha.
		"""
		scope_is_global = not self.employee
		existing = frappe.get_all(
			"PMO Capacity",
			filters={"from_date": self.from_date, "name": ["!=", self.name or ""]},
			fields=["name", "employee"],
		)
		for row in existing:
			row_is_global = not row.employee
			same_scope = (scope_is_global and row_is_global) or (
				not scope_is_global and not row_is_global and row.employee == self.employee
			)
			if same_scope:
				scope_label = _("global") if scope_is_global else self.employee
				frappe.throw(
					_("Ya existe una capacidad para el scope {0} desde {1} ({2}).").format(
						scope_label, frappe.format(self.from_date, {"fieldtype": "Date"}), row.name
					)
				)
