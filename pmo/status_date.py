# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Control a fecha de corte / Status Date (ADR-0006).

La Status Date (Data Date, PMI) es la fecha de corte del control del Project. Vive en el Custom Field
`Project.pmo_status_date` (D1) y en v0.7.0 solo puede ser **hoy o pasada** (D2): no se admite fecha futura
porque el Actual (Timesheet) solo existe hasta hoy y una fecha futura mezclaría planos.

Bloque 1: validación del campo. La composición Baseline/Current/Actual + indicadores (D3-D5) llega en el
Bloque 2 (motor) y Bloque 3 (reporte P4-safe).
"""

import frappe
from frappe import _
from frappe.utils import getdate, today


def validate_project_status_date(doc, method=None):
	"""ADR-0006 D2: `Project.pmo_status_date` no puede ser futura en v0.7.0. Vacío es válido (sin corte)."""
	status_date = doc.get("pmo_status_date")
	if not status_date:
		return
	if getdate(status_date) > getdate(today()):
		frappe.throw(
			_(
				"La Status Date ({0}) no puede ser una fecha futura: el control a fecha de corte solo admite hoy o una fecha pasada."
			).format(frappe.format(getdate(status_date), {"fieldtype": "Date"})),
			title=_("Status Date inválida"),
		)
