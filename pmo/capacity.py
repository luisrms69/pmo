# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Resolución de capacidad efectivo-datada (ADR-0003 D1, Incremento 1).

`get_capacity(employee, date)` es la ÚNICA función de resolución de capacidad del app; Allocation y los
reportes de capacidad (incrementos posteriores) deben reutilizarla, no reimplementar la lógica.

Regla de resolución:
    1. fila del `employee` con `from_date <= date`, la más reciente (override individual);
    2. si no hay, fila global (`employee` vacío/NULL) con `from_date <= date`, la más reciente;
    3. si tampoco hay, NO se asume 8h: devuelve None (config ausente). Con throw=True lanza error.
"""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce
from frappe.utils import getdate


def get_capacity(employee: str | None, date=None, throw: bool = False) -> float | None:
	"""Horas laborables/día del `employee` en `date` según `PMO Capacity`; None si no hay config.

	`date` acepta str o date (por defecto hoy). El override del `employee` tiene prioridad sobre el
	baseline global. No asume ningún default (p. ej. 8h) cuando no hay capacidad configurada.
	"""
	detail = get_capacity_detail(employee, date, throw=throw)
	return detail["hours"] if detail else None


def get_capacity_detail(employee: str | None, date=None, throw: bool = False) -> dict | None:
	"""Resolución de capacidad con **origen** y **fecha vigente** (ADR-0003 D1; fuente única).

	Devuelve `{hours, origin, from_date}` donde `origin` es `"override"` (fila del propio Employee) o
	`"global"` (baseline sin Employee). `None` si no hay config (con `throw=True` lanza). No asume 8h.
	La resolución más-específico-luego-global vive **solo aquí**; reportes/UX la reutilizan (no la
	reimplementan)."""
	on_date = getdate(date)

	if employee:
		row = _latest_capacity_row(on_date, employee=employee)
		if row is not None:
			return {"hours": row[0], "origin": "override", "from_date": row[1]}

	row = _latest_capacity_row(on_date, employee=None)
	if row is not None:
		return {"hours": row[0], "origin": "global", "from_date": row[1]}

	if throw:
		frappe.throw(
			_("No hay capacidad configurada (ni override ni global) para {0} en {1}.").format(
				employee or _("global"), frappe.format(on_date, {"fieldtype": "Date"})
			)
		)
	return None


def _latest_capacity_row(on_date, employee: str | None = None):
	"""Fila `(capacity_hours_per_day, from_date)` más reciente vigente (`from_date <= on_date`) del scope.

	`employee` informado → override de ese Employee; None → scope global (`employee` vacío/NULL). None si
	no hay fila.
	"""
	cap = frappe.qb.DocType("PMO Capacity")
	query = (
		frappe.qb.from_(cap)
		.select(cap.capacity_hours_per_day, cap.from_date)
		.where(cap.from_date <= on_date)
		.orderby(cap.from_date, order=Order.desc)
		.limit(1)
	)
	query = (
		query.where(cap.employee == employee) if employee else query.where(Coalesce(cap.employee, "") == "")
	)

	rows = query.run()
	return rows[0] if rows else None
