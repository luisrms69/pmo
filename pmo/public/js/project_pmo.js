// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — botón de navegación en el form nativo de Project (SOLO navegación).
// No modifica core, no crea campos/DocTypes, no cambia permisos ni añade lógica PMO al form: solo abre la
// Page `PMO Project Control` con este Project (que lee el contexto de frappe.get_route()[1]). La P4 la
// impone Project Control server-side; este botón no descubre ni expone nada.

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("PMO Project Control"),
			() => frappe.set_route("pmo_project_control", frm.doc.name),
			__("PMO")
		);
	},
});
