// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

// PMO — indicador DERIVADO de restricción de cronograma en el form nativo de Task (ADR-0018, II.2).
// Solo presentación: consume el endpoint read-only `pmo.constraints.get_constraint_status` (clasificador
// SSOT en backend) y pinta un dashboard indicator. NO calcula reglas, NO persiste nada, NO toca core.
// El texto se arma con __() (traducible); la fecha con frappe.datetime.str_to_user.

frappe.ui.form.on("Task", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "pmo.constraints.get_constraint_status",
			args: { task: frm.doc.name },
			callback: (r) => {
				const c = r && r.message;
				if (!c) return;
				const label = pmo_constraint_indicator_label(c);
				if (!label) return; // none / excluded / not_evaluable → sin aviso
				// Aviso compacto bajo el título (sin el encabezado nativo "Estadísticas" de add_indicator).
				frm.set_intro(label, pmo_constraint_indicator_color(c.state));
			},
		});
	},
});

// token de estado -> color del indicador (presentación pura).
function pmo_constraint_indicator_color(state) {
	if (state === "fnlt_violated" || state === "snet_violated") return "red";
	if (state === "incomplete") return "orange";
	return "blue"; // snet_ok / fnlt_ok
}

// Compone la etiqueta del indicador desde los tokens del backend (traducible; sin lógica de negocio).
function pmo_constraint_indicator_label(c) {
	const d = c.date ? frappe.datetime.str_to_user(c.date) : "";
	switch (c.state) {
		case "snet_ok":
			return `${__("No earlier than (SNET)")} · ${d}`;
		case "snet_violated":
			return `${__("SNET violated")} · +${c.delta_days} ${__("days")}`;
		case "fnlt_ok":
			return `${__("No later than (FNLT)")} · ${d}`;
		case "fnlt_violated":
			return `${__("FNLT violated")} · +${c.delta_days} ${__("days")}`;
		case "incomplete":
			return __("Schedule constraint without date");
		default:
			return null; // none / excluded / not_evaluable
	}
}
