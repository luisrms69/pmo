// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

/* PMO Capacity (ADR-0003 D1) — ergonomía de captura. No recalcula ni valida en cliente
   (la validación vive en el controller): solo ayuda a capturar bien. */
frappe.ui.form.on("PMO Capacity", {
	onload(frm) {
		// Al crear, prellenar From Date con hoy (la capacidad rige desde esta fecha).
		if (frm.is_new() && !frm.doc.from_date) {
			frm.set_value("from_date", frappe.datetime.get_today());
		}
	},
	refresh(frm) {
		frm.set_intro(
			__(
				"Capacidad efectivo-datada: Employee vacío = baseline global; con Employee = override individual. Rige desde From Date hasta que otra fila del mismo tipo la reemplace. Sin fila vigente, el recurso queda como capacidad faltante (no se asume ningún valor)."
			),
			"blue"
		);
	},
});
