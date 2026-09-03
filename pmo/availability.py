# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Disponibilidad derivada por día (ADR-0003 Incremento 3).

Availability = Capacity - no-laborables (Holiday List) - ausencias aprobadas (Leave, solo si HRMS).
Es DERIVADA: refleja el estado vigente de sus fuentes nativas; no se persiste ni se congela.

Reglas (decisiones fijadas):
    1. base = get_capacity(employee, date). Si es None → Availability None (config ausente NO se
       convierte silenciosamente en 0, aunque el día sea festivo o tenga Leave).
    2. si el día es Holiday en la Holiday List del employee (helper nativo) → 0.
    3. si HRMS está instalado y hay Leave aprobada cubriendo el día: día completo → 0; medio día → base/2.
    4. si no → base.

No duplica la resolución de capacidad ni la de Holiday List: reutiliza get_capacity y los helpers
nativos de ERPNext (Holiday List) / HRMS (Leave), con HRMS estrictamente opcional (runtime).
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pmo.capacity import get_capacity


def get_availability(employee: str, date=None) -> float | None:
	"""Horas disponibles del `employee` en `date`; None si no hay capacidad configurada."""
	on_date = getdate(date)

	base = get_capacity(employee, on_date)
	if base is None:
		return None  # sin capacidad → sin disponibilidad derivable (no 0)

	holiday_list = _holiday_list_for(employee)
	if holiday_list and _is_holiday(holiday_list, on_date):
		return 0.0

	leave = _classify_leave(_approved_leaves(employee, on_date), on_date)
	if leave == "full":
		return 0.0
	if leave == "half":
		return flt(base / 2, 2)
	return flt(base, 2)


def get_availability_range(employee: str, from_date, to_date) -> dict:
	"""{date: availability|None} por cada día de [from_date, to_date] (inclusive)."""
	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(_("To Date no puede ser anterior a From Date."))

	result = {}
	day = start
	while day <= end:
		result[day] = get_availability(employee, day)
		day += timedelta(days=1)
	return result


# --- helpers (reutilizan nativo; HRMS opcional) ---------------------------------


def _holiday_list_for(employee: str):
	"""Holiday List del employee vía helper nativo de ERPNext (Employee → Company → Global Defaults)."""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	return get_holiday_list_for_employee(employee, raise_exception=False)


def _is_holiday(holiday_list, on_date) -> bool:
	from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

	return bool(is_holiday(holiday_list, on_date))


def _approved_leaves(employee: str, on_date) -> list[dict]:
	"""Leave Applications aprobadas del employee que cubren `on_date`. [] si HRMS no está instalado."""
	if not frappe.db.exists("DocType", "Leave Application"):
		return []
	return frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"status": "Approved",
			"docstatus": 1,
			"from_date": ["<=", on_date],
			"to_date": [">=", on_date],
		},
		fields=["half_day", "half_day_date"],
	)


def _classify_leave(leaves: list[dict], on_date) -> str | None:
	"""'full' si algún Leave cubre el día completo; 'half' si todos los que aplican son medio día ese
	día; None si no hay Leave. El medio día solo cuenta como tal si half_day_date == on_date."""
	if not leaves:
		return None
	for leave in leaves:
		is_half_on_date = leave.get("half_day") and getdate(leave.get("half_day_date")) == getdate(on_date)
		if not is_half_on_date:
			return "full"  # baja de día completo (o medio día que aplica a otra fecha)
	return "half"
