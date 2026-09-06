// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// ADR-0005 D11: comparar una baseline con la que sustituye (diferencia entre baselines).
frappe.ui.form.on("PMO Project Baseline", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.supersedes_baseline) {
			frm.add_custom_button(__("Comparar con la anterior"), () => {
				window.pmo_show_baseline_diff(
					frm.doc.supersedes_baseline,
					frm.doc.name,
					__("Cambios respecto a la baseline anterior")
				);
			});
		}
	},
});
