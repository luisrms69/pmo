# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""ADR-0016 R1 — Historia del riesgo para impresión (solo lectura), reutilizando lo NATIVO de Frappe.

`Version` (track_changes) y `Comment` (Nota de actualización) son la ÚNICA fuente de verdad del historial. Este
helper NO almacena, NO crea snapshots, NO modifica Version/Comment ni introduce otro modelo histórico. Solo:
  1) verifica P4 (el usuario debe poder LEER el `PMO Project Risk`);
  2) recién entonces lee Version/Comment con permisos elevados, ESTRICTAMENTE acotado a ese riesgo;
  3) relaciona/formatea/traduce y devuelve una lista cronológica lista para el Print Format.

No es un bypass genérico: sin acceso al Risk lanza PermissionError; la consulta se limita al `docname` pedido.
Version y Comment se presentan como eventos adyacentes ordenados por fecha (no se fabrica una relación fuerte
Version↔Comment que Frappe no almacena).
"""

import frappe
from frappe import _
from frappe.utils import format_datetime, get_datetime, strip_html

from pmo.permissions import has_permission_risk

RISK_DT = "PMO Project Risk"

# Ventana de correlación Version↔Comment (solo PRESENTACIÓN). En un cambio material, el mismo save crea el
# Version (durante el guardado) y el Comment de Nota (en on_update): sus timestamps caen en el mismo save, a
# fracciones de segundo. Fusionamos un Comment con un Version SOLO si es INEQUÍVOCO (ver _correlate).
_SAVE_CORRELATION_SECONDS = 2

# Campos funcionales cuya evolución interesa mostrar (los demás cambios técnicos se omiten del reporte).
_TRACKED_FIELDS = (
	"description",
	"probability",
	"impact",
	"exposure",
	"status",
	"risk_owner",
	"response",
	"may_affect_controlled",
)
# Campos Select cuyos tokens deben traducirse (género correcto por token; ver risk_matrix / i18n).
_SELECT_FIELDS = ("probability", "impact", "exposure", "status", "may_affect_controlled")


def _fmt_value(field: str, value) -> str:
	if value in (None, ""):
		return ""
	return _(value) if field in _SELECT_FIELDS else str(value)


def get_risk_history(risk: str) -> list:
	"""Historia nativa (Version + Comment) del Risk, cronológica, para el Print Format. P4 obligatorio."""
	if not risk or not frappe.db.exists(RISK_DT, risk):
		return []

	# 1) P4 primero: el usuario debe poder LEER este Risk (hereda visibilidad del Project).
	doc = frappe.get_doc(RISK_DT, risk)
	if not has_permission_risk(doc, "read", frappe.session.user):
		frappe.throw(_("Not permitted to read this risk."), frappe.PermissionError)

	meta = frappe.get_meta(RISK_DT)
	change_events = []
	note_events = []

	# 2) Version (old → new). Lectura elevada ACOTADA a este docname (Version solo lo leen System Managers).
	for v in frappe.get_all(
		"Version",
		filters={"ref_doctype": RISK_DT, "docname": risk},
		fields=["owner", "creation", "data"],
		order_by="creation asc",
		ignore_permissions=True,
	):
		data = frappe.parse_json(v.data) or {}
		changes = []
		for item in data.get("changed", []) or []:
			if not item or len(item) < 3:
				continue
			field, old, new = item[0], item[1], item[2]
			if field not in _TRACKED_FIELDS:
				continue
			df = meta.get_field(field)
			label = _(df.label) if (df and df.label) else field
			changes.append({"field": label, "old": _fmt_value(field, old), "new": _fmt_value(field, new)})
		if changes:
			change_events.append(
				{
					"when": v.creation,
					"when_display": format_datetime(v.creation),
					"who": v.owner,
					"kind": "change",
					"changes": changes,
					"note": None,
				}
			)

	# 3) Comment (Nota de actualización = motivo). Lectura elevada ACOTADA a este docname.
	for c in frappe.get_all(
		"Comment",
		filters={"reference_doctype": RISK_DT, "reference_name": risk, "comment_type": "Comment"},
		fields=["owner", "creation", "content"],
		order_by="creation asc",
		ignore_permissions=True,
	):
		note_events.append(
			{
				"when": c.creation,
				"when_display": format_datetime(c.creation),
				"who": c.owner,
				"kind": "note",
				"changes": [],
				"note": strip_html(c.content or "").strip(),
			}
		)

	# 4) Correlación Version↔Comment (SOLO presentación; no altera el almacenamiento nativo).
	events = _correlate(change_events, note_events)

	# 5) Orden cronológico.
	events.sort(key=lambda e: get_datetime(e["when"]))
	return events


def _correlate(change_events: list, note_events: list) -> list:
	"""Fusiona cada Comment de Nota con el Version del MISMO guardado, SOLO cuando es INEQUÍVOCO.

	Criterio (usando la evidencia nativa disponible del save): un Comment se fusiona con un Version si
	  (a) mismo usuario (`who`), y
	  (b) sus timestamps difieren en <= `_SAVE_CORRELATION_SECONDS` (mismo save: Version en el guardado,
	      Comment en on_update), y
	  (c) existe EXACTAMENTE UN Version candidato (sin nota ya asignada) que cumple (a)+(b).
	Si hay 0 o >1 candidatos (ambigüedad), el Comment se mantiene como evento separado. No se inventan
	asociaciones: Version y Comment siguen siendo las fuentes de verdad; esto solo agrupa la PRESENTACIÓN.
	"""
	for note in note_events:
		nt = get_datetime(note["when"])
		candidates = [
			c
			for c in change_events
			if c["who"] == note["who"]
			and c["note"] is None
			and abs((get_datetime(c["when"]) - nt).total_seconds()) <= _SAVE_CORRELATION_SECONDS
		]
		if len(candidates) == 1:
			candidates[0]["note"] = note["note"]  # fusiona: el Version muestra su motivo
			note["_merged"] = True
	# Eventos = Versions (con su nota fusionada cuando aplica) + Comments que no pudieron asociarse.
	return change_events + [n for n in note_events if not n.get("_merged")]


def _print_format_translation_anchors():
	"""Anclas de i18n para las cadenas PROPIAS del Print Format `PMO Project Risk`. Frappe NO extrae los
	Print Formats al POT; referenciándolas aquí con `_()`, `generate-pot-file` las captura y sobreviven a
	`update-po-files`. No se ejecuta (solo existe para extracción). Las comunes (Date/User/Change) se heredan
	de frappe/erpnext y no se anclan."""
	return (
		_("Project Risk"),
		_("Current state"),
		_("Risk evolution"),
		_("No history recorded yet."),
		_(
			"History is sourced natively from Version (track_changes) and timeline Comments; no parallel history is stored."
		),
	)
