// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — acceso desde el form nativo de Project al PANEL PMO (Page pmo_project_control), la consola
// operativa del Project. Se retira el dropdown saturado: TODAS las capacidades (Acta, Línea base, Riesgos,
// Cambios, Cierre, Revisión + Control del proyecto) se operan desde el Panel, siempre vinculadas al Project
// actual. Aquí solo queda un acceso único con una señal discreta de pendientes de gobernanza (no un
// mini-dashboard en el formulario). La clasificación viene del motor; este JS solo cuenta desviaciones.

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.xcall("pmo.governance_inbox.get_project_governance", { project: frm.doc.name })
			.then((g) => pmo_panel_button(frm, g))
			.catch(() => pmo_panel_button(frm, null));
	},
});

function pmo_panel_button(frm, g) {
	// Señal discreta: "Panel PMO · N" cuando hay desviaciones de gobernanza (N del mismo motor). Sin N si
	// el proyecto está excluido o al día. Un único botón: el acceso principal a la consola PMO del Project.
	let label = __("PMO Panel");
	if (g && !g.exempt) {
		const n = (g.deviations || []).length;
		if (n) label = `${__("PMO Panel")} · ${n}`;
	}
	frm.add_custom_button(label, () => frappe.set_route("pmo_project_control", frm.doc.name));
}
