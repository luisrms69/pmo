# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""PMO Baseline Comparison (ADR-0005 D11) — Script Report a pantalla completa que explica qué cambió
entre dos líneas base del mismo Project. Patrón `Compare Projects` de MS Project: solo diferencias.

Reutiliza `pmo.compare.compare_baselines()` (NO otro engine): esa función impone P4 (read en AMBAS
baselines = `is_project_visible`) y exige mismo Project → el reporte es P4-safe por delegación (los Script
Report no aplican `permission_query_conditions`, así que la P4 se valida explícitamente dentro de
`execute`, como el resto de reports P4 de la app). Sin persistir el diff.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from pmo.compare import compare_baselines

_DATE_FIELDS = {"exp_start_date", "exp_end_date", "expected_start_date", "expected_end_date"}
_HOUR_FIELDS = {"expected_time", "override_hours", "effective_hours"}
_FIELD_LABELS = {
	"exp_start_date": "Inicio",
	"exp_end_date": "Fin",
	"expected_time": "Horas",
	"status": "Estado",
	"parent_task": "Tarea padre",
	"wbs_order": "Orden WBS",
	"expected_start_date": "Inicio (Proyecto)",
	"expected_end_date": "Fin (Proyecto)",
	"override_hours": "Horas override",
	"effective_hours": "Horas efectivas",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	before, after = filters.get("baseline_before"), filters.get("baseline_after")
	if not (before and after):
		frappe.throw(_("Selecciona la línea base previa y la posterior."))

	# P4 + mismo Project + carga de snapshots inmutables: todo dentro de compare_baselines (lanza si no).
	diff = compare_baselines(before, after)
	return _columns(), _rows(diff), _message(diff, filters), None, _summary(diff)


# --- columnas ------------------------------------------------------------------------


def _columns():
	def col(field, label, width=140):
		return {"fieldname": field, "label": _(label), "fieldtype": "Data", "width": width}

	return [
		col("change_type", "Tipo de cambio", 120),
		col("task", "WBS / Tarea", 280),
		col("field", "Campo", 150),
		col("before", "Antes", 160),
		col("after", "Después", 160),
		col("variance", "Variación", 110),
	]


# --- filas (solo diferencias; una fila por diferencia atómica) ------------------------


def _flabel(field):
	return _(_FIELD_LABELS.get(field, field))


def _tlabel(t):
	name, subject = t.get("name"), t.get("subject") or ""
	return f"{name} — {subject}".rstrip(" —") if name else (subject or "—")


def _fmt(field, value):
	if value in (None, ""):
		return "—"
	if field in _DATE_FIELDS:
		return formatdate(value)
	return str(value)


def _hours(value):
	return f"{flt(value, 2)} h" if value not in (None, "") else "—"


def _variance(field, before, after):
	if field in _DATE_FIELDS and before and after:
		d = (getdate(after) - getdate(before)).days
		return f"{'+' if d >= 0 else ''}{d} días"
	if field in _HOUR_FIELDS:
		d = flt(flt(after) - flt(before), 2)
		return f"{'+' if d >= 0 else ''}{d} h"
	return "—"


def _row(change_type, task, field, before, after, variance):
	return {
		"change_type": change_type,
		"task": task,
		"field": field,
		"before": before,
		"after": after,
		"variance": variance,
	}


def _rows(diff):
	rows = []

	# Nivel Project
	for field, ch in (diff.get("project_changes") or {}).items():
		rows.append(
			_row(
				_("Proyecto"),
				_("(Proyecto)"),
				_flabel(field),
				_fmt(field, ch["from"]),
				_fmt(field, ch["to"]),
				_variance(field, ch["from"], ch["to"]),
			)
		)

	# Tasks añadidas / eliminadas
	for t in diff.get("tasks_added") or []:
		rows.append(_row(_("Añadida"), _tlabel(t), "—", "—", t.get("subject") or _("Nueva tarea"), "—"))
	for t in diff.get("tasks_removed") or []:
		rows.append(_row(_("Eliminada"), _tlabel(t), "—", t.get("subject") or _("Tarea anterior"), "—", "—"))

	# Tasks modificadas: una fila por campo + una fila por cambio de asignación
	for t in diff.get("tasks_changed") or []:
		label = _tlabel(t)
		for field, ch in (t.get("fields") or {}).items():
			rows.append(
				_row(
					_("Modificada"),
					label,
					_flabel(field),
					_fmt(field, ch["from"]),
					_fmt(field, ch["to"]),
					_variance(field, ch["from"], ch["to"]),
				)
			)
		a = t.get("assignments") or {}
		for x in a.get("added") or []:
			rows.append(
				_row(
					_("Asignación"),
					label,
					f"{x['user']} ({_('alta')})",
					"—",
					_hours(x.get("effective_hours")),
					"—",
				)
			)
		for x in a.get("removed") or []:
			rows.append(_row(_("Asignación"), label, f"{x['user']} ({_('baja')})", _("asignado"), "—", "—"))
		for x in a.get("changed") or []:
			for field, ch in (x.get("changes") or {}).items():
				rows.append(
					_row(
						_("Asignación"),
						label,
						f"{x['user']} · {_flabel(field)}",
						_hours(ch["from"]),
						_hours(ch["to"]),
						_variance(field, ch["from"], ch["to"]),
					)
				)
	return rows


# --- cabecera (message) y resumen (report_summary) -----------------------------------


def _message(diff, filters):
	meta = diff.get("meta") or {}
	b, a = meta.get("before") or {}, meta.get("after") or {}
	parts = [
		f"<b>{_('Proyecto')}:</b> {frappe.utils.escape_html(meta.get('project') or '')}",
		f"<b>{_('Línea base previa')}:</b> {frappe.utils.escape_html(b.get('revision') or b.get('name') or '')} ({b.get('effective_date') or ''})",
		f"<b>{_('Línea base posterior')}:</b> {frappe.utils.escape_html(a.get('revision') or a.get('name') or '')} ({a.get('effective_date') or ''})",
	]
	cr = filters.get("change_request")
	if cr:
		# El CR es SOLO contexto de apertura: varios CR pueden consolidarse en una misma línea base
		# posterior. El reporte compara líneas base; no atribuye el diff a un único Change Request.
		parts.append(
			f"<b>{_('Contexto')}:</b> {_('abierto desde')} {frappe.utils.escape_html(cr)} — "
			f"{_('el reporte compara líneas base; no atribuye el diff a un solo Change Request')}"
		)
	return "<div>" + " &nbsp;·&nbsp; ".join(parts) + "</div>"


def _summary(diff):
	n_assign = 0
	for t in diff.get("tasks_changed") or []:
		a = t.get("assignments") or {}
		n_assign += len(a.get("added") or []) + len(a.get("removed") or []) + len(a.get("changed") or [])
	return [
		{"label": _("Tareas añadidas"), "value": len(diff.get("tasks_added") or []), "indicator": "Green"},
		{"label": _("Tareas eliminadas"), "value": len(diff.get("tasks_removed") or []), "indicator": "Red"},
		{
			"label": _("Tareas modificadas"),
			"value": len(diff.get("tasks_changed") or []),
			"indicator": "Orange",
		},
		{"label": _("Asignaciones modificadas"), "value": n_assign, "indicator": "Blue"},
		{
			"label": _("Cambios de Proyecto"),
			"value": len(diff.get("project_changes") or {}),
			"indicator": "Grey",
		},
	]
