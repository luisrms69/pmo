# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Resolución de capacidad (jornada neta potencial) - fuente real = HRMS/Shift (ADR-0003 / Capacity Paso 4).

`get_employee_daily_capacity(employee, date)` es la ÚNICA resolución de capacidad del app; Availability y
los reportes la reutilizan, no reimplementan la lógica. **NO** consulta `PMO Capacity` (deprecado).

Cadena de resolución (Employee, fecha):
    1. **Shift de HRMS**: `get_shifts_for_date` resuelve el Shift Type aplicable ese día (Shift Assignment
       submitted/Active que cubre la fecha) y, si no hay, `Employee.default_shift`. Capacidad = jornada NETA =
       span bruto `(end_time - start_time)` - `Shift Type.pmo_unpaid_break_minutes` (Custom Field). Si el
       turno cruza medianoche, el span suma 24 h. `origin="shift"`, `missing_shift=False`.
    2. si no hay Shift resoluble (o HRMS no instalado) → `PMO Settings.default_capacity_hours_per_day`.
       `origin="default"`, `missing_shift=True` (falta jornada en HRMS, aunque haya fallback).
    3. si tampoco hay default → `hours=None`, `origin="missing"`, `missing_shift=True`.

HRMS es **dependencia requerida** de pmo (`required_apps`), por lo que la resolución de Shift se usa
directamente, sin guards condicionales. Si un Employee no tiene Shift resoluble, se cae al default.
Separación: Capacity = jornada neta; Availability resta Holiday/Leave; Allocation = carga; Actual = Timesheet.
"""

import datetime as _dt

import frappe
from frappe import _
from frappe.utils import flt, get_time, getdate
from hrms.hr.doctype.shift_assignment.shift_assignment import get_shifts_for_date

# --- fórmula de jornada neta (pura, sin dependencias de DocType) ----------------


def _time_to_seconds(value) -> float:
	"""Segundos desde medianoche de un valor de campo Time (timedelta/time/str)."""
	if isinstance(value, _dt.timedelta):
		return value.total_seconds()
	if isinstance(value, _dt.time):
		return value.hour * 3600 + value.minute * 60 + value.second
	t = get_time(value)
	return t.hour * 3600 + t.minute * 60 + t.second


def _span_minutes(start_time, end_time) -> float:
	"""Span bruto del turno en minutos. Si cruza medianoche (`end <= start`) suma 24 h."""
	diff = _time_to_seconds(end_time) - _time_to_seconds(start_time)
	if diff <= 0:
		diff += 24 * 3600
	return diff / 60.0


def net_shift_hours(start_time, end_time, unpaid_break_minutes=0) -> float:
	"""Jornada NETA en horas = (span bruto - break no pagado), nunca negativa. Función pura (testeable)."""
	net_min = max(0.0, _span_minutes(start_time, end_time) - flt(unpaid_break_minutes))
	return flt(net_min / 60.0, 2)


# --- resolución del Shift aplicable (HRMS requerido) ----------------------------


def _resolve_shift_type_name(employee: str, on_date) -> str | None:
	"""Nombre del Shift Type aplicable al `employee` en `on_date`; None si no hay turno resoluble.

	Para CAPACIDAD interesa "qué turno aplica ese DÍA", no la desambiguación por hora (que HRMS usa para
	asistencia). Por eso se usa `get_shifts_for_date` (Shift Assignment submitted/Active que cubre la
	fecha, independiente de la hora) → si no hay, `Employee.default_shift`. Si varios turnos cubren el día
	(split shift) se toma el primero; sumar split shifts queda como mejora futura (ver ADR/gaps)."""
	ts = _dt.datetime.combine(getdate(on_date), _dt.time.min)
	shifts = get_shifts_for_date(employee, ts) or []
	if shifts:
		return shifts[0].get("shift_type")
	return frappe.db.get_value("Employee", employee, "default_shift") or None


def _net_hours_for_shift(shift_type_name: str) -> float | None:
	"""Jornada neta del Shift Type (span - `pmo_unpaid_break_minutes`). None si falta start/end."""
	st = frappe.db.get_value(
		"Shift Type",
		shift_type_name,
		["start_time", "end_time", "pmo_unpaid_break_minutes"],
		as_dict=True,
	)
	if not st or st.get("start_time") is None or st.get("end_time") is None:
		return None
	return net_shift_hours(st.start_time, st.end_time, st.get("pmo_unpaid_break_minutes"))


def _global_default_hours() -> float | None:
	"""Default global de horas/día desde `PMO Settings.default_capacity_hours_per_day`. 0/None/neg → None."""
	hours = flt(frappe.db.get_single_value("PMO Settings", "default_capacity_hours_per_day"))
	return hours if hours > 0 else None


# --- SSOT ------------------------------------------------------------------------


def get_employee_daily_capacity(employee: str, date=None) -> dict:
	"""Capacidad (jornada neta potencial) del `employee` en `date` con metadata de origen.

	Devuelve `{hours, origin, shift_type, missing_shift}`:
	    - `origin="shift"` → `hours` = jornada neta del Shift resuelto; `missing_shift=False`.
	    - `origin="default"` → sin Shift; `hours` = default de PMO Settings; `missing_shift=True`.
	    - `origin="missing"` → sin Shift y sin default; `hours=None`; `missing_shift=True`.
	`missing_shift=True` señala falta de jornada en HRMS aunque exista fallback (no implica hours=0).
	"""
	on_date = getdate(date)

	shift_name = _resolve_shift_type_name(employee, on_date)
	if shift_name:
		return {
			"hours": _net_hours_for_shift(shift_name),
			"origin": "shift",
			"shift_type": shift_name,
			"missing_shift": False,
		}

	default_hours = _global_default_hours()
	if default_hours is not None:
		return {"hours": default_hours, "origin": "default", "shift_type": None, "missing_shift": True}

	return {"hours": None, "origin": "missing", "shift_type": None, "missing_shift": True}


def get_capacity(employee: str | None, date=None, throw: bool = False) -> float | None:
	"""Horas laborables/día del `employee` en `date` (jornada neta). None si no hay capacidad resoluble."""
	detail = get_capacity_detail(employee, date, throw=throw)
	return detail["hours"] if detail else None


def get_capacity_detail(employee: str | None, date=None, throw: bool = False) -> dict | None:
	"""Resolución con origen (fuente única). `{hours, origin, shift_type, missing_shift, from_date}` o None.

	`None` cuando no hay capacidad resoluble (`origin="missing"`); con `throw=True` lanza. `from_date` se
	conserva como `None` (la jornada de Shift/Settings no es efectivo-datada en este contrato)."""
	cap = get_employee_daily_capacity(employee, date)
	if cap["hours"] is None:
		if throw:
			frappe.throw(
				_("No capacity resolvable (no shift and no default) for {0} on {1}.").format(
					employee or "", frappe.format(getdate(date), {"fieldtype": "Date"})
				)
			)
		return None
	return {
		"hours": cap["hours"],
		"origin": cap["origin"],
		"shift_type": cap["shift_type"],
		"missing_shift": cap["missing_shift"],
		"from_date": None,
	}
