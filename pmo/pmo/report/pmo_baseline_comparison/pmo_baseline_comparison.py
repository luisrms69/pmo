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
from frappe import N_, _
from frappe.utils import flt, formatdate, getdate

from pmo.compare import compare_baselines

_DATE_FIELDS = {"exp_start_date", "exp_end_date", "expected_start_date", "expected_end_date"}
_HOUR_FIELDS = {"expected_time", "override_hours", "effective_hours"}
_FIELD_LABELS = {
	"exp_start_date": N_("Start"),
	"exp_end_date": N_("End"),
	"expected_time": N_("Hours"),
	"status": N_("Status"),
	"parent_task": N_("Parent task"),
	"wbs_order": N_("WBS order"),
	"expected_start_date": N_("Start (Project)"),
	"expected_end_date": N_("End (Project)"),
	"override_hours": N_("Override hours"),
	"effective_hours": N_("Effective hours"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	before, after = filters.get("baseline_before"), filters.get("baseline_after")
	if not (before and after):
		frappe.throw(_("Select the before and after baselines."))

	# P4 + mismo Project + carga de snapshots inmutables: todo dentro de compare_baselines (lanza si no).
	diff = compare_baselines(before, after)
	return _columns(), _rows(diff), _message(diff, filters), None, _summary(diff)


# --- columnas ------------------------------------------------------------------------


def _columns():
	def col(field, label, width=140):
		return {"fieldname": field, "label": _(label), "fieldtype": "Data", "width": width}

	return [
		col("change_type", N_("Change type"), 120),
		col("task", N_("WBS / Task"), 280),
		col("field", N_("Field"), 150),
		col("before", N_("Before"), 160),
		col("after", N_("After"), 160),
		col("variance", N_("Variance"), 110),
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
		return f"{'+' if d >= 0 else ''}{d} days"
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
				_("Project"),
				_("(Project)"),
				_flabel(field),
				_fmt(field, ch["from"]),
				_fmt(field, ch["to"]),
				_variance(field, ch["from"], ch["to"]),
			)
		)

	# Tasks añadidas / eliminadas
	for t in diff.get("tasks_added") or []:
		rows.append(_row(_("Added"), _tlabel(t), "—", "—", t.get("subject") or _("New task"), "—"))
	for t in diff.get("tasks_removed") or []:
		rows.append(_row(_("Removed"), _tlabel(t), "—", t.get("subject") or _("Previous task"), "—", "—"))

	# Tasks modificadas: una fila por campo + una fila por cambio de asignación
	for t in diff.get("tasks_changed") or []:
		label = _tlabel(t)
		for field, ch in (t.get("fields") or {}).items():
			rows.append(
				_row(
					_("Modified"),
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
					_("Assignment"),
					label,
					f"{x['user']} ({_('added')})",
					"—",
					_hours(x.get("effective_hours")),
					"—",
				)
			)
		for x in a.get("removed") or []:
			rows.append(
				_row(_("Assignment"), label, f"{x['user']} ({_('removed')})", _("assigned"), "—", "—")
			)
		for x in a.get("changed") or []:
			for field, ch in (x.get("changes") or {}).items():
				rows.append(
					_row(
						_("Assignment"),
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
		f"<b>{_('Project')}:</b> {frappe.utils.escape_html(meta.get('project') or '')}",
		f"<b>{_('Before baseline')}:</b> {frappe.utils.escape_html(b.get('revision') or b.get('name') or '')} ({b.get('effective_date') or ''})",
		f"<b>{_('After baseline')}:</b> {frappe.utils.escape_html(a.get('revision') or a.get('name') or '')} ({a.get('effective_date') or ''})",
	]
	cr = filters.get("change_request")
	if cr:
		# El CR es SOLO contexto de apertura: varios CR pueden consolidarse en una misma línea base
		# posterior. El reporte compara líneas base; no atribuye el diff a un único Change Request.
		parts.append(
			f"<b>{_('Context')}:</b> {_('opened from')} {frappe.utils.escape_html(cr)} — "
			f"{_('the report compares baselines; it does not attribute the diff to a single Change Request')}"
		)
	return "<div>" + " &nbsp;·&nbsp; ".join(parts) + "</div>"


def _summary(diff):
	n_assign = 0
	for t in diff.get("tasks_changed") or []:
		a = t.get("assignments") or {}
		n_assign += len(a.get("added") or []) + len(a.get("removed") or []) + len(a.get("changed") or [])
	return [
		{"label": _("Tasks added"), "value": len(diff.get("tasks_added") or []), "indicator": "Green"},
		{"label": _("Tasks removed"), "value": len(diff.get("tasks_removed") or []), "indicator": "Red"},
		{
			"label": _("Tasks modified"),
			"value": len(diff.get("tasks_changed") or []),
			"indicator": "Orange",
		},
		{"label": _("Assignments modified"), "value": n_assign, "indicator": "Blue"},
		{
			"label": _("Project changes"),
			"value": len(diff.get("project_changes") or {}),
			"indicator": "Grey",
		},
	]
