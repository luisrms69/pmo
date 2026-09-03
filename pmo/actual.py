# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tiempo real trabajado (Actual) derivado de Timesheet (ADR-0003 Incremento 4).

REGLA FIJADA: Actual debe coincidir con la semántica oficial de los reportes de Timesheet de ERPNext.
Se replica exactamente la fuente/semántica de `daily_timesheet_summary`:
    - fuente: `Timesheet Detail` (líneas) unidas a su padre `Timesheet`;
    - horas: `Timesheet Detail.hours` (trabajado, NO billing_hours);
    - estado: `Timesheet.docstatus = 1` (solo Submitted; Draft/Cancelled no cuentan);
    - fecha: bornes `from_time >= timestamp(from_date, '00:00:00')` y `to_time <= timestamp(to_date,
      '24:00:00')` (idénticos al reporte; una línea que cruce medianoche queda fuera del día).

Diferencias justificadas frente al reporte:
    1. se AGREGA (sum) las mismas líneas por employee/día (no cambia la semántica);
    2. NO se aplica `build_match_conditions("Timesheet")`: Actual es un agregado server-side interno con
       el total real; la privacidad/enmascarado (ADR-0002 P4) se aplica en la CAPA DE REPORTES PMO, no
       alterando la fuente del cálculo.

CONFIDENCIALIDAD: estas funciones son INTERNAS (server-side). NO son `@frappe.whitelist`, no exponen
endpoint de cliente y no deben invocarse desde UI saltándose la capa P4. Cualquier presentación/desglose
de Actual pasa por los reportes PMO (incremento posterior), que aplican el enmascarado.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate


def get_actual(employee: str, date=None, project: str | None = None) -> float:
	"""Horas trabajadas (Timesheet) por `employee` en `date`; opcionalmente filtradas por `project`.

	Interna, no whitelisted. Devuelve el total real (0.0 si no hay registros)."""
	on_date = getdate(date)
	return _sum_hours(employee, on_date, on_date, project)


def get_actual_range(employee: str, from_date, to_date) -> dict:
	"""{date: horas trabajadas} por cada día de [from_date, to_date] (inclusive). Interna, no whitelisted."""
	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(_("To Date no puede ser anterior a From Date."))

	result = {}
	day = start
	while day <= end:
		result[day] = _sum_hours(employee, day, day, None)
		day += timedelta(days=1)
	return result


def _sum_hours(employee: str, from_date, to_date, project: str | None) -> float:
	"""Σ Timesheet Detail.hours con la semántica oficial de daily_timesheet_summary (docstatus=1)."""
	conditions = [
		"ts.docstatus = 1",
		"ts.employee = %(employee)s",
		"td.from_time >= timestamp(%(from_date)s, '00:00:00')",
		"td.to_time <= timestamp(%(to_date)s, '24:00:00')",
	]
	params = {"employee": employee, "from_date": from_date, "to_date": to_date}
	if project:
		conditions.append("td.project = %(project)s")
		params["project"] = project

	rows = frappe.db.sql(
		f"""select coalesce(sum(td.hours), 0)
			from `tabTimesheet Detail` td
			inner join `tabTimesheet` ts on td.parent = ts.name
			where {" and ".join(conditions)}""",
		params,
	)
	return flt(rows[0][0], 2)
