// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// ADR-0005 D11: abrir el reporte PMO Baseline Comparison comparando esta línea base con la que sustituye.
frappe.ui.form.on("PMO Project Baseline", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.supersedes_baseline) {
			frm.add_custom_button(__("Compare with previous baseline"), () => {
				frappe.set_route("query-report", "PMO Baseline Comparison", {
					project: frm.doc.project,
					baseline_before: frm.doc.supersedes_baseline,
					baseline_after: frm.doc.name,
				});
			});
		}
	},
});
