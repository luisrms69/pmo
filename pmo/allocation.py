# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Distribución diaria uniforme de horas sobre días laborables (ADR-0003).

Lógica **pura y reutilizable**: `build_allocation_days` reparte un total de horas de forma uniforme
(Even) sobre los **días laborables** de un rango, donde "laborable" = día que **no** es Holiday en la
Holiday List indicada (la lista nativa de ERPNext ya codifica fines de semana + festivos). No asume
Lun-Vie a ciegas ni ignora festivos.

Se reutiliza para distribuir el esfuerzo de una Task (`expected_time` por asignado) sobre sus fechas
(`exp_start_date..exp_end_date`). NO depende de ningún DocType de asignación: el plan de Capacity
Planning se **deriva** de Task + Assignment (ver ADR-0003). La Holiday List del Employee se resuelve
con el helper nativo de ERPNext (`get_holiday_list_for_employee`); aquí solo se consume ya resuelta.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate


def build_allocation_days(from_date, to_date, planned_hours, holiday_list) -> list[dict]:
	"""Devuelve [{date, hours}] repartiendo planned_hours en los días laborables de [from_date, to_date].

	Días laborables = los que no son Holiday en `holiday_list`. La suma de `hours` es exactamente
	`planned_hours` (el último día absorbe el redondeo). Lanza si el rango es inválido, si no hay
	`holiday_list`, o si no hay días laborables en el rango.
	"""
	from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(_("To Date no puede ser anterior a From Date."))
	if not holiday_list:
		frappe.throw(_("No hay Holiday List para resolver los días laborables."))

	working_days = []
	day = start
	while day <= end:
		if not is_holiday(holiday_list, day):
			working_days.append(day)
		day += timedelta(days=1)

	if not working_days:
		frappe.throw(
			_("No hay días laborables entre {0} y {1} según la Holiday List {2}.").format(
				start, end, holiday_list
			)
		)

	total = flt(planned_hours)
	count = len(working_days)
	per_day = flt(total / count, 2)

	rows = []
	running = 0.0
	for index, day in enumerate(working_days):
		hours = flt(total - running, 2) if index == count - 1 else per_day
		running = flt(running + hours, 2)
		rows.append({"date": day, "hours": hours})
	return rows
