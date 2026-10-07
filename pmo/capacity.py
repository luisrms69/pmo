# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Resolución de capacidad efectivo-datada (ADR-0003 D1, Incremento 1).

`get_capacity(employee, date)` es la ÚNICA función de resolución de capacidad del app; Allocation y los
reportes de capacidad (incrementos posteriores) deben reutilizarla, no reimplementar la lógica.

Regla de resolución:
    1. fila del `employee` con `from_date <= date`, la más reciente (override individual);
    2. si no hay override, el default global sale de `PMO Settings.default_capacity_hours_per_day`;
    3. fallback transitorio (deprecado, se retira en Paso 2/4): fila global `PMO Capacity` con
       `employee` vacío/NULL. PMO Settings tiene precedencia sobre esta fila;
    4. si nada aplica, NO se asume 8h en código: devuelve None (config ausente). Con throw=True lanza.
"""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce
from frappe.utils import flt, getdate


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
	`"global"` (default de PMO Settings; `from_date` None por no estar efectivo-datado). `None` si no hay
	config (con `throw=True` lanza). No asume 8h en código. La resolución override→global vive **solo
	aquí**; reportes/UX la reutilizan (no la reimplementan)."""
	on_date = getdate(date)

	if employee:
		row = _latest_capacity_row(on_date, employee=employee)
		if row is not None:
			return {"hours": row[0], "origin": "override", "from_date": row[1]}

	default_hours = _global_default_hours()
	if default_hours is not None:
		return {"hours": default_hours, "origin": "global", "from_date": None}

	# Fallback transitorio (deprecado, se retira en Paso 2/4): fila global `PMO Capacity` con employee
	# vacío. PMO Settings ya tiene precedencia arriba; esta fila solo cubre sitios aún no migrados.
	row = _latest_capacity_row(on_date, employee=None)
	if row is not None:
		return {"hours": row[0], "origin": "global", "from_date": row[1]}

	if throw:
		frappe.throw(
			_("No capacity configured (neither override nor global) for {0} on {1}.").format(
				employee or _("global"), frappe.format(on_date, {"fieldtype": "Date"})
			)
		)
	return None


def _global_default_hours() -> float | None:
	"""Default global de horas/día desde `PMO Settings.default_capacity_hours_per_day` (fuente única).

	Sustituye al patrón de la fila `PMO Capacity` con Employee vacío. Vacío/0/negativo → None (no se
	asume ninguna jornada en código; la ausencia de config no se silencia como 0).
	"""
	hours = flt(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"))
	return hours if hours > 0 else None


def _latest_capacity_row(on_date, employee: str | None = None):
	"""Fila `(capacity_hours_per_day, from_date)` más reciente vigente (`from_date <= on_date`) del scope.

	`employee` informado → override de ese Employee (uso vigente). None → fila global **legacy**
	(`employee` vacío/NULL), consultada solo como fallback transitorio deprecado; el default global vive en
	`PMO Settings.default_capacity_hours_per_day` (ver `_global_default_hours`). None si no hay fila.
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
